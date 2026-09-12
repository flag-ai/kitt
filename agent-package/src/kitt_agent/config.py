"""Agent daemon configuration model."""

from pathlib import Path

from pydantic import BaseModel, Field


class AgentTLSConfig(BaseModel):
    """TLS configuration for agent communication."""

    cert: str = ""
    key: str = ""
    ca: str = ""


class AgentDaemonConfig(BaseModel):
    """Configuration for a KITT agent daemon."""

    name: str = ""
    server_url: str = ""
    token: str = ""
    port: int = 8090
    heartbeat_interval_s: int = 30
    model_storage_dir: str = ""
    model_share_source: str = ""
    model_share_mount: str = ""
    auto_cleanup: bool = True
    tls: AgentTLSConfig = Field(default_factory=AgentTLSConfig)
    config_path: Path = Field(
        default_factory=lambda: Path.home() / ".kitt" / "agent.yaml"
    )
