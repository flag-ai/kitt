"""Hardware fingerprinting for result organization."""

import logging
import platform
from dataclasses import dataclass

from .detector import (
    CPUInfo,
    GPUInfo,
    StorageInfo,
    detect_cpu,
    detect_cuda_version,
    detect_driver_version,
    detect_environment_type,
    detect_gpu,
    detect_ram_gb,
    detect_ram_type,
    detect_storage,
)

logger = logging.getLogger(__name__)


TESTED_ENVIRONMENTS = [
    "Ubuntu 22.04 LTS (Native)",
    "Ubuntu 24.04 LTS (Native)",
    "Debian 12 (Native)",
    "macOS 13+ (Native)",
    "DGX OS / DGX Spark (Native)",
]


@dataclass
class SystemInfo:
    """Complete system hardware information."""

    gpu: GPUInfo | None
    cpu: CPUInfo
    ram_gb: int
    ram_type: str
    storage: StorageInfo
    cuda_version: str | None
    driver_version: str | None
    os: str
    kernel: str
    environment_type: str


class HardwareFingerprint:
    """Generate hardware fingerprint for result organization."""

    @staticmethod
    def generate() -> str:
        """Generate compact hardware fingerprint string."""
        info = HardwareFingerprint.detect_system()
        return HardwareFingerprint._format_fingerprint(info)

    @staticmethod
    def detect_system() -> SystemInfo:
        """Detect all system hardware with fallbacks.

        Logs warnings for low-confidence detections.
        """
        env_type = detect_environment_type()
        if env_type not in ("native_linux", "native_macos", "dgx", "dgx_spark"):
            logger.warning(
                f"Running in {env_type} environment. "
                f"Hardware detection may be incomplete. "
                f"See docs/supported_environments.md"
            )

        return SystemInfo(
            gpu=detect_gpu(environment_type=env_type),
            cpu=detect_cpu(),
            ram_gb=detect_ram_gb(),
            ram_type=detect_ram_type(),
            storage=detect_storage(),
            cuda_version=detect_cuda_version(),
            driver_version=detect_driver_version(),
            os=f"{platform.system()}-{platform.release()}",
            kernel=platform.version(),
            environment_type=env_type,
        )

    @staticmethod
    def _format_fingerprint(info: SystemInfo) -> str:
        """Format system info into compact fingerprint string."""
        parts = []

        # GPU
        if info.gpu:
            gpu_name = info.gpu.model.replace(" ", "-")
            # Unified memory architectures (e.g. GH200) report 0GB dedicated VRAM;
            # use system RAM total instead since it is shared.
            vram = info.gpu.vram_gb if info.gpu.vram_gb > 0 else info.ram_gb
            gpu_str = f"{gpu_name}-{vram}GB"
            if info.gpu.count > 1:
                gpu_str += f"-{info.gpu.count}x"
            parts.append(gpu_str)

        # CPU (first and last token of model name + core count)
        if info.cpu.model != "Unknown":
            cpu_tokens = info.cpu.model.split()
            cpu_label = (
                f"{cpu_tokens[0]}-{cpu_tokens[-1]}"
                if len(cpu_tokens) > 1
                else cpu_tokens[0]
            )
            parts.append(f"{cpu_label}-{info.cpu.cores}c")
        else:
            parts.append(f"UnknownCPU-{info.cpu.cores}c")

        # RAM
        parts.append(f"{info.ram_gb}GB-{info.ram_type}")

        # Storage
        storage_str = f"{info.storage.brand}-{info.storage.model.replace(' ', '-')}"
        if info.storage.type != "unknown":
            storage_str += f"-{info.storage.type.upper()}"
        parts.append(storage_str)

        # CUDA
        if info.cuda_version:
            parts.append(f"CUDA-{info.cuda_version}")

        # Driver
        if info.driver_version:
            parts.append(info.driver_version)

        # OS
        parts.append(info.os)

        return "_".join(parts)
