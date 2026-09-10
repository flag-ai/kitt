"""Host configuration management for remote execution."""

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_HOSTS_PATH = Path.home() / ".kitt" / "hosts.yaml"


class HostConfig(BaseModel):
    """Configuration for a remote host."""

    name: str
    hostname: str
    user: str = ""
    ssh_key: str = ""
    port: int = 22
    kitt_path: str = "~/.local/bin/kitt"
    storage_path: str = "~/kitt-results"
    gpu_info: str = ""
    gpu_count: int = 0
    python_version: str = ""
    notes: str = ""
    strict_host_key: bool = True


class HostManager:
    """CRUD operations on the host registry."""

    def __init__(self, hosts_path: Path | None = None) -> None:
        self.hosts_path = hosts_path or DEFAULT_HOSTS_PATH

    def _load(self) -> dict[str, Any]:
        if self.hosts_path.exists():
            return yaml.safe_load(self.hosts_path.read_text()) or {}
        return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.hosts_path.parent.mkdir(parents=True, exist_ok=True)
        self.hosts_path.write_text(yaml.dump(data, default_flow_style=False))

    def add(self, config: HostConfig) -> None:
        """Add or update a host."""
        data = self._load()
        hosts = data.get("hosts", {})
        hosts[config.name] = config.model_dump()
        data["hosts"] = hosts
        self._save(data)
        logger.info(f"Host '{config.name}' saved")

    def remove(self, name: str) -> bool:
        """Remove a host by name.

        Returns:
            True if host was removed.
        """
        data = self._load()
        hosts = data.get("hosts", {})
        if name in hosts:
            del hosts[name]
            data["hosts"] = hosts
            self._save(data)
            logger.info(f"Host '{name}' removed")
            return True
        return False

    def get(self, name: str) -> HostConfig | None:
        """Get a host configuration by name."""
        data = self._load()
        hosts = data.get("hosts", {})
        if name in hosts:
            return HostConfig(**hosts[name])
        return None

    def list_hosts(self) -> list[HostConfig]:
        """List all configured hosts."""
        data = self._load()
        hosts = data.get("hosts", {})
        return [HostConfig(**v) for v in hosts.values()]
