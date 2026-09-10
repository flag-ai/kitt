"""Tests for cron-based campaign scheduler."""

import json
from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.scheduler_cron import CronScheduler


@pytest.fixture
def scheduler(tmp_path):
    return CronScheduler(config_dir=tmp_path)


class TestSchedule:
    @patch("subprocess.run")
    def test_valid_cron_saves_config_file(self, mock_run, scheduler):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = scheduler.schedule(
            "/path/to/campaign.yaml", "0 2 * * *", campaign_id="nightly"
        )
        assert result is True

        config_file = scheduler.config_dir / "nightly.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["campaign_config"] == "/path/to/campaign.yaml"
        assert data["cron_expr"] == "0 2 * * *"
        assert data["schedule_id"] == "nightly"
        assert data["enabled"] is True

    def test_invalid_cron_returns_false(self, scheduler):
        result = scheduler.schedule("/path/to/campaign.yaml", "not-a-cron")
        assert result is False

    @patch("subprocess.run")
    def test_registers_in_crontab(self, mock_run, scheduler):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        scheduler.schedule("/path/to/campaign.yaml", "30 1 * * 0", campaign_id="weekly")

        # First call: crontab -l, Second call: crontab -
        assert mock_run.call_count == 2
        install_call = mock_run.call_args_list[1]
        assert install_call[0][0] == ["crontab", "-"]
        crontab_input = install_call[1]["input"]
        assert "kitt-schedule:weekly" in crontab_input
        assert "30 1 * * 0" in crontab_input

    @patch("subprocess.run")
    def test_uses_config_stem_as_default_id(self, mock_run, scheduler):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        scheduler.schedule("/path/to/my_campaign.yaml", "0 3 * * *")

        config_file = scheduler.config_dir / "my_campaign.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data["schedule_id"] == "my_campaign"

    @patch("subprocess.run")
    def test_overwrites_existing_entry_for_same_id(self, mock_run, scheduler):
        existing_crontab = "0 1 * * * /old/command # kitt-schedule:nightly\n"
        mock_run.return_value = MagicMock(
            returncode=0, stdout=existing_crontab, stderr=""
        )

        scheduler.schedule(
            "/path/to/new_campaign.yaml", "0 4 * * *", campaign_id="nightly"
        )

        install_call = mock_run.call_args_list[1]
        crontab_input = install_call[1]["input"]
        # Old entry should be removed
        assert "0 1 * * * /old/command" not in crontab_input
        # New entry should be present
        assert "0 4 * * *" in crontab_input
        assert "kitt-schedule:nightly" in crontab_input

    @patch("subprocess.run", side_effect=FileNotFoundError("crontab not found"))
    def test_handles_missing_crontab(self, mock_run, scheduler):
        result = scheduler.schedule(
            "/path/to/campaign.yaml", "0 2 * * *", campaign_id="test"
        )
        # Should still succeed (config saved to file)
        assert result is True
        config_file = scheduler.config_dir / "test.json"
        assert config_file.exists()


class TestUnschedule:
    @patch("subprocess.run")
    def test_removes_config_file(self, mock_run, scheduler):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create a config file first
        config_file = scheduler.config_dir / "nightly.json"
        config_file.write_text(json.dumps({"schedule_id": "nightly"}))
        assert config_file.exists()

        result = scheduler.unschedule("nightly")
        assert result is True
        assert not config_file.exists()

    @patch("subprocess.run")
    def test_removes_crontab_entry(self, mock_run, scheduler):
        existing = (
            "0 2 * * * /usr/bin/python -m kitt campaign run /cfg.yaml # kitt-schedule:nightly\n"
            "0 0 * * * /other/job\n"
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=existing, stderr="")

        scheduler.unschedule("nightly")

        install_call = mock_run.call_args_list[1]
        crontab_input = install_call[1]["input"]
        assert "kitt-schedule:nightly" not in crontab_input
        assert "/other/job" in crontab_input


class TestListScheduled:
    def test_returns_all_saved_schedules(self, scheduler):
        for name in ["nightly", "weekly", "monthly"]:
            (scheduler.config_dir / f"{name}.json").write_text(
                json.dumps({"schedule_id": name, "cron_expr": "0 0 * * *"})
            )

        schedules = scheduler.list_scheduled()
        assert len(schedules) == 3
        ids = {s["schedule_id"] for s in schedules}
        assert ids == {"nightly", "weekly", "monthly"}

    def test_returns_empty_for_no_schedules(self, scheduler):
        schedules = scheduler.list_scheduled()
        assert schedules == []
