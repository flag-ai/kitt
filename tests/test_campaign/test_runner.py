"""Tests for campaign runner."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.models import (
    CampaignConfig,
    CampaignEngineSpec,
    CampaignModelSpec,
    DiskConfig,
    NotificationConfig,
)
from kitt.campaign.result import CampaignResult, CampaignRunResult
from kitt.campaign.runner import CampaignRunner
from kitt.campaign.state_manager import CampaignStateManager


@pytest.fixture
def simple_config():
    return CampaignConfig(
        campaign_name="test-campaign",
        models=[
            CampaignModelSpec(
                name="TestModel",
                params="7B",
                safetensors_repo="test/safetensors-repo",
                estimated_size_gb=14.0,
            ),
        ],
        engines=[
            CampaignEngineSpec(name="vllm"),
        ],
        disk=DiskConfig(reserve_gb=10.0),
        notifications=NotificationConfig(),
        devon_managed=False,
    )


@pytest.fixture
def state_mgr(tmp_path):
    return CampaignStateManager(campaigns_dir=tmp_path)


class TestCampaignRunner:
    @patch("shutil.disk_usage")
    def test_dry_run(self, mock_disk, simple_config, state_mgr):
        mock_disk.return_value = MagicMock(free=500 * 1024**3)
        runner = CampaignRunner(simple_config, state_mgr, dry_run=True)
        result = runner.run(campaign_id="test-dry")

        assert isinstance(result, CampaignResult)
        assert result.campaign_id == "test-dry"
        assert len(result.runs) == 1
        assert result.runs[0].status == "success"
        assert result.runs[0].output_dir == "dry-run"

    @patch("shutil.disk_usage")
    def test_resume_skips_completed(self, mock_disk, simple_config, state_mgr):
        """Resume should skip already-completed runs."""
        mock_disk.return_value = MagicMock(free=500 * 1024**3)
        # First run
        runner = CampaignRunner(simple_config, state_mgr, dry_run=True)
        result1 = runner.run(campaign_id="test-resume")
        assert result1.succeeded == 1

        # Resume — should find everything done
        runner2 = CampaignRunner(simple_config, state_mgr, dry_run=True)
        result2 = runner2.run(campaign_id="test-resume", resume=True)
        assert result2.total == 0  # Nothing remaining

    def test_error_isolation(self, state_mgr):
        """One failing run should not stop the campaign."""
        config = CampaignConfig(
            campaign_name="error-test",
            models=[
                CampaignModelSpec(name="M1", safetensors_repo="test/m1"),
                CampaignModelSpec(name="M2", safetensors_repo="test/m2"),
            ],
            engines=[CampaignEngineSpec(name="vllm")],
            disk=DiskConfig(reserve_gb=1.0),
            devon_managed=False,
        )
        runner = CampaignRunner(config, state_mgr, dry_run=False)

        # Mock _execute_run to fail on first, succeed on second
        call_count = 0

        def mock_execute(run_spec, state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return CampaignRunResult(
                    model_name=run_spec.model_name,
                    engine_name=run_spec.engine_name,
                    quant=run_spec.quant,
                    status="failed",
                    error="Simulated failure",
                )
            return CampaignRunResult(
                model_name=run_spec.model_name,
                engine_name=run_spec.engine_name,
                quant=run_spec.quant,
                status="success",
            )

        runner._execute_run = mock_execute
        result = runner.run(campaign_id="error-test")

        assert result.total == 2
        assert result.failed == 1
        assert result.succeeded == 1

    def test_disk_skip(self, state_mgr):
        """Runs should be skipped if disk space is insufficient."""
        config = CampaignConfig(
            campaign_name="disk-test",
            models=[
                CampaignModelSpec(
                    name="HugeModel",
                    safetensors_repo="test/huge",
                    estimated_size_gb=999999.0,
                ),
            ],
            engines=[CampaignEngineSpec(name="vllm")],
            disk=DiskConfig(reserve_gb=999999.0),
            devon_managed=False,
        )
        runner = CampaignRunner(config, state_mgr, dry_run=False)
        result = runner.run(campaign_id="disk-test")

        assert result.total == 1
        assert result.skipped == 1
        assert "disk space" in result.runs[0].error.lower()


class TestExpandRuns:
    def test_expand_gguf_discovery(self, state_mgr):
        config = CampaignConfig(
            campaign_name="expand-test",
            models=[
                CampaignModelSpec(
                    name="TestModel",
                    gguf_repo="test/gguf-repo",
                ),
            ],
            engines=[CampaignEngineSpec(name="llama_cpp")],
        )
        runner = CampaignRunner(config, state_mgr, dry_run=True)

        with patch("kitt.campaign.runner.discover_gguf_quants") as mock_discover:
            from kitt.campaign.gguf_discovery import GGUFQuantInfo

            mock_discover.return_value = [
                GGUFQuantInfo(quant_name="Q4_K_M", files=["Model-Q4_K_M.gguf"]),
                GGUFQuantInfo(quant_name="Q8_0", files=["Model-Q8_0.gguf"]),
            ]
            planned = runner.scheduler.plan_runs(config)
            expanded = runner._expand_runs(planned)

        assert len(expanded) == 2
        assert expanded[0].quant == "Q4_K_M"
        assert expanded[1].quant == "Q8_0"

    def test_expand_ollama_discovery(self, state_mgr):
        config = CampaignConfig(
            campaign_name="expand-ollama",
            models=[
                CampaignModelSpec(
                    name="TestModel",
                    ollama_tag="test:7b",
                ),
            ],
            engines=[CampaignEngineSpec(name="ollama")],
        )
        runner = CampaignRunner(config, state_mgr, dry_run=True)

        with patch("kitt.campaign.runner.discover_ollama_tags") as mock_discover:
            mock_discover.return_value = [
                "test:7b-instruct-q4_0",
                "test:7b-instruct-q5_K_M",
            ]
            planned = runner.scheduler.plan_runs(config)
            expanded = runner._expand_runs(planned)

        assert len(expanded) == 2

    def test_quant_filter_applied(self, state_mgr):
        config = CampaignConfig(
            campaign_name="filter-test",
            models=[
                CampaignModelSpec(name="Test", gguf_repo="test/repo"),
            ],
            engines=[CampaignEngineSpec(name="llama_cpp")],
            quant_filter={"skip_patterns": ["IQ1_*", "IQ2_*"]},
        )
        runner = CampaignRunner(config, state_mgr, dry_run=True)

        with patch("kitt.campaign.runner.discover_gguf_quants") as mock:
            from kitt.campaign.gguf_discovery import GGUFQuantInfo

            mock.return_value = [
                GGUFQuantInfo(quant_name="Q4_K_M", files=["a.gguf"]),
                GGUFQuantInfo(quant_name="IQ1_S", files=["b.gguf"]),
                GGUFQuantInfo(quant_name="IQ2_XXS", files=["c.gguf"]),
            ]
            planned = runner.scheduler.plan_runs(config)
            expanded = runner._expand_runs(planned)

        assert len(expanded) == 1
        assert expanded[0].quant == "Q4_K_M"


class TestCampaignRunResult:
    def test_result_properties(self):
        result = CampaignResult(
            campaign_id="test",
            campaign_name="Test",
            runs=[
                CampaignRunResult("M1", "e1", "q1", "success", duration_s=100),
                CampaignRunResult("M1", "e2", "q1", "failed", duration_s=50),
                CampaignRunResult("M2", "e1", "q1", "skipped"),
            ],
        )
        assert result.total == 3
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.skipped == 1
        assert result.total_duration_s == 150.0
        assert result.success_rate == pytest.approx(1 / 3)
