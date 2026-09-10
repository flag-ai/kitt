"""Tests for RemoteCampaignExecutor — mock SSHConnection via subprocess.run."""

from unittest.mock import MagicMock, patch

from kitt.remote.executor import RemoteCampaignExecutor
from kitt.remote.host_config import HostConfig


def _make_host_config(**kwargs):
    """Create a HostConfig with sensible defaults."""
    defaults = dict(
        name="dgx01",
        hostname="gpu-server",
        user="kitt",
        port=22,
        kitt_path="~/.local/bin/kitt",
        storage_path="~/kitt-results",
    )
    defaults.update(kwargs)
    return HostConfig(**defaults)


class TestInit:
    def test_creates_connection_from_config(self):
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        assert executor.conn.host == "gpu-server"
        assert executor.conn.user == "kitt"
        assert executor.conn.port == 22

    def test_empty_user_becomes_none(self):
        config = _make_host_config(user="")
        executor = RemoteCampaignExecutor(config)
        assert executor.conn.user is None

    def test_empty_ssh_key_becomes_none(self):
        config = _make_host_config(ssh_key="")
        executor = RemoteCampaignExecutor(config)
        assert executor.conn.ssh_key is None


class TestUploadConfig:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        result = executor.upload_config("/tmp/campaign.yaml")
        assert result is not None
        assert "campaign.yaml" in result
        # Should have called run_command for mkdir -p and upload_file
        assert mock_run.call_count >= 2

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        # mkdir succeeds, scp fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # mkdir
            MagicMock(returncode=1, stdout="", stderr="scp error"),  # scp
        ]
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        result = executor.upload_config("/tmp/campaign.yaml")
        assert result is None


class TestStartCampaign:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="12345\n", stderr="")
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        result = executor.start_campaign("~/kitt-campaigns/campaign.yaml")
        assert result is True
        cmd = mock_run.call_args[0][0]
        full_cmd = " ".join(cmd)
        assert "nohup" in full_cmd

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_dry_run_passes_flag(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="12345\n", stderr="")
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        executor.start_campaign("~/kitt-campaigns/campaign.yaml", dry_run=True)
        cmd = mock_run.call_args[0][0]
        # The command string is passed as the last arg to ssh
        ssh_command = cmd[-1]
        assert "--dry-run" in ssh_command

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="command failed"
        )
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        result = executor.start_campaign("~/kitt-campaigns/campaign.yaml")
        assert result is False


class TestCheckStatus:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_running_when_process_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="12345\n", stderr="")
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        status = executor.check_status()
        assert status == "running"

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_unknown_when_no_process(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=""),  # pgrep
            MagicMock(returncode=1, stdout="", stderr=""),  # kitt campaign status
        ]
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        status = executor.check_status()
        assert status == "unknown"


class TestGetLogs:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_tail_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Running benchmark 5/10\nProgress: 50%\n",
            stderr="",
        )
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        logs = executor.get_logs(tail=50)
        assert "Running benchmark" in logs
        cmd = mock_run.call_args[0][0]
        ssh_command = cmd[-1]
        assert "tail" in ssh_command
        assert "50" in ssh_command

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_default_message_when_no_log(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="No such file"
        )
        config = _make_host_config()
        executor = RemoteCampaignExecutor(config)
        logs = executor.get_logs()
        assert logs == "No logs available."
