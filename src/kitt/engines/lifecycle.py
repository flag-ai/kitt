"""Engine execution mode definitions."""

from enum import Enum


class EngineMode(str, Enum):
    """How an engine runs on the host."""

    DOCKER = "docker"
    NATIVE = "native"
