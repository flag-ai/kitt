"""Tests for engine base classes."""

from datetime import datetime
from unittest.mock import patch

import pytest

from kitt.engines.base import (
    EngineDiagnostics,
    GenerationMetrics,
    GenerationResult,
    InferenceEngine,
)
from kitt.engines.image_resolver import clear_cache


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    clear_cache()
    yield
    clear_cache()


class TestGenerationMetrics:
    def test_creation(self):
        metrics = GenerationMetrics(
            ttft_ms=50.0,
            tps=30.0,
            total_latency_ms=1000.0,
            gpu_memory_peak_gb=4.5,
            gpu_memory_avg_gb=3.8,
            timestamp=datetime.now(),
        )
        assert metrics.ttft_ms == 50.0
        assert metrics.tps == 30.0
        assert metrics.total_latency_ms == 1000.0


class TestGenerationResult:
    def test_creation(self):
        metrics = GenerationMetrics(
            ttft_ms=50.0,
            tps=30.0,
            total_latency_ms=1000.0,
            gpu_memory_peak_gb=4.5,
            gpu_memory_avg_gb=3.8,
            timestamp=datetime.now(),
        )
        result = GenerationResult(
            output="Hello world",
            metrics=metrics,
            prompt_tokens=10,
            completion_tokens=5,
        )
        assert result.output == "Hello world"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5


class TestEngineDiagnostics:
    def test_creation_defaults(self):
        diag = EngineDiagnostics(available=True, image="vllm/vllm-openai:latest")
        assert diag.available is True
        assert diag.image == "vllm/vllm-openai:latest"
        assert diag.error is None
        assert diag.guidance is None

    def test_creation_full(self):
        diag = EngineDiagnostics(
            available=False,
            image="vllm/vllm-openai:latest",
            error="Docker image not pulled",
            guidance="kitt engines setup vllm",
        )
        assert diag.available is False
        assert diag.error == "Docker image not pulled"
        assert diag.guidance == "kitt engines setup vllm"


def _make_concrete_engine():
    """Create a minimal concrete subclass for testing."""

    class DummyEngine(InferenceEngine):
        @classmethod
        def name(cls):
            return "dummy"

        @classmethod
        def supported_formats(cls):
            return ["test"]

        @classmethod
        def default_image(cls):
            return "dummy/dummy:latest"

        @classmethod
        def default_port(cls):
            return 9999

        @classmethod
        def container_port(cls):
            return 9999

        @classmethod
        def health_endpoint(cls):
            return "/health"

        def initialize(self, model_path, config):
            pass

        def generate(self, prompt, **kwargs):
            pass

    return DummyEngine


class TestInferenceEngineABC:
    def test_cannot_instantiate_directly(self):
        """InferenceEngine cannot be instantiated directly."""
        with pytest.raises(TypeError):
            InferenceEngine()

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_is_available_true(self, mock_avail, mock_exists, mock_cc):
        DummyEngine = _make_concrete_engine()
        assert DummyEngine.is_available() is True

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=False,
    )
    def test_is_available_no_docker(self, mock_avail, mock_cc):
        DummyEngine = _make_concrete_engine()
        assert DummyEngine.is_available() is False

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_is_available_no_image(self, mock_avail, mock_exists, mock_cc):
        DummyEngine = _make_concrete_engine()
        assert DummyEngine.is_available() is False

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_available(self, mock_avail, mock_exists, mock_cc):
        DummyEngine = _make_concrete_engine()
        diag = DummyEngine.diagnose()
        assert diag.available is True
        assert diag.image == "dummy/dummy:latest"
        assert diag.error is None

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=False,
    )
    def test_diagnose_no_docker(self, mock_avail, mock_cc):
        DummyEngine = _make_concrete_engine()
        diag = DummyEngine.diagnose()
        assert diag.available is False
        assert "Docker is not installed" in diag.error
        assert "docs.docker.com" in diag.guidance

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_no_image(self, mock_avail, mock_exists, mock_cc):
        DummyEngine = _make_concrete_engine()
        diag = DummyEngine.diagnose()
        assert diag.available is False
        assert "not pulled" in diag.error
        assert "kitt engines setup" in diag.guidance

    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_stops_container(self, mock_stop):
        DummyEngine = _make_concrete_engine()
        engine = DummyEngine()
        engine._container_id = "abc123"
        engine.cleanup()
        mock_stop.assert_called_once_with("abc123")
        assert engine._container_id is None

    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_no_container(self, mock_stop):
        DummyEngine = _make_concrete_engine()
        engine = DummyEngine()
        engine.cleanup()  # Should not raise
        mock_stop.assert_not_called()


class TestValidateModel:
    def test_compatible_format(self, tmp_path):
        """validate_model returns None for compatible format."""

        class GGUFEngine(InferenceEngine):
            @classmethod
            def name(cls):
                return "test_gguf"

            @classmethod
            def supported_formats(cls):
                return ["gguf"]

            @classmethod
            def default_image(cls):
                return "test:latest"

            @classmethod
            def default_port(cls):
                return 9999

            @classmethod
            def container_port(cls):
                return 9999

            @classmethod
            def health_endpoint(cls):
                return "/health"

            def initialize(self, model_path, config):
                pass

            def generate(self, prompt, **kwargs):
                pass

        gguf_file = tmp_path / "model.gguf"
        gguf_file.write_bytes(b"\x00" * 100)
        assert GGUFEngine.validate_model(str(gguf_file)) is None

    def test_incompatible_format(self, tmp_path):
        """validate_model returns error for incompatible format."""

        class GGUFEngine(InferenceEngine):
            @classmethod
            def name(cls):
                return "test_gguf2"

            @classmethod
            def supported_formats(cls):
                return ["gguf"]

            @classmethod
            def default_image(cls):
                return "test:latest"

            @classmethod
            def default_port(cls):
                return 9999

            @classmethod
            def container_port(cls):
                return 9999

            @classmethod
            def health_endpoint(cls):
                return "/health"

            def initialize(self, model_path, config):
                pass

            def generate(self, prompt, **kwargs):
                pass

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)
        error = GGUFEngine.validate_model(str(model_dir))
        assert error is not None
        assert "safetensors" in error
