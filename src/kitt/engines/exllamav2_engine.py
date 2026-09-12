"""ExLlamaV2 inference engine — Docker + OpenAI-compatible API."""

import logging
import time
from pathlib import Path
from typing import Any

from .base import GenerationResult, InferenceEngine
from .registry import register_engine

logger = logging.getLogger(__name__)


@register_engine
class ExLlamaV2Engine(InferenceEngine):
    """ExLlamaV2 inference engine for GPTQ and EXL2 model formats.

    Runs ExLlamaV2 in a Docker container with an OpenAI-compatible API.
    """

    def __init__(self) -> None:
        self._container_id: str | None = None  # type: ignore[assignment]
        self._base_url: str = ""
        self._model_name: str = ""

    @classmethod
    def name(cls) -> str:
        return "exllamav2"

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["gptq", "exl2", "gguf"]

    @classmethod
    def default_image(cls) -> str:
        return "ghcr.io/turboderp/exllamav2:latest"

    @classmethod
    def default_port(cls) -> int:
        return 8082

    @classmethod
    def container_port(cls) -> int:
        return 8080

    @classmethod
    def health_endpoint(cls) -> str:
        return "/health"

    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Start ExLlamaV2 container and wait for healthy."""
        from .lifecycle import EngineMode

        self._mode = EngineMode.DOCKER

        from .docker_manager import ContainerConfig, DockerManager

        model_abs = str(Path(model_path).resolve())
        model_basename = Path(model_path).name
        self._model_name = f"/models/{model_basename}"
        port = config.get("port", self.default_port())

        cmd_args = [
            "--model-dir",
            self._model_name,
            "--host",
            "0.0.0.0",
            "--port",
            str(self.container_port()),
        ]

        if "max_seq_len" in config:
            cmd_args.extend(["--max-seq-len", str(config["max_seq_len"])])
        if "gpu_split" in config:
            cmd_args.extend(["--gpu-split", config["gpu_split"]])

        # Mount model directory
        model_dir = str(Path(model_abs).parent)
        is_directory = Path(model_abs).is_dir()

        container_cfg = ContainerConfig(
            image=config.get("image", self.resolved_image()),
            port=port,
            container_port=self.container_port(),
            volumes={
                model_abs if is_directory else model_dir: "/models"
                if is_directory
                else "/models"
            },
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
                max_tokens=max_tokens,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

        return parse_openai_result(response, elapsed_ms, tracker)

    def cleanup(self) -> None:
        """Stop the ExLlamaV2 engine."""
        super().cleanup()
