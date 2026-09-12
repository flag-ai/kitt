"""Tests for CUDA version detection.

check_cuda_compatibility() and CudaMismatchInfo have been removed since
all engines now run in Docker containers with their own CUDA runtimes.
detect_cuda_version() remains for hardware fingerprinting.
"""

from unittest.mock import MagicMock, patch

from kitt.hardware.detector import detect_cuda_version


class TestDetectCudaVersion:
    @patch("kitt.hardware.detector.subprocess.run")
    def test_detects_version(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="nvcc: NVIDIA (R) Cuda compiler driver\n"
            "Cuda compilation tools, release 13.0, V13.0.76\n",
        )
        result = detect_cuda_version()
        assert result == "13.0"

    @patch("kitt.hardware.detector.subprocess.run")
    def test_no_nvcc(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        result = detect_cuda_version()
        assert result is None

    @patch("kitt.hardware.detector.subprocess.run")
    def test_nvcc_fails(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = detect_cuda_version()
        assert result is None
