"""Abstract base class for inference engines."""

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .lifecycle import EngineMode


@dataclass
class GenerationMetrics:
    """Metrics collected during generation."""

    ttft_ms: float  # Time to first token
    tps: float  # Tokens per second
    total_latency_ms: float
    gpu_memory_peak_gb: float
    gpu_memory_avg_gb: float
    timestamp: datetime


@dataclass
class GenerationResult:
    """Result from a generation call."""

    output: str
    metrics: GenerationMetrics
    prompt_tokens: int
    completion_tokens: int


@dataclass
class EngineDiagnostics:
    """Structured diagnostics from an engine availability check."""

    available: bool
    image: str = ""
    error: str | None = None
    guidance: str | None = None


class InferenceEngine(ABC):
    """Abstract base class for inference engines.

    Engines can run in Docker containers or as native host processes.
    The execution mode is determined by ``supported_modes()`` and
    ``default_mode()``, and can be overridden per-invocation via the
    ``mode`` key in the config dict passed to ``initialize()``.
    """

    _container_id: str | None = None
    _process: subprocess.Popen | None = None
    _mode: EngineMode | None = None

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """Engine identifier (e.g., 'vllm', 'llama_cpp')."""

    @classmethod
    @abstractmethod
    def supported_formats(cls) -> list[str]:
        """Model formats this engine supports (e.g., ['safetensors', 'pytorch'])."""

    @classmethod
    def supported_modes(cls) -> list[EngineMode]:
        """Execution modes this engine supports. Default: Docker only."""
        return [EngineMode.DOCKER]

    @classmethod
    def default_mode(cls) -> EngineMode:
        """Default execution mode for this engine."""
        return EngineMode.DOCKER

    @classmethod
    def default_image(cls) -> str:
        """Default Docker image for this engine.

        Returns empty string for native-only engines.
        """
        return ""

    @classmethod
    @abstractmethod
    def default_port(cls) -> int:
        """Default host port for this engine."""

    @classmethod
    def container_port(cls) -> int:
        """Port the engine listens on inside the container.

        Returns 0 for native-only engines.
        """
        return 0

    @classmethod
    @abstractmethod
    def health_endpoint(cls) -> str:
        """Health check URL path (e.g. '/health')."""

    @classmethod
    def resolved_image(cls) -> str:
        """Return the best Docker image for this engine on the current GPU.

        Uses hardware detection to select an optimized image when available
        (e.g. NGC containers for Blackwell GPUs), falling back to the
        default image otherwise.
        """
        from .image_resolver import resolve_image

        return resolve_image(cls.name(), cls.default_image())

    @classmethod
    def setup(cls) -> None:
        """Pull or build the Docker image for this engine.

        Uses the build recipe for KITT-managed images, or pulls from the
        registry for standard images.  Passes ``--platform linux/{arch}``
        to ensure the correct manifest is selected on multi-arch registries.

        Raises:
            RuntimeError: If Docker is not available or pull/build fails.
        """
        from .docker_manager import DockerManager
        from .image_resolver import _detect_arch, get_build_recipe

        if not DockerManager.is_docker_available():
            raise RuntimeError("Docker is not installed or not running")

        image = cls.resolved_image()
        recipe = get_build_recipe(image)
        arch = _detect_arch()
        docker_platform = f"linux/{arch}" if arch else None

        if recipe is not None:
            DockerManager.build_image(
                image=image,
                dockerfile=str(recipe.dockerfile_path),
                context_dir=str(recipe.dockerfile_path.parent),
                target=recipe.target,
                build_args=recipe.build_args,
                platform=docker_platform,
            )
        else:
            DockerManager.pull_image(image, platform=docker_platform)

    @classmethod
    def validate_model(cls, model_path: str) -> str | None:
        """Check if a model's format is compatible with this engine.

        Returns:
            Error string if the model is incompatible, None if OK.
        """
        from kitt.utils.validation import validate_model_format

        return validate_model_format(model_path, cls.supported_formats())

    @classmethod
    def is_available(cls, mode: EngineMode | None = None) -> bool:
        """Check if the engine is available in the given mode.

        For Docker mode, checks Docker availability and image status.
        For native mode, checks if the engine binary is found.
        """
        check_mode = mode or cls.default_mode()

        if check_mode == EngineMode.NATIVE:
            return cls._is_native_available()

        from .docker_manager import DockerManager

        return DockerManager.is_docker_available() and DockerManager.image_exists(
            cls.resolved_image()
        )

    @classmethod
    def _is_native_available(cls) -> bool:
        """Check if the engine binary is available for native mode.

        Subclasses should override this to check for their specific binary.
        Default returns False.
        """
        return False

    @classmethod
    def diagnose(cls, mode: EngineMode | None = None) -> EngineDiagnostics:
        """Check engine availability and return structured diagnostics.

        Dispatches to Docker or native diagnostics based on mode.
        """
        check_mode = mode or cls.default_mode()

        if check_mode == EngineMode.NATIVE:
            return cls._diagnose_native()

        return cls._diagnose_docker()

    @classmethod
    def _diagnose_docker(cls) -> EngineDiagnostics:
        """Check Docker availability and image status."""
        from .docker_manager import DockerManager

        image = cls.resolved_image()

        if not DockerManager.is_docker_available():
            return EngineDiagnostics(
                available=False,
                image=image,
                error="Docker is not installed or not running",
                guidance="Install Docker: https://docs.docker.com/get-docker/",
            )
        if not DockerManager.image_exists(image):
            from .image_resolver import is_kitt_managed_image

            if is_kitt_managed_image(image):
                return EngineDiagnostics(
                    available=False,
                    image=image,
                    error=f"Docker image not built: {image}",
                    guidance=f"Build with: kitt engines setup {cls.name()}",
                )
            return EngineDiagnostics(
                available=False,
                image=image,
                error=f"Docker image not pulled: {image}",
                guidance=f"Pull with: kitt engines setup {cls.name()}",
            )
        return EngineDiagnostics(available=True, image=image)

    @classmethod
    def _diagnose_native(cls) -> EngineDiagnostics:
        """Check native binary availability.

        Subclasses should override for engine-specific checks.
        """
        if cls._is_native_available():
            return EngineDiagnostics(available=True)
        return EngineDiagnostics(
            available=False,
            error=f"{cls.name()} binary not found",
            guidance=f"Install {cls.name()} or add it to your PATH",
        )

    @abstractmethod
    def initialize(self, model_path: str, config: dict[str, Any]) -> None:
        """Start the engine and wait for healthy.

        The ``config`` dict may include a ``mode`` key to override the
        default execution mode (``"docker"`` or ``"native"``).

        Args:
            model_path: Path to model directory or model identifier.
            config: Engine-specific configuration.
        """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int = 50,
        max_tokens: int = 2048,
        **engine_specific_params: Any,
    ) -> GenerationResult:
        """Generate response via the engine's HTTP API.

        Args:
            prompt: Input prompt.
            temperature: Sampling temperature.
            top_p: Nucleus sampling parameter.
            top_k: Top-k sampling parameter.
            max_tokens: Maximum tokens to generate.
            **engine_specific_params: Engine-specific parameters.

        Returns:
            GenerationResult with output and metrics.
        """

    def cleanup(self) -> None:
        """Stop the engine (Docker container or native process)."""
        if self._mode == EngineMode.NATIVE:
            self._cleanup_native()
        else:
            self._cleanup_docker()

    def _cleanup_docker(self) -> None:
        """Stop and remove the Docker container."""
        from .docker_manager import DockerManager

        if hasattr(self, "_container_id") and self._container_id:
            DockerManager.stop_container(self._container_id)
            self._container_id = None

    def _cleanup_native(self) -> None:
        """Stop the native process."""
        from .process_manager import ProcessManager

        if self._process is not None:
            ProcessManager.stop_process(self._process)
            self._process = None
