"""Tests for checkpoint manager."""

import pytest

from kitt.runners.checkpoint import CheckpointManager


@pytest.fixture
def checkpoint_mgr(tmp_path, monkeypatch):
    """Create a CheckpointManager with temporary directory."""
    monkeypatch.setattr(
        "kitt.runners.checkpoint.Path.home",
        lambda: tmp_path,
    )
    return CheckpointManager("test_bench", {"key": "value"})


class TestCheckpointManager:
    def test_no_checkpoint_initially(self, checkpoint_mgr):
        assert checkpoint_mgr.checkpoint_exists() is False
        assert checkpoint_mgr.get_last_completed_index() == 0
        assert checkpoint_mgr.load_partial_outputs() == []

    def test_save_and_load_checkpoint(self, checkpoint_mgr):
        outputs = [{"prompt": "test", "output": "result"}]
        checkpoint_mgr.save_checkpoint(0, outputs)

        assert checkpoint_mgr.checkpoint_exists() is True
        assert checkpoint_mgr.get_last_completed_index() == 1  # +1
        assert checkpoint_mgr.load_partial_outputs() == outputs

    def test_save_with_error(self, checkpoint_mgr):
        outputs = [{"prompt": "test", "output": "result"}]
        checkpoint_mgr.save_checkpoint(0, outputs, error="test error")

        assert checkpoint_mgr.checkpoint_exists() is True

    def test_clear_checkpoint(self, checkpoint_mgr):
        checkpoint_mgr.save_checkpoint(0, [{"data": "test"}])
        assert checkpoint_mgr.checkpoint_exists() is True

        checkpoint_mgr.clear_checkpoint()
        assert checkpoint_mgr.checkpoint_exists() is False

    def test_config_change_invalidates(self, checkpoint_mgr, tmp_path, monkeypatch):
        """Changing config should invalidate existing checkpoint."""
        checkpoint_mgr.save_checkpoint(5, [{"data": "test"}])

        monkeypatch.setattr(
            "kitt.runners.checkpoint.Path.home",
            lambda: tmp_path,
        )
        new_mgr = CheckpointManager("test_bench", {"key": "different_value"})
        assert new_mgr.get_last_completed_index() == 0

    def test_config_hash_stable(self, tmp_path, monkeypatch):
        """Same config should produce same hash."""
        monkeypatch.setattr(
            "kitt.runners.checkpoint.Path.home",
            lambda: tmp_path,
        )
        mgr1 = CheckpointManager("bench", {"a": 1, "b": 2})
        mgr2 = CheckpointManager("bench", {"a": 1, "b": 2})
        assert mgr1.config_hash == mgr2.config_hash

    def test_warmup_excluded_from_hash(self, tmp_path, monkeypatch):
        """Warmup config changes should not invalidate checkpoints."""
        monkeypatch.setattr(
            "kitt.runners.checkpoint.Path.home",
            lambda: tmp_path,
        )
        mgr1 = CheckpointManager("bench", {"key": 1, "warmup": {"iterations": 5}})
        mgr2 = CheckpointManager("bench", {"key": 1, "warmup": {"iterations": 10}})
        assert mgr1.config_hash == mgr2.config_hash

    def test_progressive_checkpointing(self, checkpoint_mgr):
        """Save multiple checkpoints progressively."""
        checkpoint_mgr.save_checkpoint(0, [{"i": 0}])
        assert checkpoint_mgr.get_last_completed_index() == 1

        checkpoint_mgr.save_checkpoint(5, [{"i": j} for j in range(6)])
        assert checkpoint_mgr.get_last_completed_index() == 6
        assert len(checkpoint_mgr.load_partial_outputs()) == 6
