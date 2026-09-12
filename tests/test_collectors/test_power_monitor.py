"""Tests for GPU power monitoring (mocked since no GPU on dev machine)."""

import sys
from unittest.mock import MagicMock, patch

from kitt.collectors.power_monitor import PowerMonitor, PowerSample, PowerStats


class TestPowerSample:
    def test_creation(self):
        sample = PowerSample(
            timestamp=1000.0,
            gpu_power_watts=250.0,
            gpu_index=0,
        )
        assert sample.timestamp == 1000.0
        assert sample.gpu_power_watts == 250.0
        assert sample.gpu_index == 0

    def test_default_gpu_index(self):
        sample = PowerSample(timestamp=1.0, gpu_power_watts=100.0)
        assert sample.gpu_index == 0


class TestPowerStats:
    def test_defaults(self):
        stats = PowerStats()
        assert stats.avg_power_watts == 0.0
        assert stats.peak_power_watts == 0.0
        assert stats.min_power_watts == 0.0
        assert stats.total_energy_kwh == 0.0
        assert stats.duration_seconds == 0.0
        assert stats.sample_count == 0


class TestPowerMonitorInit:
    def test_not_initialized_without_pynvml(self):
        """PowerMonitor gracefully handles missing pynvml."""
        monitor = PowerMonitor()
        # On a machine without NVIDIA GPU / pynvml, should not crash
        assert isinstance(monitor._initialized, bool)


class TestReadPowerWatts:
    def test_converts_milliwatts_to_watts(self):
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = MagicMock()
        mock_pynvml.nvmlDeviceGetPowerUsage.return_value = 250_000  # 250W in mW

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = PowerMonitor()
            monitor._initialized = True
            monitor._handle = mock_pynvml.nvmlDeviceGetHandleByIndex(0)
            watts = monitor.read_power_watts()

        assert watts == 250.0

    def test_returns_none_when_not_initialized(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        assert monitor.read_power_watts() is None


class TestGetStats:
    def test_no_samples_returns_empty_stats(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        stats = monitor.get_stats()
        assert stats.sample_count == 0
        assert stats.avg_power_watts == 0.0

    def test_with_samples_calculates_averages(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        monitor.samples = [
            PowerSample(timestamp=100.0, gpu_power_watts=200.0),
            PowerSample(timestamp=100.1, gpu_power_watts=300.0),
            PowerSample(timestamp=100.2, gpu_power_watts=250.0),
        ]
        stats = monitor.get_stats()
        assert stats.sample_count == 3
        assert abs(stats.avg_power_watts - 250.0) < 0.01

    def test_calculates_peak_and_min(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        monitor.samples = [
            PowerSample(timestamp=100.0, gpu_power_watts=150.0),
            PowerSample(timestamp=100.1, gpu_power_watts=350.0),
            PowerSample(timestamp=100.2, gpu_power_watts=200.0),
        ]
        stats = monitor.get_stats()
        assert stats.peak_power_watts == 350.0
        assert stats.min_power_watts == 150.0

    def test_calculates_energy(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        monitor.sample_interval_ms = 100  # 0.1s intervals
        monitor.samples = [
            PowerSample(timestamp=100.0, gpu_power_watts=300.0),
            PowerSample(timestamp=100.1, gpu_power_watts=300.0),
        ]
        stats = monitor.get_stats()
        # Energy = 2 samples * 300W * 0.1s = 60 joules
        # 60 J / 3_600_000 = 1.667e-5 kWh
        assert stats.total_energy_kwh > 0
        assert abs(stats.total_energy_kwh - (60.0 / 3_600_000)) < 1e-10

    def test_calculates_duration(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        monitor.samples = [
            PowerSample(timestamp=100.0, gpu_power_watts=250.0),
            PowerSample(timestamp=100.5, gpu_power_watts=250.0),
            PowerSample(timestamp=101.0, gpu_power_watts=250.0),
        ]
        stats = monitor.get_stats()
        assert abs(stats.duration_seconds - 1.0) < 0.01


class TestIsAvailable:
    def test_is_available_when_initialized(self):
        monitor = PowerMonitor()
        monitor._initialized = True
        assert monitor.is_available is True

    def test_not_available_when_not_initialized(self):
        monitor = PowerMonitor()
        monitor._initialized = False
        assert monitor.is_available is False


class TestContextManager:
    def test_context_manager_start_stop(self):
        monitor = PowerMonitor()
        monitor._initialized = False

        with (
            patch.object(monitor, "start") as mock_start,
            patch.object(monitor, "stop") as mock_stop,
            monitor,
        ):
            pass

        mock_start.assert_called_once()
        mock_stop.assert_called_once()
