"""Tests for campaign CLI commands."""

import json

import pytest
from click.testing import CliRunner

from kitt.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_config(tmp_path):
    config = {
        "campaign_name": "test-campaign",
        "models": [
            {
                "name": "TestModel",
                "params": "7B",
                "safetensors_repo": "test/repo",
            },
        ],
        "engines": [
            {"name": "vllm", "suite": "standard"},
        ],
        "disk": {"reserve_gb": 10.0},
    }
    config_path = tmp_path / "campaign.yaml"

    import yaml

    config_path.write_text(yaml.dump(config))
    return config_path


class TestCampaignRun:
    def test_dry_run(self, runner, sample_config):
        result = runner.invoke(
            cli, ["campaign", "run", str(sample_config), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Campaign Complete" in result.output

    def test_dry_run_with_id(self, runner, sample_config):
        result = runner.invoke(
            cli,
            [
                "campaign",
                "run",
                str(sample_config),
                "--dry-run",
                "--campaign-id",
                "test-123",
            ],
        )
        assert result.exit_code == 0

    def test_missing_config(self, runner):
        result = runner.invoke(cli, ["campaign", "run", "/nonexistent.yaml"])
        assert result.exit_code != 0


class TestCampaignList:
    def test_empty_list(self, runner, tmp_path):
        result = runner.invoke(cli, ["campaign", "list"])
        # May show "No campaigns found" or a table
        assert result.exit_code == 0


class TestCampaignStatus:
    def test_status_no_campaigns(self, runner):
        result = runner.invoke(cli, ["campaign", "status"])
        assert result.exit_code == 0

    def test_status_nonexistent_id(self, runner):
        result = runner.invoke(cli, ["campaign", "status", "nonexistent-id"])
        # Should fail gracefully
        assert result.exit_code != 0 or "not found" in result.output.lower()


class TestCampaignCreate:
    def test_create_from_results(self, runner, tmp_path):
        # Create fake results
        results_dir = tmp_path / "kitt-results" / "run1"
        results_dir.mkdir(parents=True)
        metrics = {
            "model": "Llama-8B",
            "engine": "vllm",
            "suite_name": "standard",
            "passed": True,
            "total_benchmarks": 8,
        }
        (results_dir / "metrics.json").write_text(json.dumps(metrics))

        result = runner.invoke(
            cli,
            ["campaign", "create", "--from-results", str(tmp_path / "kitt-results")],
        )
        assert result.exit_code == 0
        assert "campaign_name" in result.output

    def test_create_with_output(self, runner, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        run_dir = results_dir / "run1"
        run_dir.mkdir()
        (run_dir / "metrics.json").write_text(
            json.dumps({"model": "Test", "engine": "ollama"})
        )

        output_file = tmp_path / "campaign.yaml"
        result = runner.invoke(
            cli,
            [
                "campaign",
                "create",
                "--from-results",
                str(results_dir),
                "-o",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

    def test_create_empty_results(self, runner, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(
            cli,
            ["campaign", "create", "--from-results", str(empty_dir)],
        )
        assert result.exit_code != 0
