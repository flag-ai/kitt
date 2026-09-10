"""Campaign-related Pydantic models for the web UI."""

from pydantic import BaseModel, Field


class WebCampaignCreate(BaseModel):
    """Payload for creating a campaign via the web UI."""

    name: str
    description: str = ""
    models: list[dict] = Field(default_factory=list)
    engines: list[dict] = Field(default_factory=list)
    suite: str = "quick"
    agent_id: str = ""
    devon_managed: bool = True
    cleanup_after_run: bool = True


class WebCampaignSummary(BaseModel):
    """Summary view of a web campaign."""

    id: str
    name: str
    description: str = ""
    status: str = "draft"
    agent_id: str = ""
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_runs: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    error: str = ""
