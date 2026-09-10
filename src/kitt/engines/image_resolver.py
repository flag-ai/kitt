"""Hardware- and platform-aware Docker image selection for inference engines.

Maps GPU compute capabilities and CPU architecture to the best Docker image
for each engine.  Blackwell-class GPUs (compute capability >= 10.0) require
NVIDIA NGC containers with proper sm_100+/sm_120+/sm_121 support.  ARM64
boards (DGX Spark, Jetson Orin) need platform-specific images when the
upstream registry only publishes x86_64 builds.

Compute Capability Reference:
- 7.x: Turing (RTX 20 series)
- 8.x: Ampere (RTX 30 series, A100)
- 8.9: Ada Lovelace (RTX 40 series)
- 9.0: Hopper (H100, H200)
- 10.0+: Blackwell (B100, B200)
- 12.0: Blackwell consumer (RTX 50 series)
- 12.1: Blackwell edge (GB10 on DGX Spark)

When adding new overrides:
1. Test on actual hardware when possible
2. Document which GPU models are affected
3. Add corresponding tests in test_image_resolver.py
"""

import logging
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Docker and the kernel use different names for the same architectures.
# Normalize to Docker conventions (amd64, arm64) for consistent comparison.
_ARCH_ALIASES: dict[str, str] = {
    "x86_64": "amd64",
    "aarch64": "arm64",
}


def normalize_arch(arch: str) -> str:
    """Normalize a CPU architecture string to Docker conventions.

    Maps kernel names (x86_64, aarch64) to Docker names (amd64, arm64).
    """
    return _ARCH_ALIASES.get(arch, arch)


# Project root (two levels up from this file: engines/ -> kitt/ -> src/ -> project)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class BuildRecipe:
    """Recipe for building a KITT-managed Docker image.

    Attributes:
        dockerfile: Path to the Dockerfile relative to project root.
        target: Docker build target stage (e.g. 'server').
        build_args: Build arguments passed via --build-arg.
        experimental: If True, warn the user before building.
    """

    dockerfile: str
    target: str | None = None
    build_args: dict[str, str] = field(default_factory=dict)
    experimental: bool = False

    @property
    def dockerfile_path(self) -> Path:
        """Absolute path to the Dockerfile."""
        return _PROJECT_ROOT / self.dockerfile


# Build recipes keyed by KITT-managed image name.
# These images are built locally instead of pulled from a registry.
_BUILD_RECIPES: dict[str, BuildRecipe] = {
    "kitt/llama-cpp:spark": BuildRecipe(
        dockerfile="docker/llama_cpp/Dockerfile.spark",
        target="server",
    ),
    "kitt/llama-cpp:arm64": BuildRecipe(
        dockerfile="docker/llama_cpp/Dockerfile.arm64",
        target="server",
    ),
    "kitt/vllm:arm64": BuildRecipe(
        dockerfile="docker/vllm/Dockerfile.arm64",
    ),
}


def get_build_recipe(image: str) -> BuildRecipe | None:
    """Return the BuildRecipe for a KITT-managed image, or None."""
    return _BUILD_RECIPES.get(image)


def is_kitt_managed_image(image: str) -> bool:
    """Check if an image is built locally by KITT (not pulled from a registry)."""
    return image in _BUILD_RECIPES


# Image overrides keyed by engine name.
# Each entry is a list of (cpu_arch, min_compute_capability, image) tuples.
# cpu_arch is None for "any architecture", or a Docker arch string (e.g.
# "arm64", "amd64").  More specific entries (arch + higher cc) come first.
#
# IMPORTANT: Keep lists sorted with most specific entries first:
#   1. Arch-specific entries before arch-wildcard (None) entries
#   2. Higher compute capability before lower within each group
_IMAGE_OVERRIDES: dict[str, list[tuple[str | None, tuple[int, int], str]]] = {
    # vLLM: Standard images use Triton which requires ptxas for the target arch.
    # Blackwell (sm_100+, sm_120, sm_121a) is not supported in standard vLLM.
    # NGC containers include proper Blackwell support.
    # NOTE: Update this tag when newer NGC releases are available. Check
    # https://catalog.ngc.nvidia.com/orgs/nvidia/containers/vllm for the
    # latest tag.  Newer models (e.g. Qwen3.5 qwen3_5) require both a newer
    # Transformers AND a vLLM version with the model arch implementation.
    # A KITT-managed Dockerfile at docker/vllm/Dockerfile.arm64 can patch
    # Transformers, but the vLLM inference impl must come from upstream.
    # Uncomment the arm64 override when NGC ships Qwen3.5 support:
    # ("arm64", (10, 0), "kitt/vllm:arm64"),
    "vllm": [
        (None, (10, 0), "nvcr.io/nvidia/vllm:26.01-py3"),
    ],
    # llama.cpp: Official CUDA images are x86_64-only.
    # On ARM64 Blackwell (DGX Spark, GB10), use the KITT-managed arm64 build.
    # On x86_64 Blackwell, fall back to the spark build (sm_121 CUDA support).
    "llama_cpp": [
        ("arm64", (10, 0), "kitt/llama-cpp:arm64"),
        (None, (10, 0), "kitt/llama-cpp:spark"),
    ],
    # Ollama: Bundles its own llama.cpp, works on all supported hardware.
    "ollama": [],
    # ExLlamaV2: Standard CUDA image works on most hardware.
    "exllamav2": [],
}

# Cache for detected compute capability (None = not yet detected)
_cc_cache: tuple[int, int] | None = None
_cc_detected: bool = False

# Cache for detected CPU architecture (None = not yet detected)
_arch_cache: str | None = None
_arch_detected: bool = False


