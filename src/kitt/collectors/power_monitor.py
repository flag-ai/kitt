"""GPU power consumption monitoring."""

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PowerSample:
    """A single power reading."""

    timestamp: float
    gpu_power_watts: float
    gpu_index: int = 0


@dataclass
class PowerStats:
    """Aggregated power statistics."""

    avg_power_watts: float = 0.0
    peak_power_watts: float = 0.0
    min_power_watts: float = 0.0
    total_energy_kwh: float = 0.0
    duration_seconds: float = 0.0
    sample_count: int = 0


class PowerMonitor:
    """Monitor GPU power consumption via pynvml.

    Uses nvmlDeviceGetPowerUsage() which returns milliwatts.
    """

    def __init__(self, gpu_index: int = 0, sample_interval_ms: int = 100) -> None:
        self.gpu_index = gpu_index
        self.sample_interval_ms = sample_interval_ms
        self.samples: list[PowerSample] = []
        self._initialized = False
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

        try:
            import pynvml

            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            self._initialized = True
        except Exception as e:
            logger.debug(f"Power monitoring not available: {e}")

    @property
    def is_available(self) -> bool:
        return self._initialized

    def read_power_watts(self) -> float | None:
        """Read current GPU power in watts.

        Returns:
            Power in watts, or None if unavailable.
        """
        if not self._initialized:
            return None
        try:
            import pynvml

            milliwatts = pynvml.nvmlDeviceGetPowerUsage(self._handle)
            return milliwatts / 1000.0
        except Exception:
            return None

    def start(self) -> None:
        """Start continuous power sampling in a background thread."""
        if not self._initialized:
            return

        self.samples = []
        self._stop_event = threading.Event()

        def sample_loop():
            while not self._stop_event.is_set():
                watts = self.read_power_watts()
                if watts is not None:
                    self.samples.append(
                        PowerSample(
                            timestamp=time.time(),
                            gpu_power_watts=watts,
                            gpu_index=self.gpu_index,
                        )
                    )
                time.sleep(self.sample_interval_ms / 1000.0)

        self._thread = threading.Thread(target=sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> PowerStats:
        """Stop sampling and return aggregated stats.

        Returns:
            PowerStats with averages and totals.
        """
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

        return self.get_stats()

    def get_stats(self) -> PowerStats:
        """Calculate power statistics from collected samples."""
        if not self.samples:
            return PowerStats()

        powers = [s.gpu_power_watts for s in self.samples]

        duration = 0.0
        if len(self.samples) >= 2:
            duration = self.samples[-1].timestamp - self.samples[0].timestamp

        # Energy = sum(power * interval) in joules, convert to kWh
        interval_s = self.sample_interval_ms / 1000.0
        total_energy_j = sum(p * interval_s for p in powers)
        total_energy_kwh = total_energy_j / 3_600_000.0

        return PowerStats(
            avg_power_watts=sum(powers) / len(powers),
            peak_power_watts=max(powers),
            min_power_watts=min(powers),
            total_energy_kwh=total_energy_kwh,
            duration_seconds=duration,
            sample_count=len(powers),
        )

    def __enter__(self) -> "PowerMonitor":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
