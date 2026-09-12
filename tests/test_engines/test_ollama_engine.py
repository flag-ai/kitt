"""Tests for Ollama engine — Docker lifecycle and model pulling."""

import json
from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.image_resolver import clear_cache
from kitt.engines.ollama_engine import OllamaEngine


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    clear_cache()
    yield
    clear_cache()


class TestOllamaEngineMetadata:
    def test_name(self):
        assert OllamaEngine.name() == "ollama"

    def test_supported_formats(self):
        assert "gguf" in OllamaEngine.supported_formats()

    def test_default_image(self):
        assert OllamaEngine.default_image() == "ollama/ollama:latest"

    def test_default_port(self):
        assert OllamaEngine.default_port() == 11434

    def test_container_port(self):
        assert OllamaEngine.container_port() == 11434

    def test_health_endpoint(self):
        assert OllamaEngine.health_endpoint() == "/api/tags"


class TestOllamaEngineAvailability:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_is_available_true(self, mock_avail, mock_exists, mock_cc):
        assert OllamaEngine.is_available() is True

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_image_not_pulled(self, mock_avail, mock_exists, mock_cc):
        diag = OllamaEngine.diagnose()
        assert diag.available is False
        assert "not pulled" in diag.error
        assert "kitt engines setup ollama" in diag.guidance


class TestOllamaEngineInitialize:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.exec_in_container")
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_starts_container_and_pulls_model(
        self, mock_run, mock_wait, mock_exec, mock_cc
    ):
        mock_exec.return_value = MagicMock(returncode=0)

        engine = OllamaEngine()
        engine.initialize("llama3", {})

        mock_run.assert_called_once()
        config = mock_run.call_args[0][0]
        assert config.image == "ollama/ollama:latest"
        mock_wait.assert_called_once()
        # Should pull the model inside the container
        mock_exec.assert_called_once_with("container123", ["ollama", "pull", "llama3"])

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.exec_in_container")
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_with_custom_port(self, mock_run, mock_wait, mock_exec, mock_cc):
        mock_exec.return_value = MagicMock(returncode=0)

        engine = OllamaEngine()
        engine.initialize("llama3", {"port": 12000})

        health_url = mock_wait.call_args[0][0]
        assert "12000" in health_url


class TestOllamaEngineGenerate:
    @patch("kitt.collectors.gpu_stats.GPUMemoryTracker")
    @patch("kitt.engines.ollama_engine.urllib.request.urlopen")
    def test_generate_calls_ollama_api(self, mock_urlopen, mock_tracker_cls):
        mock_tracker = MagicMock()
        mock_tracker.get_peak_memory_mb.return_value = 0.0
        mock_tracker.get_average_memory_mb.return_value = 0.0
        mock_tracker_cls.return_value.__enter__ = lambda s: mock_tracker
        mock_tracker_cls.return_value.__exit__ = MagicMock(return_value=False)

        response_data = {
            "response": "Generated text",
            "prompt_eval_count": 5,
            "eval_count": 10,
            "eval_duration": 500_000_000,  # 500ms in ns
            "prompt_eval_duration": 100_000_000,  # 100ms in ns
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        engine = OllamaEngine()
        engine._base_url = "http://localhost:11434"
        engine._model_name = "llama3"
        result = engine.generate("test prompt")

        assert result.output == "Generated text"
        assert result.prompt_tokens == 5
        assert result.completion_tokens == 10
        assert result.metrics.tps == 10 / 0.5  # 20 tps
        assert result.metrics.ttft_ms == 100.0


class TestOllamaEngineCleanup:
    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_stops_container(self, mock_stop):
        engine = OllamaEngine()
        engine._container_id = "abc123"
        engine.cleanup()
        mock_stop.assert_called_once_with("abc123")
        assert engine._container_id is None
