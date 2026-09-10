"""Tests for MLX engine."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.mlx_engine import MLXEngine


class TestMLXEngineMetadata:
    def test_name(self):
        assert MLXEngine.name() == "mlx"

    def test_supported_formats(self):
        assert "mlx" in MLXEngine.supported_formats()
        assert "safetensors" in MLXEngine.supported_formats()

    def test_default_image_empty(self):
        """MLX has no Docker image."""
        assert MLXEngine.default_image() == ""

    def test_default_port_zero(self):
        """MLX has no network port."""
        assert MLXEngine.default_port() == 0


class TestMLXEngineAvailability:
    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", True)
    @patch("platform.system", return_value="Darwin")
    def test_available_on_macos(self, mock_sys):
        assert MLXEngine.is_available() is True

    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", True)
    @patch("platform.system", return_value="Linux")
    def test_not_available_on_linux(self, mock_sys):
        assert MLXEngine.is_available() is False

    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", False)
    @patch("platform.system", return_value="Darwin")
    def test_not_available_without_mlx(self, mock_sys):
        assert MLXEngine.is_available() is False


class TestMLXEngineDiagnose:
    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", True)
    @patch("platform.system", return_value="Darwin")
    def test_diagnose_available(self, mock_sys):
        diag = MLXEngine.diagnose()
        assert diag.available is True

    @patch("platform.system", return_value="Linux")
    def test_diagnose_wrong_platform(self, mock_sys):
        diag = MLXEngine.diagnose()
        assert diag.available is False
        assert "macOS" in diag.error

    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", False)
    @patch("platform.system", return_value="Darwin")
    def test_diagnose_mlx_not_installed(self, mock_sys):
        diag = MLXEngine.diagnose()
        assert diag.available is False
        assert "mlx-lm" in diag.error


class TestMLXEngineInitialize:
    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", False)
    def test_initialize_without_mlx(self):
        engine = MLXEngine()
        with pytest.raises(RuntimeError, match="mlx-lm is not installed"):
            engine.initialize("/models/test", {})

    @patch("kitt.engines.mlx_engine.mlx_lm", create=True)
    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", True)
    def test_initialize_loads_model(self, mock_mlx):
        mock_mlx.load.return_value = (MagicMock(), MagicMock())
        engine = MLXEngine()
        engine.initialize("/models/test-model", {})
        mock_mlx.load.assert_called_once_with("/models/test-model")
        assert engine._model is not None


class TestMLXEngineGenerate:
    @patch("kitt.engines.mlx_engine.mlx_lm", create=True)
    @patch("kitt.engines.mlx_engine.MLX_AVAILABLE", True)
    def test_generate(self, mock_mlx):
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.side_effect = [
            [1, 2, 3],  # prompt tokens
            [4, 5, 6, 7],  # completion tokens
        ]
        mock_mlx.generate.return_value = "Generated text"

        engine = MLXEngine()
        engine._model = mock_model
        engine._tokenizer = mock_tokenizer

        result = engine.generate("Hello", max_tokens=100)
        assert result.output == "Generated text"
        assert result.prompt_tokens == 3
        assert result.completion_tokens == 4

    def test_generate_not_initialized(self):
        engine = MLXEngine()
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.generate("test")


class TestMLXEngineCleanup:
    def test_cleanup_releases_model(self):
        engine = MLXEngine()
        engine._model = MagicMock()
        engine._tokenizer = MagicMock()
        engine.cleanup()
        assert engine._model is None
        assert engine._tokenizer is None
