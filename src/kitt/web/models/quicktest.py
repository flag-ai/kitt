"""Quick test models for the web UI."""

from pydantic import BaseModel


class QuickTestRequest(BaseModel):
    """Request payload for a quick test."""

    agent_id: str
    model_path: str
    engine_name: str
    benchmark_name: str = "throughput"
    suite_name: str = "quick"
    engine_mode: str = "docker"
    profile_id: str = ""
