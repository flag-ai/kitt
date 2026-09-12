"""System information collection."""

import platform
from dataclasses import dataclass


@dataclass
class SystemSnapshot:
    """Snapshot of system state at time of collection."""

    os_name: str
    os_version: str
    kernel: str
    architecture: str
    python_version: str
    cpu_count_physical: int
    cpu_count_logical: int
    total_ram_gb: float
    available_ram_gb: float


def collect_system_info() -> SystemSnapshot:
    """Collect current system information.

    Returns:
        SystemSnapshot with current system state.
    """
    import psutil

    mem = psutil.virtual_memory()

    return SystemSnapshot(
        os_name=platform.system(),
        os_version=platform.release(),
        kernel=platform.version(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        cpu_count_physical=psutil.cpu_count(logical=False) or 0,
        cpu_count_logical=psutil.cpu_count(logical=True) or 0,
        total_ram_gb=round(mem.total / (1024**3), 1),
        available_ram_gb=round(mem.available / (1024**3), 1),
    )
