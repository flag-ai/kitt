"""Tests for stack configuration management."""

from pathlib import Path

from kitt.stack.config import StackConfig, StackConfigManager


class TestStackConfig:
    """Tests for StackConfig model."""

    def test_defaults(self):
        config = StackConfig(name="test")
        assert config.name == "test"
        assert config.web is False
        assert config.reporting is False
        assert config.agent is False
        assert config.postgres is False
        assert config.monitoring is False
        assert config.web_port == 8080
        assert config.agent_port == 8090
        assert config.postgres_port == 5432
        assert config.grafana_port == 3000
        assert config.prometheus_port == 9090
        assert config.influxdb_port == 8086
        assert isinstance(config.auth_token, str) and len(config.auth_token) > 0
        assert isinstance(config.secret_key, str) and len(config.secret_key) > 0
        assert (
            isinstance(config.postgres_password, str)
            and len(config.postgres_password) > 0
        )
        assert (
            isinstance(config.grafana_password, str)
            and len(config.grafana_password) > 0
        )
        assert isinstance(config.influxdb_token, str) and len(config.influxdb_token) > 0
        assert config.local_dir == ""
        assert config.results_dir == ""
        assert config.server_url == ""

    def test_custom_values(self):
        config = StackConfig(
            name="prod",
            web=True,
            postgres=True,
            monitoring=True,
            web_port=9090,
            agent_port=9091,
            postgres_port=5433,
            grafana_port=3001,
            prometheus_port=9091,
            influxdb_port=8087,
            auth_token="secret-token",
            secret_key="my-secret",
            postgres_password="strongpw",
            grafana_password="grafanapw",
            influxdb_token="custom-token",
            local_dir="/tmp/test",
            server_url="https://server:8080",
        )
        assert config.name == "prod"
        assert config.web is True
        assert config.postgres is True
        assert config.monitoring is True
        assert config.web_port == 9090
        assert config.postgres_port == 5433
        assert config.grafana_port == 3001
        assert config.auth_token == "secret-token"
        assert config.postgres_password == "strongpw"
        assert config.server_url == "https://server:8080"


class TestStackConfigManager:
    """Tests for StackConfigManager CRUD."""

    def test_add_and_get(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)

        config = StackConfig(
            name="test-stack",
            web=True,
            local_dir="/tmp/test",
        )
        manager.add(config)

        retrieved = manager.get("test-stack")
        assert retrieved is not None
        assert retrieved.name == "test-stack"
        assert retrieved.web is True
        assert retrieved.local_dir == "/tmp/test"

    def test_get_nonexistent(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)
        assert manager.get("nonexistent") is None

    def test_remove(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)

        config = StackConfig(name="to-remove", web=True)
        manager.add(config)
        assert manager.get("to-remove") is not None

        assert manager.remove("to-remove") is True
        assert manager.get("to-remove") is None

    def test_remove_nonexistent(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)
        assert manager.remove("nonexistent") is False

    def test_list_stacks(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)

        manager.add(StackConfig(name="stack-a", web=True))
        manager.add(StackConfig(name="stack-b", agent=True))

        stacks = manager.list_stacks()
        assert len(stacks) == 2
        names = {s.name for s in stacks}
        assert names == {"stack-a", "stack-b"}

    def test_list_stacks_empty(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)
        assert manager.list_stacks() == []

    def test_add_updates_existing(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        manager = StackConfigManager(config_path)

        manager.add(StackConfig(name="stack", web_port=8080))
        manager.add(StackConfig(name="stack", web_port=9090))

        stacks = manager.list_stacks()
        assert len(stacks) == 1
        assert stacks[0].web_port == 9090

    def test_persistence(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"

        manager1 = StackConfigManager(config_path)
        manager1.add(StackConfig(name="persist", web=True, auth_token="mytoken"))

        manager2 = StackConfigManager(config_path)
        retrieved = manager2.get("persist")
        assert retrieved is not None
        assert retrieved.web is True
        assert retrieved.auth_token == "mytoken"
