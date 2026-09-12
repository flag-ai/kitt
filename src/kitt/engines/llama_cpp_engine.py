"""llama.cpp inference engine implementation — Docker and native modes."""

import logging
import time
from pathlib import Path
from typing import Any

from .base import GenerationResult, InferenceEngine
from .lifecycle import EngineMode
from .registry import register_engine

logger = logging.getLogger(__name__)


@register_engine
class LlamaCppEngine(InferenceEngine):
    """llama.cpp inference engine — Docker or native llama-server.

    Uses the llama.cpp server which exposes an OpenAI-compatible API.
    """

    def __init__(self) -> None:
        self._container_id: str | None = None  # type: ignore[assignment]
        self._base_url: str = ""
        self._model_name: str = ""

    @classmethod
    def name(cls) -> str:
        return "llama_cpp"

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["gguf"]

    @classmethod
    def default_image(cls) -> str:
        return "ghcr.io/ggml-org/llama.cpp:server-cuda"

    @classmethod
    def default_port(cls) -> int:
        return 8081

    @classmethod
    def container_port(cls) -> int:
        return 8080

    @classmethod
    def health_endpoint(cls) -> str:
        return "/health"

    @staticmethod
    def _resolve_gguf_path(model_path: str) -> tuple[str, str]:
        """Resolve a model path to the actual GGUF file and its mount directory.

        If model_path is a directory, finds the first .gguf file inside it
        (preferring the first split shard for multi-part files).
        If model_path is a file, uses it directly.

        Returns:
            (gguf_file_abs, mount_dir) — absolute path to the GGUF file and
            the directory to mount as /models/.
        """
        p = Path(model_path).resolve()
        if p.is_dir():
            gguf_files = sorted(p.glob("*.gguf"))
            if not gguf_files:
                raise FileNotFoundError(f"No .gguf files found in {p}")
            gguf_file = gguf_files[0]
            return str(gguf_file), str(p)
        return str(p), str(p.parent)

    @classmethod
    def supported_modes(cls) -> list[EngineMode]:
        return [EngineMode.DOCKER, EngineMode.NATIVE]

    @classmethod
    def default_mode(cls) -> EngineMode:
        from kitt.hardware.detector import detect_environment_type

        if detect_environment_type() == "dgx_spark":
            return EngineMode.NATIVE
        return EngineMode.DOCKER

    @classmethod
    def _is_native_available(cls) -> bool:
        from .process_manager import ProcessManager

        return ProcessManager.find_binary("llama-server") is not None

    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Start llama.cpp server and wait for healthy."""
        self._mode = EngineMode(config.get("mode", self.default_mode()))

        if self._mode == EngineMode.NATIVE:
            self._initialize_native(model_path, config)
        else:
            self._initialize_docker(model_path, config)

    def _initialize_native(self, model_path: str, config: dict[str, Any]) -> None:
        """Start llama-server as a native process."""
        from .docker_manager import DockerManager
        from .process_manager import ProcessManager

        gguf_file, _ = self._resolve_gguf_path(model_path)
        self._model_name = gguf_file
        port = config.get("port", self.default_port())

        n_gpu_layers = config.get("n_gpu_layers", -1)
        n_ctx = config.get("n_ctx", 4096)

        args = [
            "-m",
            gguf_file,
            "--n-gpu-layers",
            str(n_gpu_layers),
            "-c",
            str(n_ctx),
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]

        binary = ProcessManager.find_binary("llama-server")
        if not binary:
            raise RuntimeError(
                "llama-server not found. Install llama.cpp or add it to your PATH."
            )

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
        """Start llama.cpp server container and wait for healthy."""
        from .docker_manager import ContainerConfig, DockerManager

        gguf_file, model_dir = self._resolve_gguf_path(model_path)
        model_basename = Path(gguf_file).name
        # Use full container path for consistency (llama.cpp serves single model)
        self._model_name = f"/models/{model_basename}"
        port = config.get("port", self.default_port())

        n_gpu_layers = config.get("n_gpu_layers", -1)
        n_ctx = config.get("n_ctx", 4096)

        cmd_args = [
            "-m",
            self._model_name,
            "--n-gpu-layers",
            str(n_gpu_layers),
            "-c",
            str(n_ctx),
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ]

        container_cfg = ContainerConfig(
            image=config.get("image", self.resolved_image()),
            port=port,
            container_port=self.container_port(),
            volumes={model_dir: "/models"},
            env=config.get("env", {}),
            extra_args=config.get("extra_args", []),
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
                top_k=top_k,
                max_tokens=max_tokens,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        return parse_openai_result(response, elapsed_ms, tracker)

    def cleanup(self) -> None:
        """Stop the llama.cpp engine."""
        super().cleanup()
