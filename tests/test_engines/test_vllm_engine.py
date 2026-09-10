"""Tests for vLLM engine — Docker lifecycle and OpenAI API generation."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.image_resolver import clear_cache
from kitt.engines.vllm_engine import VLLMEngine


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    """Ensure image resolver cache is clean for each test."""
    clear_cache()
    yield
    clear_cache()


class TestVLLMEngineMetadata:
    def test_name(self):
        assert VLLMEngine.name() == "vllm"

    def test_supported_formats(self):
        assert "safetensors" in VLLMEngine.supported_formats()
        assert "pytorch" in VLLMEngine.supported_formats()

    def test_default_image(self):
        assert VLLMEngine.default_image() == "vllm/vllm-openai:latest"

    def test_default_port(self):
        assert VLLMEngine.default_port() == 8000

    def test_container_port(self):
        assert VLLMEngine.container_port() == 8000

    def test_health_endpoint(self):
        assert VLLMEngine.health_endpoint() == "/health"


class TestVLLMEngineAvailability:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_is_available_true(self, mock_avail, mock_exists, mock_cc):
        assert VLLMEngine.is_available() is True

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=False,
    )
    def test_is_available_no_docker(self, mock_avail, mock_cc):
        assert VLLMEngine.is_available() is False

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_available(self, mock_avail, mock_exists, mock_cc):
        diag = VLLMEngine.diagnose()
        assert diag.available is True
        assert diag.image == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_image_not_pulled(self, mock_avail, mock_exists, mock_cc):
        diag = VLLMEngine.diagnose()
        assert diag.available is False
        assert "not pulled" in diag.error
        assert "kitt engines setup vllm" in diag.guidance

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_diagnose_blackwell_uses_ngc_image(self, mock_avail, mock_exists, mock_cc):
        diag = VLLMEngine.diagnose()
        assert diag.available is True
        assert "nvcr.io/nvidia/vllm" in diag.image


class TestVLLMEngineInitialize:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_starts_container(self, mock_run, mock_wait, mock_cc):
        engine = VLLMEngine()
        engine.initialize("/models/llama-7b", {})

        mock_run.assert_called_once()
        config = mock_run.call_args[0][0]
        assert config.image == "vllm/vllm-openai:latest"
        assert "--model" in config.command_args
        mock_wait.assert_called_once()
        assert engine._container_id == "container123"

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_blackwell_uses_ngc_image(self, mock_run, mock_wait, mock_cc):
        engine = VLLMEngine()
        engine.initialize("/models/llama-7b", {})

        config = mock_run.call_args[0][0]
        assert config.image == "nvcr.io/nvidia/vllm:26.01-py3"
        # NGC images need 'vllm serve' prefix with positional model arg
        assert config.command_args[:3] == [
            "vllm",
            "serve",
            "/models/llama-7b",
        ]
        assert "--model" not in config.command_args

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_with_tensor_parallel(self, mock_run, mock_wait, mock_cc):
        engine = VLLMEngine()
        engine.initialize("/models/llama-7b", {"tensor_parallel_size": 2})

        config = mock_run.call_args[0][0]
        assert "--tensor-parallel-size" in config.command_args
        assert "2" in config.command_args

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_with_custom_port(self, mock_run, mock_wait, mock_cc):
        engine = VLLMEngine()
        engine.initialize("/models/llama-7b", {"port": 9000})

        health_url = mock_wait.call_args[0][0]
        assert "9000" in health_url

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_explicit_image_overrides_resolver(
        self, mock_run, mock_wait, mock_cc
    ):
        """User-provided image in config takes priority over resolved image."""
        engine = VLLMEngine()
        engine.initialize("/models/llama-7b", {"image": "custom/image:v1"})

        config = mock_run.call_args[0][0]
        assert config.image == "custom/image:v1"

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
        """Model name should include /models/ prefix for vLLM served_model_name."""
        engine = VLLMEngine()
        engine.initialize("/path/to/Qwen2.5-0.5B-Instruct", {})

        # Model name should be full container path for API calls
        assert engine._model_name == "/models/Qwen2.5-0.5B-Instruct"
        # Volume should mount to the same path
        config = mock_run.call_args[0][0]
        assert "/models/Qwen2.5-0.5B-Instruct" in config.volumes.values()

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.wait_for_healthy", return_value=True
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.run_container",
        return_value="container123",
    )
    def test_initialize_model_name_in_command_args(self, mock_run, mock_wait, mock_cc):
        """Command args should use the container path for --model flag."""
        engine = VLLMEngine()
        engine.initialize("/home/user/models/my-model", {})

        config = mock_run.call_args[0][0]
        # Standard image uses --model flag
        assert "--model" in config.command_args
        idx = config.command_args.index("--model")
        assert config.command_args[idx + 1] == "/models/my-model"


class TestVLLMEngineGenerate:
    @patch("kitt.engines.openai_compat.parse_openai_result")
    @patch("kitt.engines.openai_compat.openai_generate")
    @patch("kitt.collectors.gpu_stats.GPUMemoryTracker")
    def test_generate_calls_openai_api(self, mock_tracker_cls, mock_gen, mock_parse):
        mock_tracker = MagicMock()
        mock_tracker_cls.return_value.__enter__ = lambda s: mock_tracker
        mock_tracker_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_gen.return_value = {"choices": [{"text": "hi"}]}
        mock_parse.return_value = MagicMock()

        engine = VLLMEngine()
        engine._base_url = "http://localhost:8000"
        engine._model_name = "llama-7b"

        engine.generate("Hello", temperature=0.5, max_tokens=100)

        mock_gen.assert_called_once()
        assert mock_gen.call_args[1]["model"] == "llama-7b"
        assert mock_gen.call_args[1]["temperature"] == 0.5
        mock_parse.assert_called_once()


class TestVLLMEngineCleanup:
    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_stops_container(self, mock_stop):
        engine = VLLMEngine()
        engine._container_id = "abc123"
        engine.cleanup()
        mock_stop.assert_called_once_with("abc123")
        assert engine._container_id is None

    @patch("kitt.engines.docker_manager.DockerManager.stop_container")
    def test_cleanup_no_container(self, mock_stop):
        engine = VLLMEngine()
        engine.cleanup()
        mock_stop.assert_not_called()
