"""Tests for campaign state manager."""

import pytest

from kitt.campaign.state_manager import CampaignState, CampaignStateManager, RunState


@pytest.fixture
def state_mgr(tmp_path):
    return CampaignStateManager(campaigns_dir=tmp_path)


class TestCampaignStateManager:
    def test_create(self, state_mgr):
        state = state_mgr.create("test-001", "Test Campaign")
        assert state.campaign_id == "test-001"
        assert state.campaign_name == "Test Campaign"
        assert state.status == "running"
        assert state.started_at

    def test_save_and_load(self, state_mgr):
        state = state_mgr.create("test-002", "Saved Campaign")
        state.runs.append(
            RunState(
                model_name="Llama-8B",
                engine_name="llama_cpp",
                quant="Q4_K_M",
                status="success",
                duration_s=120.5,
            )
        )
        state_mgr.save(state)

        loaded = state_mgr.load("test-002")
        assert loaded is not None
        assert loaded.campaign_name == "Saved Campaign"
        assert len(loaded.runs) == 1
        assert loaded.runs[0].status == "success"
        assert loaded.runs[0].duration_s == 120.5

    def test_load_nonexistent(self, state_mgr):
        assert state_mgr.load("nonexistent") is None

    def test_list_campaigns(self, state_mgr):
        state_mgr.create("camp-1", "First")
        state_mgr.create("camp-2", "Second")
        campaigns = state_mgr.list_campaigns()
        assert len(campaigns) == 2
        names = {c["campaign_name"] for c in campaigns}
        assert names == {"First", "Second"}

    def test_update_run(self, state_mgr):
        state = state_mgr.create("test-003", "Update Test")
        state.runs.append(
            RunState(
                model_name="Llama-8B",
                engine_name="vllm",
                quant="bf16",
                status="pending",
            )
        )
        state_mgr.save(state)

        state_mgr.update_run(
            state,
            "Llama-8B|vllm|bf16",
            status="success",
            duration_s=300.0,
            output_dir="/results/test",
        )

        loaded = state_mgr.load("test-003")
        assert loaded.runs[0].status == "success"
        assert loaded.runs[0].duration_s == 300.0
        assert loaded.runs[0].output_dir == "/results/test"
        assert loaded.runs[0].completed_at

    def test_is_run_done(self, state_mgr):
        state = state_mgr.create("test-004", "Done Check")
        state.runs.append(
            RunState(
                model_name="Llama-8B",
                engine_name="vllm",
                quant="bf16",
                status="success",
            )
        )
        assert state_mgr.is_run_done(state, "Llama-8B|vllm|bf16")
        assert not state_mgr.is_run_done(state, "Llama-8B|ollama|8b")


class TestCampaignState:
    def test_completed_keys(self):
        state = CampaignState(campaign_id="t", campaign_name="t")
        state.runs = [
            RunState("M1", "e1", "q1", "success"),
            RunState("M1", "e2", "q1", "failed"),
            RunState("M2", "e1", "q1", "pending"),
        ]
        keys = state.completed_keys
        assert "M1|e1|q1" in keys
        assert "M1|e2|q1" in keys
        assert "M2|e1|q1" not in keys

    def test_counts(self):
        state = CampaignState(campaign_id="t", campaign_name="t")
        state.runs = [
            RunState("M1", "e1", "q1", "success"),
            RunState("M1", "e2", "q1", "failed"),
            RunState("M2", "e1", "q1", "skipped"),
            RunState("M2", "e2", "q1", "pending"),
        ]
        assert state.total == 4
        assert state.succeeded == 1
        assert state.failed == 1
        assert state.skipped == 1
        assert state.pending == 1


class TestRunState:
    def test_key(self):
        run = RunState("Model", "engine", "quant", "pending")
        assert run.key == "Model|engine|quant"
