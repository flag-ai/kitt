"""MLX inference engine — native Apple Silicon, no Docker."""

import logging
import time
from datetime import datetime
from typing import Any

from .base import (
    EngineDiagnostics,
    GenerationMetrics,
    GenerationResult,
    InferenceEngine,
)
from .lifecycle import EngineMode
from .registry import register_engine

logger = logging.getLogger(__name__)

MLX_AVAILABLE = False
try:
    import mlx_lm

    MLX_AVAILABLE = True
except ImportError:
    pass


@register_engine
class MLXEngine(InferenceEngine):
    """Apple Silicon native inference via mlx-lm.

    Unlike other engines, MLX runs natively (no Docker container).
    Requires macOS with Apple Silicon and the mlx-lm package.
    """

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._model_path: str = ""

    @classmethod
    def name(cls) -> str:
        return "mlx"

    @classmethod
    def supported_modes(cls) -> list[EngineMode]:
        return [EngineMode.NATIVE]

    @classmethod
    def default_mode(cls) -> EngineMode:
        return EngineMode.NATIVE

    @classmethod
    def supported_formats(cls) -> list[str]:
        return ["mlx", "safetensors"]

    @classmethod
    def default_image(cls) -> str:
        return ""  # No Docker image — native execution

    @classmethod
    def default_port(cls) -> int:
        return 0  # No network port

    @classmethod
    def container_port(cls) -> int:
        return 0

    @classmethod
    def health_endpoint(cls) -> str:
        return ""

    @classmethod
    def is_available(cls, mode: EngineMode | None = None) -> bool:
        """MLX is available if mlx-lm is installed and on macOS."""
        import platform

        return MLX_AVAILABLE and platform.system() == "Darwin"

    @classmethod
    def diagnose(cls, mode: EngineMode | None = None) -> EngineDiagnostics:
        import platform

        if platform.system() != "Darwin":
            return EngineDiagnostics(
                available=False,
                error="MLX requires macOS with Apple Silicon",
                guidance="Use a Mac with M1/M2/M3/M4 chip",
            )
        if not MLX_AVAILABLE:
            return EngineDiagnostics(
                available=False,
                error="mlx-lm is not installed",
                guidance="Install with: pip install mlx-lm",
            )
        return EngineDiagnostics(available=True)

    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Load model into memory using mlx-lm."""
        self._mode = EngineMode.NATIVE

        if not MLX_AVAILABLE:
            raise RuntimeError(
                "mlx-lm is not installed. Install with: pip install mlx-lm"
            )

        self._model_path = model_path
        logger.info(f"Loading MLX model: {model_path}")

        self._model, self._tokenizer = mlx_lm.load(model_path)
        logger.info("MLX model loaded successfully")

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 2048,
        **engine_specific_params: Any,
    ) -> GenerationResult:
        """Generate text using mlx-lm."""
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Engine not initialized — call initialize() first")

        start = time.perf_counter()

        output = mlx_lm.generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=temperature if temperature > 0 else 0.0,
            top_p=top_p,
        )

        elapsed_ms = (time.perf_counter() - start) * 1000

        # Estimate token counts
        prompt_tokens = len(self._tokenizer.encode(prompt))
        completion_tokens = len(self._tokenizer.encode(output))
        tps = completion_tokens / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

        metrics = GenerationMetrics(
            ttft_ms=0,  # MLX doesn't expose TTFT
            tps=tps,
            total_latency_ms=elapsed_ms,
            gpu_memory_peak_gb=0,  # Unified memory — not tracked separately
            gpu_memory_avg_gb=0,
            timestamp=datetime.now(),
        )

        return GenerationResult(
            output=output,
            metrics=metrics,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def cleanup(self) -> None:
        """Release model from memory."""
        self._model = None
        self._tokenizer = None
