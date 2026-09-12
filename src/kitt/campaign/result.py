"""Campaign result dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CampaignRunResult:
    """Result of a single campaign run."""

    model_name: str
    engine_name: str
    quant: str
    status: str  # "success", "failed", "skipped"
    duration_s: float = 0.0
    output_dir: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CampaignResult:
    """Aggregated result of a full campaign."""

    campaign_id: str
    campaign_name: str
    started_at: str = ""
    completed_at: str = ""
    runs: list[CampaignRunResult] = field(default_factory=list)

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
    def total_duration_s(self) -> float:
        return sum(r.duration_s for r in self.runs)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.succeeded / self.total
