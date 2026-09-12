"""Hardware detection for agent registration."""

import logging
import platform
import socket
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def detect_environment_type() -> str:
    """Detect environment type (dgx_spark, dgx, wsl2, docker, native_linux, etc.)."""
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

    system = platform.system()
    return {
        "Linux": "native_linux",
        "Darwin": "native_macos",
        "Windows": "native_windows",
    }.get(system, "unknown")


def _detect_gpu(ram_gb: int) -> dict[str, Any]:
    """Detect GPU info with unified memory fallback.

    Args:
        ram_gb: System RAM in GB, used as VRAM fallback for unified memory
                architectures (e.g. DGX Spark GB10) that report 0 dedicated VRAM.
    """
    result: dict[str, Any] = {
        "gpu_info": "",
        "gpu_count": 0,
        "gpu_vram_gb": 0,
        "gpu_compute_capability": "",
    }

    # Method 1: pynvml
    try:
        import pynvml

        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            pynvml.nvmlShutdown()
            return result

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode()

        # Memory query may fail on unified memory architectures
        vram_gb = 0
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            vram_gb = round(mem.total / (1024**3))
        except Exception as e:
            logger.debug(f"pynvml memory query failed (unified memory?): {e}")

        # Unified memory fallback: use system RAM
        if vram_gb == 0 and ram_gb > 0:
            vram_gb = ram_gb

        # Compute capability
        cc_str = ""
        try:
            major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
            cc_str = f"{major}.{minor}"
        except Exception:
            pass

        pynvml.nvmlShutdown()

        result["gpu_info"] = f"{name} {vram_gb}GB" if vram_gb else name
        result["gpu_count"] = count
        result["gpu_vram_gb"] = vram_gb
        result["gpu_compute_capability"] = cc_str
        return result

    except Exception as e:
        logger.debug(f"pynvml detection failed: {e}")

    # Method 2: nvidia-smi
    try:
        smi = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if smi.returncode == 0:
            lines = smi.stdout.strip().split("\n")
            if lines:
                name, mem = lines[0].split(",")
                name = name.strip()
                mem_str = mem.strip().split()[0]
                try:
                    vram_gb = int(mem_str) // 1024
                except ValueError:
                    vram_gb = 0

                # Unified memory fallback
                if vram_gb == 0 and ram_gb > 0:
                    vram_gb = ram_gb

                # Compute capability via nvidia-smi
                cc_str = ""
                try:
                    cc_result = subprocess.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=compute_cap",
                            "--format=csv,noheader",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if cc_result.returncode == 0:
                        cc_str = cc_result.stdout.strip().split("\n")[0].strip()
                except Exception:
                    pass

                result["gpu_info"] = f"{name} {vram_gb}GB" if vram_gb else name
                result["gpu_count"] = len(lines)
                result["gpu_vram_gb"] = vram_gb
                result["gpu_compute_capability"] = cc_str
                return result
    except Exception as e:
        logger.debug(f"nvidia-smi detection failed: {e}")

    return result


def _detect_cuda_version() -> str:
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
                        return parts[1].strip().split(",")[0].strip()
    except Exception:
        pass
    return ""


def _detect_driver_version() -> str:
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
    return ""


def _detect_ram_type() -> str:
    """Detect RAM type (DDR4, DDR5, etc.)."""
    if platform.system() != "Linux":
        return ""

    # Try dmidecode (needs root)
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
                    for ddr in ["DDR5", "DDR4", "DDR3", "LPDDR5X", "LPDDR5", "LPDDR4"]:
                        if ddr in line:
                            return ddr
    except Exception:
        pass

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
                for ddr in ["DDR5", "DDR4", "DDR3", "LPDDR5X", "LPDDR5", "LPDDR4"]:
                    if ddr in line:
                        return ddr
    except Exception:
        pass

    return ""


def _detect_storage() -> dict[str, str]:
    """Detect primary storage info."""
    result = {"storage_brand": "", "storage_model": "", "storage_type": ""}

    if platform.system() != "Linux":
        return result

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

    # Check NVMe devices
    try:
        nvme_devices = list(Path("/sys/block").glob("nvme*"))
        if nvme_devices:
            model_file = nvme_devices[0] / "device" / "model"
            if model_file.exists():
                model = model_file.read_text().strip()
                brand = ""
                for b in known_brands:
                    if b.lower() in model.lower():
                        brand = "WD" if b == "Western Digital" else b
                        break
                result["storage_brand"] = brand or "Unknown"
                result["storage_model"] = model
                result["storage_type"] = "nvme"
                return result
    except Exception:
        pass

    # Try lsblk
    try:
        lsblk = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,TYPE,MODEL"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if lsblk.returncode == 0:
            for line in lsblk.stdout.split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    model = " ".join(parts[2:])
                    brand = ""
                    for b in known_brands:
                        if b.lower() in model.lower():
                            brand = "WD" if b == "Western Digital" else b
                            break
                    result["storage_brand"] = brand or "Unknown"
                    result["storage_model"] = model
                    result["storage_type"] = "nvme" if "nvme" in parts[0] else "ssd"
                    return result
    except Exception:
        pass

    return result


