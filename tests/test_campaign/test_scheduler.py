"""Tests for campaign scheduler."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.models import (
    CampaignConfig,
    CampaignEngineSpec,
    CampaignModelSpec,
    CampaignRunSpec,
    DiskConfig,
    ResourceLimitsConfig,
)
from kitt.campaign.scheduler import (
    CampaignScheduler,
    estimate_quant_size_gb,
    parse_params,
)
from kitt.campaign.state_manager import CampaignState, RunState


@pytest.fixture
def scheduler():
    return CampaignScheduler(DiskConfig(reserve_gb=50.0))


@pytest.fixture
def sample_config():
    return CampaignConfig(
        campaign_name="test",
        models=[
            CampaignModelSpec(
                name="Llama-8B",
                params="8B",
                safetensors_repo="meta-llama/Llama-3.1-8B",
                gguf_repo="bartowski/Llama-3.1-8B-GGUF",
                ollama_tag="llama3.1:8b",
                estimated_size_gb=16.0,
            ),
            CampaignModelSpec(
                name="Qwen-7B",
                params="7B",
                gguf_repo="Qwen/Qwen2.5-7B-GGUF",
                ollama_tag="qwen2.5:7b",
                estimated_size_gb=14.0,
            ),
        ],
        engines=[
            CampaignEngineSpec(name="vllm"),
            CampaignEngineSpec(name="llama_cpp"),
            CampaignEngineSpec(name="ollama"),
        ],
    )


class TestCampaignScheduler:
    def test_plan_runs(self, scheduler, sample_config):
        runs = scheduler.plan_runs(sample_config)
        # Llama-8B: vllm(bf16) + llama_cpp(discover) + ollama(discover) = 3
        # Qwen-7B: no safetensors_repo so no vllm + llama_cpp(discover) + ollama(discover) = 2
        assert len(runs) == 5

    def test_plan_runs_vllm_only_with_safetensors(self, scheduler, sample_config):
        runs = scheduler.plan_runs(sample_config)
        vllm_runs = [r for r in runs if r.engine_name == "vllm"]
        assert len(vllm_runs) == 1
        assert vllm_runs[0].model_name == "Llama-8B"
        assert vllm_runs[0].quant == "bf16"

    def test_order_by_size(self, scheduler):
        runs = [
            CampaignRunSpec(
                model_name="Big", engine_name="e", quant="q", estimated_size_gb=70.0
            ),
            CampaignRunSpec(
                model_name="Small", engine_name="e", quant="q", estimated_size_gb=4.0
            ),
            CampaignRunSpec(
                model_name="Med", engine_name="e", quant="q", estimated_size_gb=16.0
            ),
        ]
        ordered = scheduler.order_by_size(runs)
        assert ordered[0].model_name == "Small"
        assert ordered[1].model_name == "Med"
        assert ordered[2].model_name == "Big"

    def test_filter_completed(self, scheduler):
        runs = [
            CampaignRunSpec(model_name="M1", engine_name="e1", quant="q1"),
            CampaignRunSpec(model_name="M2", engine_name="e1", quant="q1"),
        ]
        state = CampaignState(campaign_id="t", campaign_name="t")
        state.runs = [RunState("M1", "e1", "q1", "success")]

        remaining = scheduler.filter_completed(runs, state)
        assert len(remaining) == 1
        assert remaining[0].model_name == "M2"

    @patch("shutil.disk_usage")
    def test_check_disk_space_passes(self, mock_disk, scheduler):
        """Should pass when disk has plenty of space."""
        mock_disk.return_value = MagicMock(free=500 * 1024**3)  # 500 GB free
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="q",
            estimated_size_gb=1.0,
        )
        assert scheduler.check_disk_space(run) is True

    @patch("shutil.disk_usage")
    def test_should_skip_returns_false_normally(self, mock_disk, scheduler):
        mock_disk.return_value = MagicMock(free=500 * 1024**3)  # 500 GB free
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="q",
            estimated_size_gb=0.1,
        )
        assert scheduler.should_skip(run) is False

    def test_should_skip_for_size_no_limit(self, scheduler):
        """With default limit (0), nothing is skipped."""
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="q",
            estimated_size_gb=999.0,
        )
        assert scheduler.should_skip_for_size(run) is False

    def test_should_skip_for_size_under_limit(self):
        sched = CampaignScheduler(
            DiskConfig(reserve_gb=50.0),
            ResourceLimitsConfig(max_model_size_gb=100.0),
        )
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="q",
            estimated_size_gb=50.0,
        )
        assert sched.should_skip_for_size(run) is False

    def test_should_skip_for_size_over_limit(self):
        sched = CampaignScheduler(
            DiskConfig(reserve_gb=50.0),
            ResourceLimitsConfig(max_model_size_gb=100.0),
        )
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="fp16",
            estimated_size_gb=154.0,
        )
        assert sched.should_skip_for_size(run) is True

    def test_should_skip_for_size_zero_estimated(self):
        """Runs with no size estimate are not skipped."""
        sched = CampaignScheduler(
            DiskConfig(reserve_gb=50.0),
            ResourceLimitsConfig(max_model_size_gb=100.0),
        )
        run = CampaignRunSpec(
            model_name="test",
            engine_name="e",
            quant="q",
            estimated_size_gb=0.0,
        )
        assert sched.should_skip_for_size(run) is False

    def test_should_skip_integrates_size_check(self):
        """should_skip() checks both disk and size."""
        sched = CampaignScheduler(
            DiskConfig(reserve_gb=50.0),
            ResourceLimitsConfig(max_model_size_gb=100.0),
        )
        run = CampaignRunSpec(
            model_name="big",
            engine_name="e",
            quant="fp16",
            estimated_size_gb=150.0,
        )
        assert sched.should_skip(run) is True


class TestParseParams:
    def test_simple(self):
        assert parse_params("8B") == 8.0

    def test_large(self):
        assert parse_params("70B") == 70.0

    def test_decimal(self):
        assert parse_params("1.5B") == 1.5

    def test_lowercase(self):
        assert parse_params("14b") == 14.0

    def test_empty(self):
        assert parse_params("") == 0.0

    def test_no_match(self):
        assert parse_params("unknown") == 0.0


class TestEstimateQuantSizeGb:
    def test_fp16_8b(self):
        size = estimate_quant_size_gb(8.0, "fp16")
        assert size == pytest.approx(17.6, abs=0.1)

    def test_bf16_8b(self):
        size = estimate_quant_size_gb(8.0, "bf16")
        assert size == pytest.approx(17.6, abs=0.1)

    def test_fp16_70b(self):
        size = estimate_quant_size_gb(70.0, "fp16")
        assert size == pytest.approx(154.0, abs=1.0)

    def test_q4_k_m_70b(self):
        size = estimate_quant_size_gb(70.0, "Q4_K_M")
        assert 35.0 < size < 55.0

    def test_f32_14b(self):
        size = estimate_quant_size_gb(14.0, "f32")
        assert size == pytest.approx(61.6, abs=1.0)

    def test_q8_0_8b(self):
        size = estimate_quant_size_gb(8.0, "Q8_0")
        assert 7.0 < size < 12.0

    def test_zero_params(self):
        assert estimate_quant_size_gb(0.0, "Q4_K_M") == 0.0

    def test_unknown_quant(self):
        assert estimate_quant_size_gb(8.0, "unknown_format") == 0.0

    def test_ollama_fp16_tag(self):
        """Ollama tags like '70b-instruct-fp16' should match fp16."""
        size = estimate_quant_size_gb(70.0, "70b-instruct-fp16")
        assert size == pytest.approx(154.0, abs=1.0)

    def test_ollama_q4_tag(self):
        """Ollama tags like '8b-instruct-q4_0' should match q4_0."""
        size = estimate_quant_size_gb(8.0, "8b-instruct-q4_0")
        assert 3.0 < size < 7.0

    def test_case_insensitive(self):
        size_upper = estimate_quant_size_gb(8.0, "Q4_K_M")
        size_lower = estimate_quant_size_gb(8.0, "q4_k_m")
        assert size_upper == size_lower
