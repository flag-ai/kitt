"""vLLM inference engine implementation — Docker + OpenAI-compatible API."""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .base import EngineDiagnostics, GenerationResult, InferenceEngine
from .lifecycle import EngineMode
from .registry import register_engine

logger = logging.getLogger(__name__)


@register_engine
class VLLMEngine(InferenceEngine):
    """vLLM inference engine running in a Docker container.

    Communicates via the OpenAI-compatible /v1/completions API.
    """

    def __init__(self) -> None:
        self._container_id: str | None = None  # type: ignore[assignment]
        self._base_url: str = ""
        self._model_name: str = ""

    @classmethod
    def name(cls) -> str:
        return "vllm"

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["safetensors", "pytorch"]

    @classmethod
    def default_image(cls) -> str:
        return "vllm/vllm-openai:latest"

    @classmethod
    def default_port(cls) -> int:
        return 8000

    @classmethod
    def container_port(cls) -> int:
        return 8000

    @classmethod
    def health_endpoint(cls) -> str:
        return "/health"

    # NGC and KITT-managed NGC-derived images use a wrapper entrypoint
    # and need explicit 'vllm serve' instead of bare --model flags.
    _NGC_PREFIXES = ("nvcr.io/", "kitt/vllm:")

    @classmethod
    def supported_modes(cls) -> list[EngineMode]:
        return [EngineMode.DOCKER, EngineMode.NATIVE]

    # Dedicated venv for vLLM with CUDA-matched wheels.
    _VLLM_VENV_DIR = Path.home() / ".kitt" / "vllm-venv"

    @classmethod
    def _find_vllm_python(cls) -> str:
        """Find the Python interpreter that has vLLM installed.

        Checks the dedicated vLLM venv first (CUDA-matched wheels),
        then falls back to the current interpreter.
        """
        venv_python = str(cls._VLLM_VENV_DIR / "bin" / "python")
        if cls._VLLM_VENV_DIR.exists() and os.path.isfile(venv_python):
            try:
                out = subprocess.run(
                    [venv_python, "-c", "import vllm"],
                    capture_output=True,
                    timeout=10,
                )
                if out.returncode == 0:
                    return venv_python
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return sys.executable

    @classmethod
    def _is_native_available(cls) -> bool:
        """Check if vLLM is installed as a Python module."""
        python = cls._find_vllm_python()
        if python == sys.executable:
            import importlib

            try:
                importlib.import_module("vllm")
                return True
            except ImportError:
                return False
        # Dedicated venv exists and has vllm (already verified by _find_vllm_python).
        return True

    @classmethod
    def _diagnose_native(cls) -> EngineDiagnostics:
        if cls._is_native_available():
            return EngineDiagnostics(available=True)
        return EngineDiagnostics(
            available=False,
            error="vllm Python module is not installed",
            guidance="Install with: pip install vllm (or create ~/.kitt/vllm-venv/)",
        )

    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Start vLLM and wait for healthy."""
        self._mode = EngineMode(config.get("mode", self.default_mode()))

        if self._mode == EngineMode.NATIVE:
            self._initialize_native(model_path, config)
        else:
            self._initialize_docker(model_path, config)

    def _initialize_native(self, model_path: str, config: dict[str, Any]) -> None:
        """Start vLLM as a native process."""
        from .docker_manager import DockerManager
        from .process_manager import ProcessManager

        port = config.get("port", self.default_port())
        self._model_name = model_path

        args = [
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            model_path,
            "--port",
            str(port),
        ]

        if config.get("tensor_parallel_size", 1) > 1:
            args += ["--tensor-parallel-size", str(config["tensor_parallel_size"])]
        if "gpu_memory_utilization" in config:
            args += ["--gpu-memory-utilization", str(config["gpu_memory_utilization"])]

        # Use the dedicated vLLM venv if available (CUDA-matched wheels),
        # otherwise fall back to the current interpreter.
        binary = config.get("python_path") or self._find_vllm_python()
        self._process = ProcessManager.start_process(
            binary,
            args,
            env=config.get("env", {}),
        )

        health_url = f"http://localhost:{port}{self.health_endpoint()}"
        startup_timeout = config.get("startup_timeout", 600.0)
        DockerManager.wait_for_healthy(health_url, timeout=startup_timeout)
        self._base_url = f"http://localhost:{port}"

    def _initialize_docker(self, model_path: str, config: dict[str, Any]) -> None:
        """Start vLLM Docker container and wait for healthy."""
        from .docker_manager import ContainerConfig, DockerManager

        model_abs = str(Path(model_path).resolve())
        model_basename = Path(model_path).name
        # vLLM uses the container path as served_model_name
        self._model_name = f"/models/{model_basename}"
        port = config.get("port", self.default_port())
        image = config.get("image", self.resolved_image())

        # NGC images (and KITT-managed images derived from NGC) use a wrapper
        # entrypoint; prepend 'vllm serve' and pass model as a positional arg.
        if image.startswith(self._NGC_PREFIXES):
            cmd_args = [
                "vllm",
                "serve",
                self._model_name,
            ]
        else:
            cmd_args = ["--model", self._model_name]

        if config.get("tensor_parallel_size", 1) > 1:
            cmd_args += [
                "--tensor-parallel-size",
                str(config["tensor_parallel_size"]),
            ]
        if "gpu_memory_utilization" in config:
            cmd_args += [
                "--gpu-memory-utilization",
                str(config["gpu_memory_utilization"]),
            ]

        container_cfg = ContainerConfig(
            image=image,
            port=port,
            container_port=self.container_port(),
            volumes={model_abs: self._model_name},
            env=config.get("env", {}),
            extra_args=config.get("extra_args", ["--shm-size=8g"]),
            command_args=cmd_args,
        )
        self._container_id = DockerManager.run_container(container_cfg)

        health_url = f"http://localhost:{port}{self.health_endpoint()}"
        startup_timeout = config.get("startup_timeout", 600.0)
        DockerManager.wait_for_healthy(
            health_url, timeout=startup_timeout, container_id=self._container_id
        )
        self._base_url = f"http://localhost:{port}"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 2048,
        **engine_specific_params: Any,
    ) -> GenerationResult:
        """Generate via OpenAI-compatible API."""
        from kitt.collectors.gpu_stats import GPUMemoryTracker

        from .openai_compat import openai_generate, parse_openai_result

        with GPUMemoryTracker(gpu_index=0) as tracker:
            start = time.perf_counter()
            response = openai_generate(
                self._base_url,
                prompt,
                model=self._model_name,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        return parse_openai_result(response, elapsed_ms, tracker)

    def cleanup(self) -> None:
        """Stop the vLLM engine."""
        super().cleanup()
