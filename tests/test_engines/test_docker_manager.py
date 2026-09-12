"""Tests for DockerManager — all tests mock subprocess.run."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.docker_manager import ContainerConfig, DockerManager


class TestIsDockerAvailable:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert DockerManager.is_docker_available() is True
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["docker", "info"]

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_not_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert DockerManager.is_docker_available() is False

    @patch("kitt.engines.docker_manager.subprocess.run", side_effect=FileNotFoundError)
    def test_docker_not_installed(self, mock_run):
        assert DockerManager.is_docker_available() is False

    @patch(
        "kitt.engines.docker_manager.subprocess.run",
        side_effect=subprocess.TimeoutExpired("docker", 10),
    )
    def test_timeout(self, mock_run):
        assert DockerManager.is_docker_available() is False


class TestImageExists:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert DockerManager.image_exists("vllm/vllm-openai:latest") is True
        assert "docker" in mock_run.call_args[0][0]

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_not_exists(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert DockerManager.image_exists("nonexistent:latest") is False


class TestPullImage:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_pull_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.pull_image("vllm/vllm-openai:latest")
        cmd = mock_run.call_args[0][0]
        assert "pull" in cmd
        assert "vllm/vllm-openai:latest" in cmd

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_pull_quiet(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.pull_image("vllm/vllm-openai:latest", quiet=True)
        cmd = mock_run.call_args[0][0]
        assert "-q" in cmd

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_pull_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not found")
        with pytest.raises(RuntimeError, match="Failed to pull"):
            DockerManager.pull_image("bad/image:latest")


class TestBuildImage:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.build_image(
            image="kitt/llama-cpp:spark",
            dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
            context_dir="/project/docker/llama_cpp",
        )
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "docker"
        assert "build" in cmd
        assert "-f" in cmd
        assert "/project/docker/llama_cpp/Dockerfile.spark" in cmd
        assert "-t" in cmd
        assert "kitt/llama-cpp:spark" in cmd
        assert cmd[-1] == "/project/docker/llama_cpp"

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_with_target(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.build_image(
            image="kitt/llama-cpp:spark",
            dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
            context_dir="/project/docker/llama_cpp",
            target="server",
        )
        cmd = mock_run.call_args[0][0]
        assert "--target" in cmd
        target_idx = cmd.index("--target")
        assert cmd[target_idx + 1] == "server"

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_with_build_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.build_image(
            image="kitt/llama-cpp:spark",
            dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
            context_dir="/project/docker/llama_cpp",
            build_args={"CUDA_VERSION": "13.1.1", "LLAMA_CPP_REF": "b1234"},
        )
        cmd = mock_run.call_args[0][0]
        assert "--build-arg" in cmd
        assert "CUDA_VERSION=13.1.1" in cmd
        assert "LLAMA_CPP_REF=b1234" in cmd

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="build error")
        with pytest.raises(RuntimeError, match="Failed to build"):
            DockerManager.build_image(
                image="kitt/llama-cpp:spark",
                dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
                context_dir="/project/docker/llama_cpp",
            )

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_timeout(self, mock_run):
        """Build uses 3600s timeout by default."""
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.build_image(
            image="kitt/llama-cpp:spark",
            dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
            context_dir="/project/docker/llama_cpp",
        )
        assert mock_run.call_args[1]["timeout"] == 3600

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_build_custom_timeout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.build_image(
            image="kitt/llama-cpp:spark",
            dockerfile="/project/docker/llama_cpp/Dockerfile.spark",
            context_dir="/project/docker/llama_cpp",
            timeout=7200,
        )
        assert mock_run.call_args[1]["timeout"] == 7200


class TestRunContainer:
    @patch("kitt.engines.docker_manager.time.time", return_value=1700000000)
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_basic_run(self, mock_run, mock_time):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        config = ContainerConfig(
            image="vllm/vllm-openai:latest",
            port=8000,
            container_port=8000,
        )
        container_id = DockerManager.run_container(config)
        assert container_id == "abc123"

        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "run" in cmd
        assert "-d" in cmd
        assert "--network" in cmd
        assert "host" in cmd
        assert "--gpus" in cmd
        assert "all" in cmd
        assert "vllm/vllm-openai:latest" in cmd

    @patch("kitt.engines.docker_manager.time.time", return_value=1700000000)
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_run_with_volumes_and_env(self, mock_run, mock_time):
        mock_run.return_value = MagicMock(returncode=0, stdout="def456\n")
        config = ContainerConfig(
            image="vllm/vllm-openai:latest",
            port=8000,
            container_port=8000,
            volumes={"/models/llama": "/models/llama"},
            env={"HF_TOKEN": "abc"},
            extra_args=["--shm-size=8g"],
            command_args=["--model", "/models/llama"],
        )
        container_id = DockerManager.run_container(config)
        assert container_id == "def456"

        cmd = mock_run.call_args[0][0]
        assert "-v" in cmd
        assert "/models/llama:/models/llama" in cmd
        assert "-e" in cmd
        assert "HF_TOKEN=abc" in cmd
        assert "--shm-size=8g" in cmd
        assert "--model" in cmd

    @patch("kitt.engines.docker_manager.time.time", return_value=1700000000)
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_run_no_gpu(self, mock_run, mock_time):
        mock_run.return_value = MagicMock(returncode=0, stdout="nogpu1\n")
        config = ContainerConfig(
            image="ollama/ollama:latest",
            port=11434,
            container_port=11434,
            gpu=False,
        )
        DockerManager.run_container(config)
        cmd = mock_run.call_args[0][0]
        assert "--gpus" not in cmd

    @patch("kitt.engines.docker_manager.time.time", return_value=1700000000)
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_run_failure(self, mock_run, mock_time):
        mock_run.return_value = MagicMock(returncode=1, stderr="error starting")
        config = ContainerConfig(
            image="bad:latest",
            port=8000,
            container_port=8000,
        )
        with pytest.raises(RuntimeError, match="Failed to start"):
            DockerManager.run_container(config)


class TestStopContainer:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_stop_and_remove(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        DockerManager.stop_container("abc123")
        assert mock_run.call_count == 2
        stop_cmd = mock_run.call_args_list[0][0][0]
        rm_cmd = mock_run.call_args_list[1][0][0]
        assert "stop" in stop_cmd
        assert "rm" in rm_cmd


class TestContainerLogs:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_get_logs(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="log output\n", stderr=""
        )
        logs = DockerManager.container_logs("abc123", tail=20)
        assert "log output" in logs
        cmd = mock_run.call_args[0][0]
        assert "--tail" in cmd
        assert "20" in cmd


class TestWaitForHealthy:
    @patch("kitt.engines.docker_manager.time.sleep")
    @patch("kitt.engines.docker_manager.urllib.request.urlopen")
    def test_healthy_immediately(self, mock_urlopen, mock_sleep):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = DockerManager.wait_for_healthy("http://localhost:8000/health")
        assert result is True
        mock_sleep.assert_not_called()

    @patch("kitt.engines.docker_manager.time.monotonic")
    @patch("kitt.engines.docker_manager.time.sleep")
    @patch("kitt.engines.docker_manager.urllib.request.urlopen")
    def test_healthy_after_retries(self, mock_urlopen, mock_sleep, mock_monotonic):
        # Simulate: first call fails, second succeeds
        # monotonic: start=0, check=0 (< deadline 300), poll fails, sleep,
        # check=5 (< deadline 300), poll succeeds
        mock_monotonic.side_effect = [0, 0, 5, 5]

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [
            urllib_error(),
            mock_response,
        ]

        result = DockerManager.wait_for_healthy(
            "http://localhost:8000/health", timeout=300
        )
        assert result is True

    @patch("kitt.engines.docker_manager.time.monotonic")
    @patch("kitt.engines.docker_manager.time.sleep")
    @patch("kitt.engines.docker_manager.urllib.request.urlopen")
    def test_timeout_raises(self, mock_urlopen, mock_sleep, mock_monotonic):
        # First call sets deadline (0 + 10 = 10), second call is past deadline
        mock_monotonic.side_effect = [0, 999]
        mock_urlopen.side_effect = urllib_error()

        with pytest.raises(RuntimeError, match="failed to become healthy"):
            DockerManager.wait_for_healthy("http://localhost:8000/health", timeout=10)


class TestExecInContainer:
    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_exec_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="pulled model\n", stderr=""
        )
        result = DockerManager.exec_in_container("abc123", ["ollama", "pull", "llama3"])
        assert result.returncode == 0
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "exec", "abc123", "ollama", "pull", "llama3"]

    @patch("kitt.engines.docker_manager.subprocess.run")
    def test_exec_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="command not found"
        )
        with pytest.raises(RuntimeError, match="docker exec failed"):
            DockerManager.exec_in_container("abc123", ["bad", "cmd"])


def urllib_error():
    """Helper to create a URLError for mocking."""
    import urllib.error

    return urllib.error.URLError("Connection refused")
