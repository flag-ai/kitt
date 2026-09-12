"""Campaign state persistence and resume support."""

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RunState:
    """State of a single campaign run."""

    model_name: str
    engine_name: str
    quant: str
    status: str  # "pending", "running", "success", "failed", "skipped"
    duration_s: float = 0.0
    output_dir: str = ""
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    @property
    def key(self) -> str:
        return f"{self.model_name}|{self.engine_name}|{self.quant}"


@dataclass
class CampaignState:
    """Full state of a campaign execution."""

    campaign_id: str
    campaign_name: str
    started_at: str = ""
    completed_at: str = ""
    status: str = "running"  # "running", "completed", "failed", "paused"
    runs: list[RunState] = field(default_factory=list)

    @property
    def completed_keys(self) -> set:
        return {
            r.key for r in self.runs if r.status in ("success", "failed", "skipped")
        }

    @property
    def total(self) -> int:
        return len(self.runs)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.runs if r.status == "success")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.runs if r.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.runs if r.status == "skipped")

    @property
    def pending(self) -> int:
        return sum(1 for r in self.runs if r.status == "pending")


class CampaignStateManager:
    """Persist campaign state to disk with atomic writes.

    Follows the CheckpointManager pattern — stores JSON state files
    in ~/.kitt/campaigns/ with atomic write-then-rename for safety.
    """

    def __init__(self, campaigns_dir: Path | None = None) -> None:
        self.campaigns_dir = campaigns_dir or (Path.home() / ".kitt" / "campaigns")
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self, campaign_id: str) -> Path:
        return self.campaigns_dir / f"{campaign_id}.json"

    def create(self, campaign_id: str, campaign_name: str) -> CampaignState:
        """Create a new campaign state."""
        state = CampaignState(
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            started_at=datetime.now().isoformat(),
        )
        self.save(state)
        return state

    def save(self, state: CampaignState) -> None:
        """Atomically save campaign state to disk."""
        state_file = self._state_file(state.campaign_id)
        data = {
            "campaign_id": state.campaign_id,
            "campaign_name": state.campaign_name,
            "started_at": state.started_at,
            "completed_at": state.completed_at,
            "status": state.status,
            "runs": [asdict(r) for r in state.runs],
        }

        # Atomic write: write to temp file, then rename
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self.campaigns_dir, suffix=".tmp")
            try:
                os.fchmod(fd, 0o600)
                with open(fd, "w") as f:
                    json.dump(data, f, indent=2)
                Path(tmp_path).replace(state_file)
            except Exception:
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except Exception as e:
            logger.error(f"Failed to save campaign state: {e}")
            raise

    def load(self, campaign_id: str) -> CampaignState | None:
        """Load campaign state from disk."""
        state_file = self._state_file(campaign_id)
        if not state_file.exists():
            return None

        try:
            data = json.loads(state_file.read_text())
            state = CampaignState(
                campaign_id=data["campaign_id"],
                campaign_name=data["campaign_name"],
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at", ""),
                status=data.get("status", "running"),
                runs=[RunState(**r) for r in data.get("runs", [])],
            )
            return state
        except Exception as e:
            logger.error(f"Failed to load campaign state: {e}")
            return None

    def list_campaigns(self) -> list[dict[str, Any]]:
        """List all campaigns with summary info."""
        campaigns = []
        for state_file in sorted(self.campaigns_dir.glob("*.json")):
            try:
                data = json.loads(state_file.read_text())
                runs = data.get("runs", [])
                campaigns.append(
                    {
                        "campaign_id": data["campaign_id"],
                        "campaign_name": data["campaign_name"],
                        "status": data.get("status", "unknown"),
                        "started_at": data.get("started_at", ""),
                        "total_runs": len(runs),
                        "succeeded": sum(
                            1 for r in runs if r.get("status") == "success"
                        ),
                        "failed": sum(1 for r in runs if r.get("status") == "failed"),
                    }
                )
            except Exception as e:
                logger.warning(f"Could not read {state_file}: {e}")
        return campaigns

    def update_run(
        self,
        state: CampaignState,
        run_key: str,
        status: str,
        duration_s: float = 0.0,
        output_dir: str = "",
        error: str = "",
    ) -> None:
        """Update a specific run's status and save."""
        for run in state.runs:
            if run.key == run_key:
                run.status = status
                run.duration_s = duration_s
                run.output_dir = output_dir
                run.error = error
                if status == "running":
                    run.started_at = datetime.now().isoformat()
                elif status in ("success", "failed", "skipped"):
                    run.completed_at = datetime.now().isoformat()
                break
        self.save(state)

    def is_run_done(self, state: CampaignState, run_key: str) -> bool:
        """Check if a run has already completed (for resume)."""
        return run_key in state.completed_keys