def _detect_cc() -> tuple[int, int] | None:
    """Detect and cache GPU compute capability."""
    global _cc_cache, _cc_detected
    if _cc_detected:
        return _cc_cache
    _cc_detected = True

    try:
        from kitt.hardware.detector import detect_gpu_compute_capability

        _cc_cache = detect_gpu_compute_capability()
    except Exception as e:
        logger.debug("Compute capability detection failed: %s", e)
        _cc_cache = None

    if _cc_cache:
        logger.info("GPU compute capability: %s.%s", _cc_cache[0], _cc_cache[1])
    return _cc_cache


def _detect_arch() -> str | None:
    """Detect and cache host CPU architecture (Docker convention: amd64, arm64)."""
    global _arch_cache, _arch_detected
    if _arch_detected:
        return _arch_cache
    _arch_detected = True

    raw = platform.machine()
    _arch_cache = normalize_arch(raw) if raw else None

    if _arch_cache:
        logger.info("Host CPU architecture: %s", _arch_cache)
    return _arch_cache


_USER_CONFIG_PATH = Path.home() / ".kitt" / "engines.yaml"

# Cache for user config (None = not yet loaded, empty dict = loaded but empty/missing)
_user_config_cache: dict[str, Any] | None = None


def _load_user_overrides() -> dict[str, str]:
    """Load user image overrides from ~/.kitt/engines.yaml.

    Expected format::

        image_overrides:
          vllm: "vllm/vllm-openai:latest"
          llama_cpp: "kitt/llama-cpp:spark"

    Returns:
        Flat dict mapping engine name to image string.
    """
    global _user_config_cache
    if _user_config_cache is not None:
        return _user_config_cache.get("image_overrides", {})

    _user_config_cache = {}
    if _USER_CONFIG_PATH.is_file():
        try:
            data = yaml.safe_load(_USER_CONFIG_PATH.read_text()) or {}
            _user_config_cache = data
            overrides = data.get("image_overrides", {})
            if overrides:
                logger.info("Loaded user image overrides from %s", _USER_CONFIG_PATH)
            return overrides
        except Exception as e:
            logger.warning("Failed to read %s: %s", _USER_CONFIG_PATH, e)
    return {}


def resolve_image(engine_name: str, default_image: str) -> str:
    """Return the best Docker image for an engine on the current GPU.

    Resolution order:
    1. User config (~/.kitt/engines.yaml) — highest priority
    2. Hardware-aware overrides (_IMAGE_OVERRIDES)
    3. Engine's default_image — fallback

    Args:
        engine_name: Engine identifier (e.g. 'vllm', 'tgi').
        default_image: Fallback image when no override matches.

    Returns:
        Docker image string appropriate for the detected hardware.
    """
    # 1. Check user config first
    user_overrides = _load_user_overrides()
    user_image = user_overrides.get(engine_name)
    if user_image and isinstance(user_image, str):
        logger.info("Using user-configured image for %s: %s", engine_name, user_image)
        return user_image

    # 2. Hardware-aware overrides (arch + compute capability)
    cc = _detect_cc()
    arch = _detect_arch()
    if cc is not None:
        overrides = _IMAGE_OVERRIDES.get(engine_name, [])
        for required_arch, min_cc, image in overrides:
            # Skip if override requires a specific arch that doesn't match
            if required_arch is not None and required_arch != arch:
                continue
            if cc >= min_cc:
                logger.info(
                    "GPU cc %s.%s arch=%s matched override for %s: %s",
                    cc[0],
                    cc[1],
                    arch,
                    engine_name,
                    image,
                )
                return image

    return default_image


def clear_cache() -> None:
    """Reset all cached state (for testing)."""
    global _cc_cache, _cc_detected, _arch_cache, _arch_detected, _user_config_cache
    _cc_cache = None
    _cc_detected = False
    _arch_cache = None
    _arch_detected = False
    _user_config_cache = None


def get_supported_engines() -> list[str]:
    """Return list of engines with hardware-aware image selection.

    All engines in _IMAGE_OVERRIDES are supported, even if they have
    empty override lists (meaning default image works on all hardware).
    """
    return list(_IMAGE_OVERRIDES.keys())


def has_hardware_overrides(engine_name: str) -> bool:
    """Check if an engine has any hardware-specific image overrides.

    Args:
        engine_name: Engine identifier (e.g. 'vllm', 'tgi').

    Returns:
        True if the engine has non-empty overrides list.
    """
    return bool(_IMAGE_OVERRIDES.get(engine_name, []))


# Known engine-platform incompatibilities.
# Keyed by engine name → set of incompatible Docker arch strings.
# Engines not listed here (or with empty sets) work on all platforms.
# Populated from Phase 1-2 hardware validation on DGX Spark (arm64).
_PLATFORM_INCOMPATIBLE: dict[str, dict[str, str]] = {
    "exllamav2": {
        "arm64": "Default Docker image is x86_64-only; no ARM64 build available",
    },
}


def get_engine_compatibility(cpu_arch: str) -> dict[str, dict]:
    """Return per-engine compatibility information for a given CPU architecture.

    Args:
        cpu_arch: CPU architecture in kernel convention (x86_64, aarch64)
                  or Docker convention (amd64, arm64).

    Returns:
        Dict mapping engine name to compatibility info::

            {
                "vllm": {"compatible": True},
                "exllamav2": {"compatible": False, "reason": "No ARM64 images"},
                ...
            }
    """
    arch = normalize_arch(cpu_arch) if cpu_arch else ""
    result: dict[str, dict] = {}

    for engine_name in _IMAGE_OVERRIDES:
        incompatible = _PLATFORM_INCOMPATIBLE.get(engine_name, {})
        reason = incompatible.get(arch)
        if reason:
            result[engine_name] = {"compatible": False, "reason": reason}
        else:
            result[engine_name] = {"compatible": True}

    return result
