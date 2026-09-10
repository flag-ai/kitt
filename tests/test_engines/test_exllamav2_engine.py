"""Tests for ExLlamaV2 engine."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.exllamav2_engine import ExLlamaV2Engine
from kitt.engines.image_resolver import clear_cache


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    clear_cache()
    yield
    clear_cache()


class TestExLlamaV2EngineMetadata:
    def test_name(self):
        assert ExLlamaV2Engine.name() == "exllamav2"

    def test_supported_formats(self):
        formats = ExLlamaV2Engine.supported_formats()
        assert "gptq" in formats
        assert "exl2" in formats
        assert "gguf" in formats

    def test_default_image(self):
        assert "exllamav2" in ExLlamaV2Engine.default_image()

    def test_default_port(self):
        assert ExLlamaV2Engine.default_port() == 8082

    def test_health_endpoint(self):
        assert ExLlamaV2Engine.health_endpoint() == "/health"


class TestExLlamaV2EngineInitialize:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_starts_container(self, mock_run, mock_wait, mock_cc):
        engine = ExLlamaV2Engine()
        engine.initialize("/models/gptq-model", {})

        mock_run.assert_called_once()
        mock_wait.assert_called_once()
        assert engine._container_id == "container123"

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_with_max_seq_len(self, mock_run, mock_wait, mock_cc):
        engine = ExLlamaV2Engine()
        engine.initialize("/models/gptq-model", {"max_seq_len": 8192})

        config = mock_run.call_args[0][0]
        assert "--max-seq-len" in config.command_args
        assert "8192" in config.command_args


class TestExLlamaV2EngineGenerate:
    @patch("kitt.engines.openai_compat.parse_openai_result")
    @patch("kitt.engines.openai_compat.openai_generate")
    @patch("kitt.collectors.gpu_stats.GPUMemoryTracker")
    def test_generate_calls_openai_api(self, mock_tracker_cls, mock_gen, mock_parse):
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value.__enter__ = lambda s: mock_tracker
        mock_tracker_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_gen.return_value = {"choices": [{"text": "hello"}]}
        mock_parse.return_value = MagicMock()

        engine = ExLlamaV2Engine()
        engine._base_url = "http://localhost:8082"
        engine._model_name = "/models/gptq-model"

        engine.generate("Test prompt", temperature=0.5)
        mock_gen.assert_called_once()
        mock_parse.assert_called_once()


class TestExLlamaV2EngineCleanup:
    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_stops_container(self, mock_stop):
        engine = ExLlamaV2Engine()
        engine._container_id = "abc123"
        engine.cleanup()
        mock_stop.assert_called_once_with("abc123")
        assert engine._container_id is None
