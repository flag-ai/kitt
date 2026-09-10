"""Individual hardware detection functions with fallbacks."""

import logging
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    model: str
    vram_gb: int
    count: int = 1
    compute_capability: tuple[int, int] | None = None


@dataclass
class CPUInfo:
    model: str
    cores: int
    threads: int


@dataclass
class StorageInfo:
    brand: str
    model: str
    type: str  # 'nvme', 'ssd', 'hdd', 'unknown'


def detect_environment_type() -> str:
    """Detect if running in WSL2, Docker, DGX, or native.

    Returns:
        One of: 'dgx_spark', 'dgx', 'wsl2', 'docker', 'container',
                'native_linux', 'native_macos', 'native_windows', 'unknown'
    """
    # Check for DGX OS
    dgx_release = Path("/etc/dgx-release")
    if dgx_release.exists():
        try:
            content = dgx_release.read_text().lower()
            if "spark" in content:
                return "dgx_spark"
            return "dgx"
        except Exception:
            return "dgx"

    # Also check for NVIDIA DGX via nv-fabricmanager or other markers
    if Path("/etc/nvidia/nvidia-dgs.conf").exists():
        return "dgx_spark"

    # Check for WSL2
    try:
        version = Path("/proc/version").read_text().lower()
        if "microsoft" in version or "wsl" in version:
            return "wsl2"
    except Exception:
        pass

    # Check for Docker
    if Path("/.dockerenv").exists():
        return "docker"

    # Check for other containers
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
        if "docker" in cgroup or "lxc" in cgroup:
            return "container"
    except Exception:
        pass

    # Native
    system = platform.system()
    native_env = {
        "Linux": "native_linux",
        "Darwin": "native_macos",
        "Windows": "native_windows",
    }
    return native_env.get(system, "unknown")


def detect_gpu(environment_type: str | None = None) -> GPUInfo | None:
    """Detect GPU with multiple fallback methods.

    Method 1: pynvml (most reliable)
    Method 2: nvidia-smi CLI

    Args:
        environment_type: Detected environment type, used to provide
            better diagnostics on systems known to have GPUs.
    """
    pynvml_error = None
    smi_error = None

    # Method 1: pynvml
    try:
        import pynvml

        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count > 0:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            # Memory query may fail on unified memory architectures (e.g. GH200)
            vram_gb = 0
            try:
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_gb = int(mem.total / (1024**3))
            except Exception as mem_err:
                logger.debug(f"pynvml memory query failed (unified memory?): {mem_err}")

            # Compute capability detection
            cc = None
            try:
                major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                cc = (major, minor)
            except Exception as cc_err:
                logger.debug(f"pynvml compute capability query failed: {cc_err}")

            pynvml.nvmlShutdown()

            return GPUInfo(
                model=name,
                vram_gb=vram_gb,
                count=device_count,
                compute_capability=cc,
            )
    except Exception as e:
        pynvml_error = e
        logger.debug(f"pynvml detection failed: {e}")

    # Method 2: nvidia-smi
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines:
                name, mem = lines[0].split(",")
                mem_str = mem.strip().split()[0]
                # Memory may be '[N/A]' on unified memory architectures (e.g. GH200)
                try:
                    vram_gb = int(mem_str) // 1024
                except ValueError:
                    vram_gb = 0
                    logger.debug(
                        f"nvidia-smi reported memory as '{mem_str}' (unified memory?)"
                    )
                cc = _detect_compute_capability_smi()
                return GPUInfo(
                    model=name.strip(),
                    vram_gb=vram_gb,
                    count=len(lines),
                    compute_capability=cc,
                )
        else:
            smi_error = (
                result.stderr.strip()
                if result.stderr
                else f"exit code {result.returncode}"
            )
    except Exception as e:
        smi_error = str(e)
        logger.debug(f"nvidia-smi detection failed: {e}")

    # Provide environment-aware diagnostics
    if environment_type in ("dgx_spark", "dgx"):
        logger.warning(
            f"GPU detection failed on {environment_type} environment. "
            f"This system should have an NVIDIA GPU. "
            f"Check that NVIDIA drivers are loaded and accessible. "
            f"pynvml error: {pynvml_error}; nvidia-smi error: {smi_error}"
        )
    else:
        logger.warning("No NVIDIA GPU detected")

    return None


