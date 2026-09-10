"""Tests for GPU stats collection (mocked since no GPU on dev machine)."""

from unittest.mock import MagicMock, patch

from kitt.collectors.gpu_stats import (
    GPUMemoryStats,
    GPUMemoryTracker,
    GPUMonitor,
)


class TestGPUMemoryStats:
    def test_creation(self):
        stats = GPUMemoryStats(
            used_mb=4096.0,
            free_mb=8192.0,
            total_mb=12288.0,
            utilization_percent=45.0,
        )
        assert stats.used_mb == 4096.0
        assert stats.total_mb == 12288.0


class TestGPUMonitor:
    def test_unavailable_gracefully(self):
        """GPUMonitor gracefully handles missing NVML."""
        monitor = GPUMonitor()
        # On a machine without NVIDIA GPU, should not crash
        stats = monitor.get_memory_stats()
        # Stats will be None if no GPU
        assert stats is None or isinstance(stats, GPUMemoryStats)

    def test_all_gpus_stats_empty_when_unavailable(self):
        monitor = GPUMonitor()
        if not monitor.is_available:
            assert monitor.get_all_gpus_stats() == []


class TestGPUMemoryTracker:
    def test_tracker_no_gpu(self):
        """Tracker works without GPU (returns zeros)."""
        tracker = GPUMemoryTracker(gpu_index=0)
        # Force the monitor to appear unavailable so we test the no-GPU path
        tracker.monitor._initialized = False
        with tracker:
            pass

        assert tracker.get_peak_memory_mb() == 0.0
        assert tracker.get_average_memory_mb() == 0.0
        assert tracker.get_min_memory_mb() == 0.0

    def test_tracker_with_mocked_samples(self):
        """Test tracker calculations with injected samples."""
        tracker = GPUMemoryTracker()
        tracker.samples = [
            GPUMemoryStats(
                used_mb=1000, free_mb=3000, total_mb=4000, utilization_percent=25
            ),
            GPUMemoryStats(
                used_mb=2000, free_mb=2000, total_mb=4000, utilization_percent=50
            ),
            GPUMemoryStats(
                used_mb=1500, free_mb=2500, total_mb=4000, utilization_percent=37
            ),
        ]
        assert tracker.get_peak_memory_mb() == 2000.0
        assert tracker.get_min_memory_mb() == 1000.0
        assert abs(tracker.get_average_memory_mb() - 1500.0) < 0.01


