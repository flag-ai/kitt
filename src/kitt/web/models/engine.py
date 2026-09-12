"""Engine profile models for the web UI."""

from typing import Literal

from pydantic import BaseModel, Field


class EngineProfileCreate(BaseModel):
    """Request payload for creating an engine profile."""

    name: str
    engine: str
    mode: Literal["docker", "native"] = "docker"
    description: str = ""
    build_config: dict = Field(default_factory=dict)
    runtime_config: dict = Field(default_factory=dict)


class EngineProfile(EngineProfileCreate):
    """Engine profile with server-generated fields."""

    id: str
    created_at: str
    updated_at: str
