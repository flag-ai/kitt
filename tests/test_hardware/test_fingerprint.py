"""Tests for hardware fingerprinting."""

from kitt.hardware.detector import CPUInfo, GPUInfo, StorageInfo
from kitt.hardware.fingerprint import HardwareFingerprint, SystemInfo


class TestHardwareFingerprint:
    def test_format_fingerprint_full(self):
        info = SystemInfo(
            gpu=GPUInfo(model="NVIDIA RTX 5090", vram_gb=32, count=1),
            cpu=CPUInfo(model="AMD Ryzen 9 7950X", cores=16, threads=32),
            ram_gb=64,
            ram_type="DDR5",
            storage=StorageInfo(brand="Samsung", model="990 PRO", type="nvme"),
            cuda_version="12.6",
            driver_version="560.35.03",
            os="Linux-6.8.0",
            kernel="#1 SMP",
            environment_type="native_linux",
        )
        fp = HardwareFingerprint._format_fingerprint(info)
        assert "NVIDIA-RTX-5090-32GB" in fp
        assert "AMD-7950X-16c" in fp
        assert "64GB-DDR5" in fp
        assert "Samsung-990-PRO-NVME" in fp
        assert "CUDA-12.6" in fp
        assert "560.35.03" in fp
        assert "Linux-6.8.0" in fp

    def test_format_fingerprint_no_gpu(self):
        info = SystemInfo(
            gpu=None,
            cpu=CPUInfo(model="Intel i7-13700K", cores=16, threads=24),
            ram_gb=32,
            ram_type="DDR4",
            storage=StorageInfo(brand="Unknown", model="Unknown", type="unknown"),
            cuda_version=None,
            driver_version=None,
            os="Linux-6.8.0",
            kernel="#1 SMP",
            environment_type="native_linux",
        )
        fp = HardwareFingerprint._format_fingerprint(info)
        assert "NVIDIA" not in fp
        assert "CUDA" not in fp
        assert "Intel-i7-13700K-16c" in fp

    def test_format_fingerprint_multi_gpu(self):
        info = SystemInfo(
            gpu=GPUInfo(model="NVIDIA A100", vram_gb=80, count=4),
            cpu=CPUInfo(model="AMD EPYC 7763", cores=64, threads=128),
            ram_gb=512,
            ram_type="DDR4",
            storage=StorageInfo(brand="Intel", model="P5800X", type="nvme"),
            cuda_version="12.2",
            driver_version="535.129.03",
            os="Linux-5.15.0",
            kernel="#1 SMP",
            environment_type="dgx",
        )
        fp = HardwareFingerprint._format_fingerprint(info)
        assert "NVIDIA-A100-80GB-4x" in fp

    def test_detect_system_runs(self):
        """detect_system() should not crash regardless of environment."""
        info = HardwareFingerprint.detect_system()
        assert isinstance(info, SystemInfo)
        assert info.environment_type != ""
        assert info.cpu.model != ""

    def test_generate_runs(self):
        """generate() should return a non-empty string."""
        fp = HardwareFingerprint.generate()
        assert isinstance(fp, str)
        assert len(fp) > 0