class TestHardwareCompatibility:
    """Tests for various hardware scenarios including edge cases."""

    def setup_method(self):
        """Reset class-level warning flag before each test."""
        GPUMonitor._stats_warned = False

    def teardown_method(self):
        """Reset class-level warning flag after each test."""
        GPUMonitor._stats_warned = False

    def test_unified_memory_system_memory_not_supported(self):
        """Test graceful handling when memory info is not supported (e.g., GB10)."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = MagicMock()
        mock_pynvml.NVMLError = Exception
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = Exception("Not Supported")

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = GPUMonitor()
            monitor._initialized = True
            stats = monitor.get_memory_stats(0)
            assert stats is None

    def test_utilization_not_supported_fallback(self):
        """Test fallback when utilization is not supported but memory is."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_handle = MagicMock()
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle

        # Memory works
        mock_mem = MagicMock()
        mock_mem.used = 4 * 1024 * 1024 * 1024  # 4GB
        mock_mem.free = 8 * 1024 * 1024 * 1024  # 8GB
        mock_mem.total = 12 * 1024 * 1024 * 1024  # 12GB
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mock_mem

        # Utilization fails
        mock_pynvml.NVMLError = Exception
        mock_pynvml.nvmlDeviceGetUtilizationRates.side_effect = Exception(
            "Not Supported"
        )

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = GPUMonitor()
            monitor._initialized = True
            stats = monitor.get_memory_stats(0)
            assert stats is not None
            assert stats.total_mb == 12288.0
            assert stats.utilization_percent == 0.0  # Fallback value

    def test_warning_only_logged_once(self):
        """Verify warning is only logged once per session (class-level flag)."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = MagicMock()
        mock_pynvml.NVMLError = Exception
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = Exception("Not Supported")

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor1 = GPUMonitor()
            monitor1._initialized = True
            monitor2 = GPUMonitor()
            monitor2._initialized = True

            # First call should set the flag
            assert GPUMonitor._stats_warned is False
            monitor1.get_memory_stats(0)
            assert GPUMonitor._stats_warned is True

            # Second monitor instance should not reset the flag
            monitor2.get_memory_stats(0)
            assert GPUMonitor._stats_warned is True

    def test_complete_nvml_success(self):
        """Test successful path with all NVML calls working."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_handle = MagicMock()
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle

        mock_mem = MagicMock()
        mock_mem.used = 2 * 1024 * 1024 * 1024
        mock_mem.free = 6 * 1024 * 1024 * 1024
        mock_mem.total = 8 * 1024 * 1024 * 1024
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mock_mem

        mock_util = MagicMock()
        mock_util.gpu = 75
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = mock_util
        mock_pynvml.NVMLError = Exception

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = GPUMonitor()
            monitor._initialized = True
            stats = monitor.get_memory_stats(0)
            assert stats is not None
            assert stats.used_mb == 2048.0
            assert stats.free_mb == 6144.0
            assert stats.total_mb == 8192.0
            assert stats.utilization_percent == 75

    def test_monitor_not_initialized_returns_none(self):
        """Monitor returns None when not initialized."""
        monitor = GPUMonitor()
        monitor._initialized = False
        assert monitor.get_memory_stats(0) is None

    def test_monitor_not_initialized_device_count_zero(self):
        """Device count is 0 when not initialized."""
        monitor = GPUMonitor()
        monitor._initialized = False
        assert monitor.get_device_count() == 0


class TestMultiGPUCompatibility:
    """Tests for multi-GPU scenarios."""

    def setup_method(self):
        GPUMonitor._stats_warned = False

    def teardown_method(self):
        GPUMonitor._stats_warned = False

    def test_multi_gpu_all_working(self):
        """Test get_all_gpus_stats with multiple working GPUs."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlDeviceGetCount.return_value = 2
        mock_pynvml.NVMLError = Exception

        mock_handles = [MagicMock(), MagicMock()]
        mock_pynvml.nvmlDeviceGetHandleByIndex.side_effect = mock_handles

        mock_mem1 = MagicMock(used=4 * 1024**3, free=4 * 1024**3, total=8 * 1024**3)
        mock_mem2 = MagicMock(used=6 * 1024**3, free=2 * 1024**3, total=8 * 1024**3)
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [mock_mem1, mock_mem2]

        mock_util = MagicMock(gpu=50)
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = mock_util

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = GPUMonitor()
            monitor._initialized = True
            all_stats = monitor.get_all_gpus_stats()
            assert len(all_stats) == 2
            assert all_stats[0].used_mb == 4096.0
            assert all_stats[1].used_mb == 6144.0

    def test_multi_gpu_partial_failure(self):
        """Test handling when some GPUs fail but others work."""
        import sys

        mock_pynvml = MagicMock()
        mock_pynvml.nvmlInit.return_value = None
        mock_pynvml.nvmlDeviceGetCount.return_value = 2
        mock_pynvml.NVMLError = Exception

        mock_handles = [MagicMock(), MagicMock()]
        mock_pynvml.nvmlDeviceGetHandleByIndex.side_effect = mock_handles

        # First GPU works, second fails
        mock_mem = MagicMock(used=4 * 1024**3, free=4 * 1024**3, total=8 * 1024**3)
        mock_pynvml.nvmlDeviceGetMemoryInfo.side_effect = [
            mock_mem,
            Exception("GPU 1 failed"),
        ]
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = MagicMock(gpu=50)

        with patch.dict(sys.modules, {"pynvml": mock_pynvml}):
            monitor = GPUMonitor()
            monitor._initialized = True
            all_stats = monitor.get_all_gpus_stats()
            # Should return stats for working GPUs only
            assert len(all_stats) == 1
            assert all_stats[0].used_mb == 4096.0
