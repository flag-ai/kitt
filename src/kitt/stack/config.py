"""Stack configuration management."""

import logging
import secrets
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".kitt" / "stacks.yaml"


class StackConfig(BaseModel):
    """Configuration for a generated deployment stack."""

    name: str

    # Component flags
    web: bool = False
    reporting: bool = False
    agent: bool = False
    postgres: bool = False
    monitoring: bool = False

    # Ports
    web_port: int = 8080
    agent_port: int = 8090
    postgres_port: int = 5432
    grafana_port: int = 3000
    prometheus_port: int = 9090
    influxdb_port: int = 8086

    # Secrets
    auth_token: str = ""
    secret_key: str = ""
    postgres_password: str = ""
    grafana_password: str = ""
    influxdb_token: str = ""

    # Paths
    local_dir: str = ""
    results_dir: str = ""

    # Agent
    server_url: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.auth_token:
            self.auth_token = secrets.token_hex(32)
        if not self.secret_key:
            self.secret_key = secrets.token_hex(32)
        if not self.postgres_password:
            self.postgres_password = secrets.token_urlsafe(24)
        if not self.grafana_password:
            self.grafana_password = secrets.token_urlsafe(16)
        if not self.influxdb_token:
            self.influxdb_token = secrets.token_hex(32)


class StackConfigManager:
    """CRUD operations on the stack registry."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH

    def _load(self) -> dict[str, Any]:
        if self.config_path.exists():
            return yaml.safe_load(self.config_path.read_text()) or {}
        return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(yaml.dump(data, default_flow_style=False))

    def add(self, config: StackConfig) -> None:
        """Add or update a stack."""
        data = self._load()
        stacks = data.get("stacks", {})
        stacks[config.name] = config.model_dump()
        data["stacks"] = stacks
        self._save(data)
        logger.info(f"Stack '{config.name}' saved")

    def get(self, name: str) -> StackConfig | None:
        """Get a stack configuration by name."""
        data = self._load()
        stacks = data.get("stacks", {})
        if name in stacks:
            return StackConfig(**stacks[name])
        return None

    def remove(self, name: str) -> bool:
        """Remove a stack by name.

        Returns:
            True if stack was removed.
        """
        data = self._load()
        stacks = data.get("stacks", {})
        if name in stacks:
            del stacks[name]
            data["stacks"] = stacks
            self._save(data)
            logger.info(f"Stack '{name}' removed")
            return True
        return False

    def list_stacks(self) -> list[StackConfig]:
        """List all configured stacks."""
        data = self._load()
        stacks = data.get("stacks", {})
        return [StackConfig(**v) for v in stacks.values()]