def _detect_compute_capability_smi() -> tuple[int, int] | None:
    """Detect GPU compute capability via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=compute_cap",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            cap_str = result.stdout.strip().split("\n")[0].strip()
            parts = cap_str.split(".")
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
    except Exception as e:
        logger.debug(f"nvidia-smi compute capability detection failed: {e}")
    return None


def detect_gpu_compute_capability() -> tuple[int, int] | None:
    """Detect GPU compute capability.

    Returns:
        Tuple of (major, minor) compute capability, or None if not detected.
        E.g. (8, 9) for Ada Lovelace, (12, 1) for GB10 Blackwell.
    """
    # Try pynvml first
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
        pynvml.nvmlShutdown()
        return (major, minor)
    except Exception:
        pass

    # Fallback to nvidia-smi
    return _detect_compute_capability_smi()


def detect_cpu() -> CPUInfo:
    """Detect CPU information with fallbacks."""
    try:
        import cpuinfo
        import psutil

        info = cpuinfo.get_cpu_info()
        return CPUInfo(
            model=info.get("brand_raw", "Unknown"),
            cores=psutil.cpu_count(logical=False) or 0,
            threads=psutil.cpu_count(logical=True) or 0,
        )
    except Exception as e:
        logger.warning(f"CPU detection failed: {e}")
        return CPUInfo(model="Unknown", cores=0, threads=0)


def detect_ram_gb() -> int:
    """Detect total RAM in GB."""
    try:
        import psutil

        return int(psutil.virtual_memory().total / (1024**3))
    except Exception:
        return 0


def detect_ram_type() -> str:
    """Detect RAM type (DDR4, DDR5, etc.) with fallbacks.

    Returns "Unknown" if detection fails.
    """
    system = platform.system()

    if system == "Linux":
        # Try dmidecode first (needs root)
        try:
            result = subprocess.run(
                ["sudo", "dmidecode", "-t", "memory"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line.startswith("Type:") and "DDR" in line:
                        for ddr in ["DDR5", "DDR4", "DDR3"]:
                            if ddr in line:
                                return ddr
        except Exception as e:
            logger.debug(f"dmidecode check failed: {e}")

        # Try lshw
        try:
            result = subprocess.run(
                ["lshw", "-short", "-C", "memory"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    for ddr in ["DDR5", "DDR4", "DDR3"]:
                        if ddr in line:
                            return ddr
        except Exception as e:
            logger.debug(f"lshw check failed: {e}")

    elif system == "Darwin":
        try:
            result = subprocess.run(
                ["system_profiler", "SPMemoryDataType"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "Type:" in line and "DDR" in line:
                        for ddr in ["DDR5", "DDR4", "DDR3"]:
                            if ddr in line:
                                return ddr
        except Exception:
            pass

    logger.warning("Could not detect RAM type")
    return "Unknown"


def detect_storage() -> StorageInfo:
    """Detect primary storage brand and model."""
    system = platform.system()

    if system == "Linux":
        return _detect_storage_linux()
    elif system == "Darwin":
        return _detect_storage_macos()

    return StorageInfo(brand="Unknown", model="Unknown", type="unknown")


def _detect_storage_linux() -> StorageInfo:
    """Detect storage on Linux systems."""
    known_brands = [
        "Samsung",
        "WD",
        "Western Digital",
        "Intel",
        "Crucial",
        "Kingston",
        "SK hynix",
        "Seagate",
        "Micron",
    ]

    # Check /sys/block for NVMe devices
    try:
        nvme_devices = list(Path("/sys/block").glob("nvme*"))
        if nvme_devices:
            device = nvme_devices[0]
            model_file = device / "device" / "model"
            if model_file.exists():
                model = model_file.read_text().strip()
                brand = _extract_brand(model, known_brands)
                return StorageInfo(brand=brand, model=model, type="nvme")
    except Exception as e:
        logger.debug(f"NVMe detection failed: {e}")

    # Try lsblk
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,TYPE,MODEL"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    model = " ".join(parts[2:])
                    brand = _extract_brand(model, known_brands)
                    storage_type = "nvme" if "nvme" in parts[0] else "ssd"
                    return StorageInfo(brand=brand, model=model, type=storage_type)
    except Exception as e:
        logger.debug(f"lsblk detection failed: {e}")

    return StorageInfo(brand="Unknown", model="Unknown", type="unknown")


def _detect_storage_macos() -> StorageInfo:
    """Detect storage on macOS."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPNVMeDataType"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.split("\n"):
                if "Model:" in line:
                    model = line.split(":", 1)[1].strip()
                    brand = "Apple" if "Apple" in model else "Unknown"
                    return StorageInfo(brand=brand, model=model, type="nvme")
    except Exception:
        pass

    return StorageInfo(brand="Unknown", model="Unknown", type="unknown")


def _extract_brand(model: str, known_brands: list) -> str:
    """Extract brand name from model string."""
    model_lower = model.lower()
    for brand in known_brands:
        if brand.lower() in model_lower:
            if brand == "Western Digital":
                return "WD"
            return brand
    return "Unknown"


def detect_cuda_version() -> str | None:
    """Detect CUDA version."""
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "release" in line.lower():
                    parts = line.split("release")
                    if len(parts) > 1:
                        version = parts[1].strip().split(",")[0].strip()
                        return version
    except Exception:
        pass
    return None


def detect_driver_version() -> str | None:
    """Detect NVIDIA driver version."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None
