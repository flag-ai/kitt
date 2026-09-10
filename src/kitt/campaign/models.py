"""Pydantic models for campaign configuration."""

from typing import Any

from pydantic import BaseModel, Field


class CampaignModelSpec(BaseModel):
    """Specification for a model to benchmark in a campaign."""

    name: str
    params: str = ""
    safetensors_repo: str | None = None
    gguf_repo: str | None = None
    ollama_tag: str | None = None
    estimated_size_gb: float = 0.0


class CampaignEngineSpec(BaseModel):
    """Engine configuration for a campaign."""

    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    suite: str = "standard"
    formats: list[str] = Field(default_factory=list)


class DiskConfig(BaseModel):
    """Disk space management configuration."""

    reserve_gb: float = Field(default=100.0, ge=0.0)
    storage_path: str | None = None
    cleanup_after_run: bool = True


class NotificationConfig(BaseModel):
    """Notification settings for campaign events."""

    webhook_url: str | None = None
    email: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    desktop: bool = False
    on_complete: bool = True
    on_failure: bool = True


class ResourceLimitsConfig(BaseModel):
    """Resource-based skip rules for campaign runs.

    Models/quants whose estimated loaded size exceeds max_model_size_gb
    are skipped automatically. Set to 0 to disable (no limit).
    """

    max_model_size_gb: float = Field(
        default=0.0,
        ge=0.0,
        description="Skip runs where estimated model size exceeds this limit (0 = no limit)",
    )


class QuantFilterConfig(BaseModel):
    """Filter rules for quantization variants."""

    skip_patterns: list[str] = Field(default_factory=list)
    include_only: list[str] = Field(default_factory=list)


class CampaignRunSpec(BaseModel):
    """A single planned benchmark run within a campaign."""

    model_name: str
    engine_name: str
    quant: str
    model_path: str | None = None
    repo_id: str | None = None
    include_pattern: str | None = None
    estimated_size_gb: float = 0.0
    suite: str = "standard"
    engine_config: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        """Unique identifier for this run."""
        return f"{self.model_name}|{self.engine_name}|{self.quant}"


class CampaignConfig(BaseModel):
    """Top-level campaign configuration."""

    campaign_name: str
    description: str = ""
    models: list[CampaignModelSpec] = Field(default_factory=list)
    engines: list[CampaignEngineSpec] = Field(default_factory=list)
    disk: DiskConfig = Field(default_factory=DiskConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    quant_filter: QuantFilterConfig = Field(default_factory=QuantFilterConfig)
    resource_limits: ResourceLimitsConfig = Field(default_factory=ResourceLimitsConfig)
    parallel: bool = False
    devon_managed: bool = True
    devon_url: str | None = None
    devon_api_key: str | None = None
    hf_token: str | None = None
    skip_gated: bool = True
    matching_rules: list[str] | None = None
