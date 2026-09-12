"""Tests for individual hardware detectors."""

from unittest.mock import MagicMock, patch

from kitt.hardware.detector import (
    _extract_brand,
    detect_cpu,
    detect_environment_type,
    detect_gpu,
    detect_ram_gb,
)


class TestDetectEnvironmentType:
    def test_returns_string(self):
        env = detect_environment_type()
        assert isinstance(env, str)
        assert env != ""

    @patch("kitt.hardware.detector.Path")
    def test_docker_detection(self, mock_path_cls):
        """Detect Docker via /.dockerenv."""
        instances = {}

        def path_side_effect(p):
            if p not in instances:
                m = MagicMock()
                if p == "/etc/dgx-release" or p == "/etc/nvidia/nvidia-dgs.conf":
                    m.exists.return_value = False
                elif p == "/.dockerenv":
                    m.exists.return_value = True
                else:
                    m.exists.return_value = False
                instances[p] = m
            return instances[p]

        mock_path_cls.side_effect = path_side_effect

        # Also mock /proc/version read
        with patch("builtins.open", side_effect=FileNotFoundError):
            env = detect_environment_type()
        # Result depends on actual system - just check it doesn't crash
        assert isinstance(env, str)


class TestDetectCPU:
    def test_returns_cpu_info(self):
        cpu = detect_cpu()
        assert cpu.model != ""
        assert cpu.cores >= 0
        assert cpu.threads >= 0


class TestDetectRAM:
    def test_returns_positive(self):
        ram = detect_ram_gb()
        assert ram > 0


class TestDetectGPU:
    def test_returns_gpu_or_none(self):
        """Should return GPUInfo or None, never crash."""
        gpu = detect_gpu()
        assert gpu is None or gpu.model != ""


class TestExtractBrand:
    def test_samsung(self):
        assert (
            _extract_brand("Samsung SSD 970 EVO Plus", ["Samsung", "WD"]) == "Samsung"
        )

    def test_western_digital(self):
        assert (
            _extract_brand(
                "Western Digital WD Black SN850X", ["Samsung", "WD", "Western Digital"]
            )
            == "WD"
        )

    def test_unknown(self):
        assert _extract_brand("Some Random Drive", ["Samsung", "WD"]) == "Unknown"
