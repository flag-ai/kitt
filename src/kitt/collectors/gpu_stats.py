"""GPU memory monitoring using pynvml."""

import atexit
import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GPUMemoryStats:
    """GPU memory statistics."""

    used_mb: float
    free_mb: float
    total_mb: float
    utilization_percent: float


class GPUMonitor:
    """Monitor GPU memory and utilization during tests."""

    # Class-level flag to only warn once per session about unsupported operations
    _stats_warned: bool = False

    def __init__(self) -> None:
        """Initialize NVIDIA Management Library."""
        self._initialized = False
        try:
            import pynvml

            pynvml.nvmlInit()
            self._initialized = True
            atexit.register(self.cleanup)
        except Exception as e:
            logger.warning(f"Could not initialize NVML: {e}")

    def cleanup(self) -> None:
        """Cleanup NVML resources."""
        if self._initialized:
            try:
                import pynvml

                pynvml.nvmlShutdown()
            except Exception:
                pass
            self._initialized = False

    def get_device_count(self) -> int:
        """Get number of GPU devices."""
        if not self._initialized:
            return 0
        try:
            import pynvml

            return pynvml.nvmlDeviceGetCount()
        except Exception:
            return 0

    def get_memory_stats(self, gpu_index: int = 0) -> GPUMemoryStats | None:
        """Get current GPU memory statistics.

        Args:
            gpu_index: GPU device index (default 0).

        Returns:
            GPUMemoryStats or None if unavailable.
        """
        if not self._initialized:
            return None

        try:
            import pynvml

            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)

            # Memory info may not be supported on unified memory systems (e.g., GB10)
            try:
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                used_mb = mem_info.used / (1024 * 1024)
                free_mb = mem_info.free / (1024 * 1024)
                total_mb = mem_info.total / (1024 * 1024)
            except pynvml.NVMLError:
                # Return None if we can't get memory info - that's the core data we need
                if not GPUMonitor._stats_warned:
                    logger.debug(
                        "GPU memory info not supported (unified memory system?)"
                    )
                    GPUMonitor._stats_warned = True
                return None

            # Utilization may also not be supported on some GPUs
            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                utilization_percent = utilization.gpu
            except pynvml.NVMLError:
                utilization_percent = 0.0

            return GPUMemoryStats(
                used_mb=used_mb,
                free_mb=free_mb,
                total_mb=total_mb,
                utilization_percent=utilization_percent,
            )
        except Exception as e:
            # Only warn once per session to avoid log spam
            if not GPUMonitor._stats_warned:
                logger.warning(f"Could not get GPU stats: {e}")
                GPUMonitor._stats_warned = True
            return None

    def get_all_gpus_stats(self) -> list[GPUMemoryStats]:
        """Get memory stats for all GPUs."""
        if not self._initialized:
            return []

        stats = []
        device_count = self.get_device_count()
        for i in range(device_count):
            gpu_stats = self.get_memory_stats(i)
            if gpu_stats:
                stats.append(gpu_stats)

        return stats

    @property
    def is_available(self) -> bool:
        """Check if GPU monitoring is available."""
        return self._initialized


class GPUMemoryTracker:
    """Context manager for tracking GPU memory during a code block."""

    def __init__(self, gpu_index: int = 0, sample_interval_ms: int = 100) -> None:
        self.gpu_index = gpu_index
        self.sample_interval_ms = sample_interval_ms
        self.monitor = GPUMonitor()
        self.samples: list[GPUMemoryStats] = []
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "GPUMemoryTracker":
        """Start monitoring."""
        if not self.monitor.is_available:
            return self

        self._stop_event = threading.Event()

        def sample_loop() -> None:
            while self._stop_event is not None and not self._stop_event.is_set():
                stats = self.monitor.get_memory_stats(self.gpu_index)
                if stats:
                    self.samples.append(stats)
                time.sleep(self.sample_interval_ms / 1000.0)

        self._thread = threading.Thread(target=sample_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop monitoring."""
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def get_peak_memory_mb(self) -> float:
        """Get peak memory usage during tracking."""
        if not self.samples:
            return 0.0
        return max(s.used_mb for s in self.samples)

    def get_average_memory_mb(self) -> float:
        """Get average memory usage during tracking."""
        if not self.samples:
            return 0.0
        return sum(s.used_mb for s in self.samples) / len(self.samples)

    def get_min_memory_mb(self) -> float:
        """Get minimum memory usage during tracking."""
        if not self.samples:
            return 0.0
        return min(s.used_mb for s in self.samples)
