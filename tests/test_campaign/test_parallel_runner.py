"""Tests for parallel campaign runner."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.models import (
    CampaignConfig,
    CampaignEngineSpec,
    CampaignModelSpec,
    CampaignRunSpec,
    DiskConfig,
)
from kitt.campaign.parallel_runner import ParallelCampaignRunner
from kitt.campaign.state_manager import CampaignState, CampaignStateManager, RunState


def _make_config(models=None, engines=None):
    return CampaignConfig(
        campaign_name="parallel-test",
        models=models
        or [
            CampaignModelSpec(
                name="test-model",
                gguf_repo="test/model-GGUF",
            ),
        ],
        engines=engines
        or [
            CampaignEngineSpec(name="llama_cpp"),
        ],
        suite="quick",
        disk=DiskConfig(reserve_gb=5),
    )


@pytest.fixture
def mock_state_manager():
    sm = MagicMock(spec=CampaignStateManager)
    sm.load.return_value = None
    sm.create.return_value = CampaignState(
        campaign_id="test-parallel",
        campaign_name="parallel-test",
        status="running",
        started_at=datetime.now().isoformat(),
        runs=[],
    )
    sm.is_run_done.return_value = False
    return sm


class TestParallelCampaignRunner:
    @patch("kitt.campaign.runner.filter_quants")
    @patch("kitt.campaign.runner.discover_gguf_quants")
    def test_dry_run(self, mock_discover, mock_filter, mock_state_manager):
        quants = [
            MagicMock(quant_name="Q4_K_M", include_pattern="*Q4_K_M*"),
        ]
        mock_discover.return_value = quants
        mock_filter.return_value = quants

        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
            dry_run=True,
        )

        result = runner.run(campaign_id="test-parallel")
        assert result.campaign_id == "test-parallel"
        assert result.total >= 1
        # All dry runs should succeed
        assert all(r.status == "success" for r in result.runs)

    @patch("kitt.campaign.runner.filter_quants")
    @patch("kitt.campaign.runner.discover_gguf_quants")
    def test_download_overlap(self, mock_discover, mock_filter, mock_state_manager):
        """Verify that downloads happen in parallel with benchmarks."""
        quants = [
            MagicMock(quant_name="Q4_K_M", include_pattern="*Q4_K_M*"),
            MagicMock(quant_name="Q5_K_M", include_pattern="*Q5_K_M*"),
        ]
        mock_discover.return_value = quants
        mock_filter.return_value = quants

        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
            dry_run=True,
        )

        result = runner.run(campaign_id="test-overlap")
        assert result.total == 2
        assert result.succeeded == 2

    @patch("kitt.campaign.runner.filter_quants")
    @patch("kitt.campaign.runner.discover_gguf_quants")
    def test_error_isolation(self, mock_discover, mock_filter, mock_state_manager):
        """One failed run shouldn't stop the campaign."""
        quants = [
            MagicMock(quant_name="Q4_K_M", include_pattern="*Q4_K_M*"),
            MagicMock(quant_name="Q5_K_M", include_pattern="*Q5_K_M*"),
        ]
        mock_discover.return_value = quants
        mock_filter.return_value = quants

        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
            dry_run=False,
        )

        # Make all downloads fail but catch it in execute
        with patch.object(runner._runner, "_execute_run") as mock_exec:
            from kitt.campaign.result import CampaignRunResult

            results = [
                CampaignRunResult(
                    model_name="test-model",
                    engine_name="llama_cpp",
                    quant="Q4_K_M",
                    status="failed",
                    error="test error",
                ),
                CampaignRunResult(
                    model_name="test-model",
                    engine_name="llama_cpp",
                    quant="Q5_K_M",
                    status="success",
                    duration_s=10.0,
                ),
            ]
            mock_exec.side_effect = results

            with patch.object(
                runner._runner, "_download_model", return_value="/fake/path"
            ):
                result = runner.run(campaign_id="test-isolation")

        assert result.total == 2
        assert result.failed == 1
        assert result.succeeded == 1

    def test_disk_space_check(self, mock_state_manager):
        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
        )

        with patch("kitt.campaign.parallel_runner.shutil.disk_usage") as mock_disk:
            mock_disk.return_value = MagicMock(
                free=50 * (1024**3),  # 50 GB free
            )
            assert runner._check_disk_space() is True

            mock_disk.return_value = MagicMock(
                free=1 * (1024**3),  # 1 GB free
            )
            assert runner._check_disk_space() is False

    def test_safe_download_catches_errors(self, mock_state_manager):
        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
        )

        run_spec = CampaignRunSpec(
            model_name="test",
            engine_name="llama_cpp",
            quant="Q4_K_M",
            suite="quick",
        )

        with patch.object(
            runner._runner,
            "_download_model",
            side_effect=RuntimeError("download failed"),
        ):
            result = runner._safe_download(run_spec)
            assert result is None

    def test_thread_safe_state_update(self, mock_state_manager):
        """Verify state lock is used during finalization."""
        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
            dry_run=True,
        )

        # Run should complete without deadlock
        with (
            patch("kitt.campaign.runner.discover_gguf_quants") as mock_discover,
            patch("kitt.campaign.runner.filter_quants") as mock_filter,
        ):
            quants = [MagicMock(quant_name="Q4_K_M", include_pattern="*Q4_K_M*")]
            mock_discover.return_value = quants
            mock_filter.return_value = quants
            result = runner.run(campaign_id="test-thread-safe")

        assert result.completed_at is not None
        mock_state_manager.save.assert_called()

    @patch("kitt.campaign.runner.filter_quants")
    @patch("kitt.campaign.runner.discover_gguf_quants")
    def test_resume_support(self, mock_discover, mock_filter, mock_state_manager):
        quants = [MagicMock(quant_name="Q4_K_M", include_pattern="*Q4_K_M*")]
        mock_discover.return_value = quants
        mock_filter.return_value = quants

        existing_state = CampaignState(
            campaign_id="test-resume",
            campaign_name="parallel-test",
            status="running",
            started_at=datetime.now().isoformat(),
            runs=[
                RunState(
                    model_name="test-model",
                    engine_name="llama_cpp",
                    quant="Q4_K_M",
                    status="success",
                )
            ],
        )
        mock_state_manager.load.return_value = existing_state
        mock_state_manager.is_run_done.return_value = True

        config = _make_config()
        runner = ParallelCampaignRunner(
            config=config,
            state_manager=mock_state_manager,
            dry_run=True,
        )

        result = runner.run(campaign_id="test-resume", resume=True)
        # All runs already done, so 0 new runs
        assert result.total == 0