def _build_fingerprint(info: dict[str, Any]) -> str:
    """Build a compact fingerprint string from detected hardware."""
    parts = []

    # GPU
    gpu_model = info.get("gpu_model", "")
    if gpu_model:
        gpu_name = gpu_model.replace(" ", "-")
        vram = info.get("gpu_vram_gb", 0)
        gpu_str = f"{gpu_name}-{vram}GB" if vram else gpu_name
        gpu_count = info.get("gpu_count", 1)
        if gpu_count > 1:
            gpu_str += f"-{gpu_count}x"
        parts.append(gpu_str)

    # CPU
    cpu_model = info.get("cpu_info", "Unknown")
    cpu_tokens = cpu_model.split()
    cpu_label = (
        f"{cpu_tokens[0]}-{cpu_tokens[-1]}" if len(cpu_tokens) > 1 else cpu_tokens[0]
    )
    cpu_cores = info.get("cpu_cores", 0)
    parts.append(f"{cpu_label}-{cpu_cores}c")

    # RAM
    ram_gb = info.get("ram_gb", 0)
    ram_type = info.get("ram_type", "")
    ram_str = f"{ram_gb}GB"
    if ram_type:
        ram_str += f"-{ram_type}"
    parts.append(ram_str)

    # Storage
    storage_model = info.get("storage_model", "")
    if storage_model:
        storage_brand = info.get("storage_brand", "Unknown")
        storage_type = info.get("storage_type", "")
        storage_str = f"{storage_brand}-{storage_model.replace(' ', '-')}"
        if storage_type:
            storage_str += f"-{storage_type.upper()}"
        parts.append(storage_str)

    # CUDA
    cuda = info.get("cuda_version", "")
    if cuda:
        parts.append(f"CUDA-{cuda}")

    # Driver
    driver = info.get("driver_version", "")
    if driver:
        parts.append(driver)

    # OS
    parts.append(f"{platform.system()}-{platform.release()}")

    return "_".join(parts)


def detect_system() -> dict[str, Any]:
    """Gather system info for registration payload."""
    from kitt_agent.docker_ops import normalize_arch

    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()}-{platform.release()}",
        "kernel": platform.version(),
        "cpu_arch": normalize_arch(platform.machine()),
    }

    # Environment type
    info["environment_type"] = detect_environment_type()

    # CPU
    try:
        import cpuinfo

        cpu = cpuinfo.get_cpu_info()
        info["cpu_info"] = cpu.get("brand_raw", "unknown")
        info["cpu_cores"] = cpu.get("count", 0)
    except Exception:
        info["cpu_info"] = platform.processor() or "unknown"
        info["cpu_cores"] = 0

    # CPU threads
    try:
        import psutil

        info["cpu_threads"] = psutil.cpu_count(logical=True) or 0
    except Exception:
        info["cpu_threads"] = 0

    # RAM
    try:
        import psutil

        info["ram_gb"] = round(psutil.virtual_memory().total / (1024**3))
    except Exception:
        info["ram_gb"] = 0

    # GPU (with unified memory fallback)
    gpu = _detect_gpu(info["ram_gb"])
    info["gpu_info"] = gpu["gpu_info"]
    info["gpu_count"] = gpu["gpu_count"]
    info["gpu_vram_gb"] = gpu["gpu_vram_gb"]
    info["gpu_compute_capability"] = gpu["gpu_compute_capability"]

    # Extract raw GPU model name (without VRAM suffix) for fingerprint
    gpu_model = info["gpu_info"]
    if gpu_model and info["gpu_vram_gb"]:
        # Remove the " XGB" suffix to get just the model name
        suffix = f" {info['gpu_vram_gb']}GB"
        if gpu_model.endswith(suffix):
            gpu_model = gpu_model[: -len(suffix)]
    info["gpu_model"] = gpu_model

    # CUDA & driver
    info["cuda_version"] = _detect_cuda_version()
    info["driver_version"] = _detect_driver_version()

    # RAM type
    info["ram_type"] = _detect_ram_type()

    # Storage
    storage = _detect_storage()
    info.update(storage)

    # Fingerprint string
    info["fingerprint"] = _build_fingerprint(info)

    return info
