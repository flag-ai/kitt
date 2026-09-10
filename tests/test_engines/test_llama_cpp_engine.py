"""Tests for llama.cpp engine — Docker lifecycle and OpenAI API generation."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.image_resolver import clear_cache
from kitt.engines.llama_cpp_engine import LlamaCppEngine


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    clear_cache()
    yield
    clear_cache()


class TestLlamaCppEngineMetadata:
    def test_name(self):
        assert LlamaCppEngine.name() == "llama_cpp"

    def test_supported_formats(self):
        assert "gguf" in LlamaCppEngine.supported_formats()

    def test_default_image(self):
        assert (
            LlamaCppEngine.default_image() == "ghcr.io/ggml-org/llama.cpp:server-cuda"
        )

    def test_default_port(self):
        assert LlamaCppEngine.default_port() == 8081

    def test_container_port(self):
        assert LlamaCppEngine.container_port() == 8080

    def test_health_endpoint(self):
        assert LlamaCppEngine.health_endpoint() == "/health"


class TestLlamaCppEngineAvailability:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_is_available_true(self, mock_avail, mock_exists, mock_cc):
        assert LlamaCppEngine.is_available() is True

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_image_not_pulled(self, mock_avail, mock_exists, mock_cc):
        diag = LlamaCppEngine.diagnose()
        assert diag.available is False
        assert "not pulled" in diag.error
        assert "kitt engines setup llama_cpp" in diag.guidance


class TestLlamaCppEngineInitialize:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_starts_container(self, mock_run, mock_wait, mock_cc):
        engine = LlamaCppEngine()
        engine.initialize("/models/model.gguf", {})

        mock_run.assert_called_once()
        config = mock_run.call_args[0][0]
        assert config.image == "ghcr.io/ggml-org/llama.cpp:server-cuda"
        assert "-m" in config.command_args
        mock_wait.assert_called_once()

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_uses_host_port_for_server(self, mock_run, mock_wait, mock_cc):
        """With --network host, server must listen on the host port."""
        engine = LlamaCppEngine()
        engine.initialize("/models/model.gguf", {})

        config = mock_run.call_args[0][0]
        # --port must use the host port (8081), not container_port (8080)
        assert "--port" in config.command_args
        idx = config.command_args.index("--port")
        assert config.command_args[idx + 1] == "8081"

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_with_gpu_layers(self, mock_run, mock_wait, mock_cc):
        engine = LlamaCppEngine()
        engine.initialize("/models/model.gguf", {"n_gpu_layers": 32, "n_ctx": 8192})

        config = mock_run.call_args[0][0]
        assert "--n-gpu-layers" in config.command_args
        assert "32" in config.command_args
        assert "-c" in config.command_args
        assert "8192" in config.command_args

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_sets_model_name_with_container_path(
        self, mock_run, mock_wait, mock_cc
    ):
        """Model name should include /models/ prefix for API consistency."""
        engine = LlamaCppEngine()
        engine.initialize("/path/to/my-model.gguf", {})

        # Model name should be full container path
        assert engine._model_name == "/models/my-model.gguf"
        # Command args should use the same path
        config = mock_run.call_args[0][0]
        assert "-m" in config.command_args
        idx = config.command_args.index("-m")
        assert config.command_args[idx + 1] == "/models/my-model.gguf"


class TestLlamaCppEngineGenerate:
    @patch("kitt.engines.openai_compat.parse_openai_result")
    @patch("kitt.engines.openai_compat.openai_generate")
    @patch("kitt.collectors.gpu_stats.GPUMemoryTracker")
    def test_generate_calls_openai_api(self, mock_tracker_cls, mock_gen, mock_parse):
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value.__enter__ = lambda s: mock_tracker
        mock_tracker_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_gen.return_value = {"choices": [{"text": "generated"}]}
        mock_parse.return_value = MagicMock()

        engine = LlamaCppEngine()
        engine._base_url = "http://localhost:8081"
        engine._model_name = "/models/model.gguf"

        engine.generate("Hello", temperature=0.7, top_k=40)

        mock_gen.assert_called_once()
        assert mock_gen.call_args[1]["model"] == "/models/model.gguf"
        assert mock_gen.call_args[1]["top_k"] == 40
        mock_parse.assert_called_once()


class TestLlamaCppEngineCleanup:
    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_stops_container(self, mock_stop):
        engine = LlamaCppEngine()
        engine._container_id = "abc123"
        engine.cleanup()
        mock_stop.assert_called_once_with("abc123")
        assert engine._container_id is None
