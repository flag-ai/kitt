"""Ollama inference engine implementation — Docker and native modes."""

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from .base import GenerationMetrics, GenerationResult, InferenceEngine
from .lifecycle import EngineMode
from .registry import register_engine

logger = logging.getLogger(__name__)


@register_engine
class OllamaEngine(InferenceEngine):
    """Ollama inference engine — Docker or native service.

    Communicates via the Ollama HTTP API (/api/generate).
    """

    def __init__(self) -> None:
        self._container_id: str | None = None  # type: ignore[assignment]
        self._base_url: str = ""
        self._model_name: str = ""

    @classmethod
    def name(cls) -> str:
        return "ollama"

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["gguf"]

    @classmethod
    def default_image(cls) -> str:
        return "ollama/ollama:latest"

    @classmethod
    def default_port(cls) -> int:
        return 11434

    @classmethod
    def container_port(cls) -> int:
        return 11434

    @classmethod
    def health_endpoint(cls) -> str:
        return "/api/tags"

    @staticmethod
    def _is_local_gguf(model_path: str) -> bool:
        """Check if model_path points to a local GGUF file or directory."""
        from pathlib import Path

        p = Path(model_path)
        if p.is_file() and p.suffix == ".gguf":
            return True
        return bool(p.is_dir() and any(p.glob("*.gguf")))

    @staticmethod
    def _resolve_gguf_path(model_path: str) -> str:
        """Resolve a GGUF model path to the first .gguf file."""
        from pathlib import Path

        p = Path(model_path).resolve()
        if p.is_dir():
            gguf_files = sorted(p.glob("*.gguf"))
            if not gguf_files:
                raise FileNotFoundError(f"No .gguf files found in {p}")
            return str(gguf_files[0])
        return str(p)

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

        return ProcessManager.find_binary("ollama") is not None

    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Start Ollama, wait for healthy, and load the model.

        Supports both Ollama registry model names (e.g. 'llama3:8b') and
        local GGUF files/directories.
        """
        self._mode = EngineMode(config.get("mode", self.default_mode()))

        if self._mode == EngineMode.NATIVE:
            self._initialize_native(model_path, config)
        else:
            self._initialize_docker(model_path, config)

    def _initialize_native(self, model_path: str, config: dict[str, Any]) -> None:
        """Start or reuse Ollama native service and load the model."""
        import subprocess

        from .docker_manager import DockerManager
        from .process_manager import ProcessManager

        port = config.get("port", self.default_port())

        # Check if Ollama is already running (e.g. via systemd)
        already_running = False
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "ollama"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            already_running = result.stdout.strip() == "active"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if not already_running:
            binary = ProcessManager.find_binary("ollama")
            if not binary:
                raise RuntimeError(
                    "ollama not found. Install Ollama or add it to your PATH."
                )
            env = {"OLLAMA_HOST": f"0.0.0.0:{port}"}
            env.update(config.get("env", {}))
            self._process = ProcessManager.start_process(binary, ["serve"], env=env)

        health_url = f"http://localhost:{port}{self.health_endpoint()}"
        startup_timeout = config.get("startup_timeout", 120.0)
        DockerManager.wait_for_healthy(health_url, timeout=startup_timeout)
        self._base_url = f"http://localhost:{port}"

        # Load the model
        local_gguf = self._is_local_gguf(model_path)
        if local_gguf:
            gguf_file = self._resolve_gguf_path(model_path)
            self._model_name = "kitt-local-model"
            modelfile_content = f"FROM {gguf_file}\n"
            logger.info("Importing local GGUF '%s' into Ollama...", gguf_file)
            create_payload = json.dumps(
                {
                    "name": self._model_name,
                    "modelfile": modelfile_content,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/api/create",
                data=create_payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=300)
        else:
            self._model_name = model_path
            logger.info("Pulling model '%s' via Ollama API...", self._model_name)
            pull_payload = json.dumps({"name": self._model_name}).encode("utf-8")
            req = urllib.request.Request(
                f"{self._base_url}/api/pull",
                data=pull_payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=600)

    def _initialize_docker(self, model_path: str, config: dict[str, Any]) -> None:
        """Start Ollama container, wait for healthy, and load the model."""
        from pathlib import Path

        from .docker_manager import ContainerConfig, DockerManager

        local_gguf = self._is_local_gguf(model_path)
        port = config.get("port", self.default_port())

        volumes = dict(config.get("volumes", {}))
        if local_gguf:
            gguf_file = self._resolve_gguf_path(model_path)
            gguf_dir = str(Path(gguf_file).parent)
            gguf_basename = Path(gguf_file).name
            # Mount the model directory into the container
            volumes[gguf_dir] = "/models"

        container_cfg = ContainerConfig(
            image=config.get("image", self.resolved_image()),
            port=port,
            container_port=self.container_port(),
            volumes=volumes,
            env=config.get("env", {}),
            extra_args=config.get("extra_args", []),
            command_args=[],
        )
        self._container_id = DockerManager.run_container(container_cfg)

        health_url = f"http://localhost:{port}{self.health_endpoint()}"
        startup_timeout = config.get("startup_timeout", 600.0)
        DockerManager.wait_for_healthy(
            health_url, timeout=startup_timeout, container_id=self._container_id
        )
        self._base_url = f"http://localhost:{port}"

        if local_gguf:
            # Import local GGUF via Modelfile — use tee to avoid shell injection
            container_model_path = f"/models/{gguf_basename}"
            self._model_name = "kitt-local-model"
            modelfile_content = f"FROM {container_model_path}\n"
            logger.info("Importing local GGUF '%s' into Ollama...", gguf_basename)
            DockerManager.exec_in_container(
                self._container_id,
                ["tee", "/tmp/Modelfile"],
                stdin_data=modelfile_content,
            )
            DockerManager.exec_in_container(
                self._container_id,
                ["ollama", "create", self._model_name, "-f", "/tmp/Modelfile"],
            )
        else:
            # Pull from Ollama registry
            self._model_name = model_path
            logger.info("Pulling model '%s' in Ollama container...", self._model_name)
            DockerManager.exec_in_container(
                self._container_id, ["ollama", "pull", self._model_name]
            )

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 2048,
        **engine_specific_params: Any,
    ) -> GenerationResult:
        """Generate via Ollama HTTP API."""
        from kitt.collectors.gpu_stats import GPUMemoryTracker

        payload = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "num_predict": max_tokens,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        with GPUMemoryTracker(gpu_index=0) as tracker:
            start_time = time.perf_counter()
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read())
            end_time = time.perf_counter()

        total_latency_ms = (end_time - start_time) * 1000

        output = result.get("response", "")
        prompt_tokens = result.get("prompt_eval_count", 0)
        completion_tokens = result.get("eval_count", 0)

        # Ollama provides eval_duration in nanoseconds
        eval_duration_ns = result.get("eval_duration", 0)
        if eval_duration_ns > 0 and completion_tokens > 0:
            tps = completion_tokens / (eval_duration_ns / 1e9)
        elif total_latency_ms > 0 and completion_tokens > 0:
            tps = completion_tokens / (total_latency_ms / 1000)
        else:
            tps = 0

        # TTFT from Ollama's prompt eval timing
        prompt_eval_duration_ns = result.get("prompt_eval_duration", 0)
        ttft_ms = prompt_eval_duration_ns / 1e6 if prompt_eval_duration_ns > 0 else 0

        metrics = GenerationMetrics(
            ttft_ms=ttft_ms,
            tps=tps,
            total_latency_ms=total_latency_ms,
            gpu_memory_peak_gb=tracker.get_peak_memory_mb() / 1024,
            gpu_memory_avg_gb=tracker.get_average_memory_mb() / 1024,
            timestamp=datetime.now(),
        )

        return GenerationResult(
            output=output,
            metrics=metrics,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def cleanup(self) -> None:
        """Stop the Ollama engine."""
        super().cleanup()
