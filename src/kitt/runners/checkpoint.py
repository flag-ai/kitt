"""Checkpoint management for error recovery during long-running benchmarks."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manage benchmark checkpoints for recovery from failures."""

    def __init__(self, test_name: str, config: dict[str, Any]) -> None:
        """Initialize checkpoint manager.

        Args:
            test_name: Name of the benchmark.
            config: Benchmark configuration (used to detect config changes).
        """
        self.test_name = test_name
        self.config_hash = self._hash_config(config)
        self.checkpoint_dir = Path.home() / ".kitt" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = (
            self.checkpoint_dir / f"{test_name}_{self.config_hash}.json"
        )

    def _hash_config(self, config: dict[str, Any]) -> str:
        """Create hash of config to detect changes."""
        config_copy = config.copy()
        config_copy.pop("warmup", None)  # Warmup doesn't affect checkpoint validity
        config_str = json.dumps(config_copy, sort_keys=True, default=str)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]

    def save_checkpoint(
        self,
        last_index: int,
        partial_outputs: list[dict],
        error: str | None = None,
    ) -> None:
        """Save checkpoint to disk.

        Args:
            last_index: Last completed item index.
            partial_outputs: All outputs so far.
            error: Optional error message.
        """
        checkpoint_data = {
            "test_name": self.test_name,
            "config_hash": self.config_hash,
            "last_completed_index": last_index,
            "total_completed": len(partial_outputs),
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "outputs": partial_outputs,
        }

        try:
            with open(self.checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f)
            self.checkpoint_file.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def get_last_completed_index(self) -> int:
        """Get index of last completed item from checkpoint."""
        if not self.checkpoint_file.exists():
            return 0

        try:
            with open(self.checkpoint_file) as f:
                data = json.load(f)
                if data["config_hash"] != self.config_hash:
                    logger.warning("Config changed, ignoring checkpoint")
                    return 0
                return data["last_completed_index"] + 1
        except Exception as e:
            logger.warning(f"Could not load checkpoint: {e}")
            return 0

    def load_partial_outputs(self) -> list[dict]:
        """Load partial outputs from checkpoint."""
        if not self.checkpoint_file.exists():
            return []

        try:
            with open(self.checkpoint_file) as f:
                data = json.load(f)
                return data["outputs"]
        except Exception as e:
            logger.warning(f"Could not load partial outputs: {e}")
            return []

    def clear_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion."""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
            except Exception as e:
                logger.warning(f"Could not clear checkpoint: {e}")

    def checkpoint_exists(self) -> bool:
        """Check if checkpoint exists for this benchmark."""
        return self.checkpoint_file.exists()
