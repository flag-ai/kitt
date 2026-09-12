"""Tests for SSHConnection — all tests mock subprocess.run."""

import subprocess
from unittest.mock import MagicMock, patch

from kitt.remote.ssh_connection import SSHConnection


class TestTarget:
    def test_target_with_user(self):
        conn = SSHConnection(host="gpu-server", user="kitt")
        assert conn.target == "kitt@gpu-server"

    def test_target_without_user(self):
        conn = SSHConnection(host="gpu-server")
        assert conn.target == "gpu-server"

    def test_target_with_empty_user(self):
        conn = SSHConnection(host="gpu-server", user=None)
        assert conn.target == "gpu-server"


class TestSSHBaseArgs:
    def test_includes_port_and_batch_mode(self):
        conn = SSHConnection(host="gpu-server", port=22)
        args = conn._ssh_base_args()
        assert args[0] == "ssh"
        assert "-o" in args
        assert "BatchMode=yes" in args
        assert "StrictHostKeyChecking=yes" in args
        assert "-p" in args
        port_idx = args.index("-p")
        assert args[port_idx + 1] == "22"

    def test_includes_ssh_key_when_provided(self):
        conn = SSHConnection(host="gpu-server", ssh_key="/home/user/.ssh/id_rsa")
        args = conn._ssh_base_args()
        assert "-i" in args
        key_idx = args.index("-i")
        assert args[key_idx + 1] == "/home/user/.ssh/id_rsa"

    def test_no_ssh_key_when_not_provided(self):
        conn = SSHConnection(host="gpu-server")
        args = conn._ssh_base_args()
        assert "-i" not in args

    def test_custom_port(self):
        conn = SSHConnection(host="gpu-server", port=2222)
        args = conn._ssh_base_args()
        port_idx = args.index("-p")
        assert args[port_idx + 1] == "2222"


class TestCheckConnection:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="kitt-ok\n", stderr="")
        conn = SSHConnection(host="gpu-server", user="kitt")
        assert conn.check_connection() is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ssh"
        assert "kitt@gpu-server" in cmd
        assert "echo" in cmd
        assert "kitt-ok" in cmd

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_failure_nonzero_returncode(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Connection refused"
        )
        conn = SSHConnection(host="gpu-server", user="kitt")
        assert conn.check_connection() is False

    @patch(
        "kitt.remote.ssh_connection.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ssh", 10),
    )
    def test_timeout(self, mock_run):
        conn = SSHConnection(host="gpu-server", user="kitt")
        assert conn.check_connection(timeout=10) is False


class TestRunCommand:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Python 3.10.12\n", stderr=""
        )
        conn = SSHConnection(host="gpu-server", user="kitt")
        rc, out, err = conn.run_command("python3 --version")
        assert rc == 0
        assert "Python 3.10.12" in out
        assert err == ""
        cmd = mock_run.call_args[0][0]
        assert "kitt@gpu-server" in cmd
        assert "python3 --version" in cmd

    @patch(
        "kitt.remote.ssh_connection.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ssh", 30),
    )
    def test_timeout(self, mock_run):
        conn = SSHConnection(host="gpu-server", user="kitt")
        rc, out, err = conn.run_command("long-running-cmd", timeout=30)
        assert rc == -1
        assert out == ""
        assert err == "Command timed out"

    @patch(
        "kitt.remote.ssh_connection.subprocess.run",
        side_effect=FileNotFoundError,
    )
    def test_ssh_not_found(self, mock_run):
        conn = SSHConnection(host="gpu-server")
        rc, out, err = conn.run_command("echo hello")
        assert rc == -1
        assert err == "ssh not found"


class TestUploadFile:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        conn = SSHConnection(host="gpu-server", user="kitt", port=22)
        result = conn.upload_file("/tmp/config.yaml", "~/kitt-campaigns/config.yaml")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "scp"
        assert "BatchMode=yes" in cmd
        assert "-P" in cmd
        assert "/tmp/config.yaml" in cmd
        assert "kitt@gpu-server:~/kitt-campaigns/config.yaml" in cmd

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        conn = SSHConnection(host="gpu-server", user="kitt")
        result = conn.upload_file("/tmp/config.yaml", "~/remote/config.yaml")
        assert result is False


class TestDownloadFile:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        conn = SSHConnection(host="gpu-server", user="kitt")
        result = conn.download_file("~/results/metrics.json", "/tmp/metrics.json")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "scp"
        assert "kitt@gpu-server:~/results/metrics.json" in cmd
        assert "/tmp/metrics.json" in cmd


class TestDownloadDirectory:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        conn = SSHConnection(host="gpu-server", user="kitt")
        result = conn.download_directory("~/results/run1", "/tmp/run1")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "scp"
        assert "-r" in cmd
        assert "kitt@gpu-server:~/results/run1" in cmd
        assert "/tmp/run1" in cmd
