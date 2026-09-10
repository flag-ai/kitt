"""Agent-related Pydantic models."""

from typing import Any

from pydantic import BaseModel, Field


class AgentRegistration(BaseModel):
    """Payload sent by an agent when it registers with the server."""

    name: str
    hostname: str
    port: int = 8090
    gpu_info: str = ""
    gpu_count: int = 0
    cpu_info: str = ""
    cpu_arch: str = ""
    ram_gb: int = 0
    environment_type: str = ""
    fingerprint: str = ""
    kitt_version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    hardware_details: str = ""


class AgentHeartbeat(BaseModel):
    """Payload sent periodically by an agent."""

    status: str = "idle"
    current_task: str = ""
    gpu_utilization_pct: float = 0.0
    gpu_memory_used_gb: float = 0.0
    storage_gb_free: float = 0.0
    uptime_s: float = 0.0
    engines: list[dict[str, Any]] = Field(default_factory=list)


class AgentCommand(BaseModel):
    """Command sent from server to agent.

    Command types:
        run_container — Docker container orchestration
        run_test — benchmark execution (Docker or native)
        cleanup_storage — evict local model copies
        stop_container — stop an active Docker container
        check_docker — check Docker availability
        engine_status — query native engine status
        start_engine — start a native engine process
        stop_engine — stop a native engine process
        install_engine — check/install an engine
    """

    command_id: str
    type: str
    payload: dict = Field(default_factory=dict)


class AgentProvisionRequest(BaseModel):
    """Payload for provisioning a new agent with a unique token."""

    name: str = ""
    port: int = 8090


class AgentProvisionResponse(BaseModel):
    """Returned once after provisioning — contains the raw token."""

    agent_id: str
    token: str
    token_prefix: str


class AgentSettings(BaseModel):
    """Per-agent configurable settings, synced via heartbeat."""

    model_storage_dir: str = "~/.kitt/models"
    model_share_source: str = ""
    model_share_mount: str = ""
    auto_cleanup: bool = True
    heartbeat_interval_s: int = 30


class AgentSummary(BaseModel):
    """Summary view of an agent for listings."""

    id: str
    name: str
    hostname: str
    port: int
    status: str
    gpu_info: str = ""
    gpu_count: int = 0
    cpu_arch: str = ""
    last_heartbeat: str = ""
    tags: list[str] = Field(default_factory=list)
