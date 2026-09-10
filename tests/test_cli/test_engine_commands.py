"""Tests for engine CLI commands (setup, check, list) — Docker-only."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kitt.cli.engine_commands import engines
from kitt.engines.base import EngineDiagnostics
from kitt.engines.image_resolver import clear_cache


@pytest.fixture(autouse=True)
def _reset_image_resolver():
    clear_cache()
    yield
    clear_cache()


class TestSetupEngine:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.pull_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_pulls_image(self, mock_avail, mock_pull, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "vllm"])
        assert result.exit_code == 0
        assert "ready" in result.output
        mock_pull.assert_called_once_with("vllm/vllm-openai:latest")

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_dry_run(self, mock_avail, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "--dry-run", "vllm"])
        assert result.exit_code == 0
        assert "would run" in result.output
        assert "docker pull" in result.output
        assert "vllm/vllm-openai" in result.output
        assert "Dry run" in result.output

    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=False,
    )
    def test_setup_no_docker(self, mock_avail):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "vllm"])
        assert result.exit_code != 0
        assert "Docker is not installed" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.docker_manager.DockerManager.pull_image",
        side_effect=RuntimeError("network error"),
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_pull_failure(self, mock_avail, mock_pull, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "vllm"])
        assert result.exit_code != 0
        assert "network error" in result.output

    def test_setup_unknown_engine(self):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.pull_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_ollama(self, mock_avail, mock_pull, mock_cc):
        """All engines are now supported by setup (not just vllm)."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "ollama"])
        assert result.exit_code == 0
        assert "ready" in result.output
        mock_pull.assert_called_once_with("ollama/ollama:latest")

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.pull_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_llama_cpp(self, mock_avail, mock_pull, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "llama_cpp"])
        assert result.exit_code == 0
        mock_pull.assert_called_once_with("ghcr.io/ggml-org/llama.cpp:server-cuda")

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.pull_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_vllm_blackwell_pulls_ngc(self, mock_avail, mock_pull, mock_cc):
        """On Blackwell hardware, setup pulls the NGC image for vLLM."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "vllm"])
        assert result.exit_code == 0
        mock_pull.assert_called_once_with("nvcr.io/nvidia/vllm:26.01-py3")


class TestSetupEngineBuild:
    """Tests for KITT-managed image builds (docker build path)."""

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch("kitt.engines.docker_manager.DockerManager.build_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_llama_cpp_blackwell_builds(
        self, mock_avail, mock_build, mock_exists, mock_cc, mock_arch
    ):
        """On x86_64 Blackwell, llama_cpp setup builds the spark image."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "llama_cpp"])
        assert result.exit_code == 0
        assert "Building" in result.output
        assert "ready" in result.output
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["image"] == "kitt/llama-cpp:spark"
        assert call_kwargs["target"] == "server"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_llama_cpp_blackwell_dry_run(self, mock_avail, mock_cc, mock_arch):
        """Dry run for x86_64 KITT-managed image shows docker build command."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "--dry-run", "llama_cpp"])
        assert result.exit_code == 0
        assert "would run" in result.output
        assert "docker build" in result.output
        assert "kitt/llama-cpp:spark" in result.output
        assert "--target server" in result.output
        assert "Dry run" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch("kitt.engines.docker_manager.DockerManager.build_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_skips_existing_build(
        self, mock_avail, mock_build, mock_exists, mock_cc
    ):
        """If KITT-managed image already exists, skip build."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "llama_cpp"])
        assert result.exit_code == 0
        assert "already exists" in result.output
        mock_build.assert_not_called()

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch("kitt.engines.docker_manager.DockerManager.build_image")
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_force_rebuild(self, mock_avail, mock_build, mock_exists, mock_cc):
        """--force-rebuild builds even if image exists."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "--force-rebuild", "llama_cpp"])
        assert result.exit_code == 0
        assert "Building" in result.output
        mock_build.assert_called_once()

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.build_image",
        side_effect=RuntimeError("build failed"),
    )
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_setup_build_failure(self, mock_avail, mock_build, mock_exists, mock_cc):
        """Build failure is reported to user."""
        runner = CliRunner()
        result = runner.invoke(engines, ["setup", "llama_cpp"])
        assert result.exit_code != 0
        assert "build failed" in result.output


class TestCheckEngine:
    def test_check_available(self):
        diag = EngineDiagnostics(
            available=True,
            image="vllm/vllm-openai:latest",
        )
        with patch("kitt.engines.vllm_engine.VLLMEngine.diagnose", return_value=diag):
            runner = CliRunner()
            result = runner.invoke(engines, ["check", "vllm"])
        assert "Available" in result.output
        assert "vllm/vllm-openai:latest" in result.output

    def test_check_not_available(self):
        diag = EngineDiagnostics(
            available=False,
            image="vllm/vllm-openai:latest",
            error="Docker image not pulled: vllm/vllm-openai:latest",
            guidance="Pull with: kitt engines setup vllm",
        )
        with patch("kitt.engines.vllm_engine.VLLMEngine.diagnose", return_value=diag):
            runner = CliRunner()
            result = runner.invoke(engines, ["check", "vllm"])
        assert "Not Available" in result.output
        assert "not pulled" in result.output
        assert "kitt engines setup vllm" in result.output

    def test_check_not_built(self):
        """KITT-managed image shows 'not built' message."""
        diag = EngineDiagnostics(
            available=False,
            image="kitt/llama-cpp:spark",
            error="Docker image not built: kitt/llama-cpp:spark",
            guidance="Build with: kitt engines setup llama_cpp",
        )
        with patch(
            "kitt.engines.llama_cpp_engine.LlamaCppEngine.diagnose", return_value=diag
        ):
            runner = CliRunner()
            result = runner.invoke(engines, ["check", "llama_cpp"])
        assert "Not Available" in result.output
        assert "not built" in result.output

    def test_check_no_docker(self):
        diag = EngineDiagnostics(
            available=False,
            image="vllm/vllm-openai:latest",
            error="Docker is not installed or not running",
            guidance="Install Docker: https://docs.docker.com/get-docker/",
        )
        with patch("kitt.engines.vllm_engine.VLLMEngine.diagnose", return_value=diag):
            runner = CliRunner()
            result = runner.invoke(engines, ["check", "vllm"])
        assert "Docker is not installed" in result.output

    def test_check_unknown_engine(self):
        runner = CliRunner()
        result = runner.invoke(engines, ["check", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestListEngines:
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_shows_all_engines(self, mock_avail, mock_exists, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        assert result.exit_code == 0
        assert "vllm" in result.output
        assert "llama_cpp" in result.output
        assert "ollama" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_shows_image_column(self, mock_avail, mock_exists, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        # Image names may be truncated by Rich table; check prefix is visible
        assert "vllm/vllm-" in result.output
        assert "ollama/oll" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_shows_status(self, mock_avail, mock_exists, mock_cc):
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        assert "Not Pulled" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_shows_source_column(self, mock_avail, mock_exists, mock_cc):
        """List shows Registry as source for non-Blackwell images."""
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        assert "Source" in result.output
        assert "Registry" in result.output

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=True)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_blackwell_shows_ngc_for_vllm(
        self, mock_avail, mock_exists, mock_cc, mock_arch
    ):
        """On x86_64 Blackwell, vLLM should show NGC and llama.cpp shows spark."""
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        # Rich table truncates long image names; check for visible prefix
        assert "nvcr.io/nv" in result.output
        # llama.cpp shows the KITT-managed spark image on x86_64
        assert "kitt/llama" in result.output
        # Other engines still show their default images
        assert "ollama/oll" in result.output

    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch("kitt.engines.docker_manager.DockerManager.image_exists", return_value=False)
    @patch(
        "kitt.engines.docker_manager.DockerManager.is_docker_available",
        return_value=True,
    )
    def test_list_blackwell_shows_build_source(self, mock_avail, mock_exists, mock_cc):
        """On Blackwell, KITT-managed images show Build source and Not Built status."""
        runner = CliRunner()
        result = runner.invoke(engines, ["list"])
        assert "Build" in result.output
        assert "Not Built" in result.output
