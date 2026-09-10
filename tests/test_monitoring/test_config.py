"""Tests for monitoring stack configuration management."""

from pathlib import Path

from kitt.monitoring.config import MonitoringConfigManager, MonitoringStackConfig


class TestMonitoringStackConfig:
    """Tests for MonitoringStackConfig model."""

    def test_defaults(self):
        config = MonitoringStackConfig(name="test")
        assert config.name == "test"
        assert config.scrape_targets == []
        assert config.grafana_port == 3000
        assert config.prometheus_port == 9090
        assert config.influxdb_port == 8086
        assert (
            isinstance(config.grafana_password, str)
            and len(config.grafana_password) > 0
        )
        assert isinstance(config.influxdb_token, str) and len(config.influxdb_token) > 0
        assert config.deployed_to == ""
        assert config.remote_dir == ""
        assert config.local_dir == ""

    def test_custom_values(self):
        config = MonitoringStackConfig(
            name="lab",
            scrape_targets=["192.168.1.10:9100", "192.168.1.11:9100"],
            grafana_port=3001,
            prometheus_port=9091,
            influxdb_port=8087,
            grafana_password="secret",
            influxdb_token="custom-token",
            local_dir="/tmp/test",
            deployed_to="dgx01",
            remote_dir="~/kitt-monitoring/lab",
        )
        assert config.name == "lab"
        assert len(config.scrape_targets) == 2
        assert config.grafana_port == 3001
        assert config.prometheus_port == 9091
        assert config.influxdb_port == 8087
        assert config.grafana_password == "secret"
        assert config.influxdb_token == "custom-token"
        assert config.deployed_to == "dgx01"


class TestMonitoringConfigManager:
    """Tests for MonitoringConfigManager CRUD."""

    def test_add_and_get(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)

        config = MonitoringStackConfig(
            name="test-stack",
            scrape_targets=["localhost:9100"],
            local_dir="/tmp/test",
        )
        manager.add(config)

        retrieved = manager.get("test-stack")
        assert retrieved is not None
        assert retrieved.name == "test-stack"
        assert retrieved.scrape_targets == ["localhost:9100"]
        assert retrieved.local_dir == "/tmp/test"

    def test_get_nonexistent(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)
        assert manager.get("nonexistent") is None

    def test_remove(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)

        config = MonitoringStackConfig(name="to-remove")
        manager.add(config)
        assert manager.get("to-remove") is not None

        assert manager.remove("to-remove") is True
        assert manager.get("to-remove") is None

    def test_remove_nonexistent(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)
        assert manager.remove("nonexistent") is False

    def test_list_stacks(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)

        manager.add(MonitoringStackConfig(name="stack-a"))
        manager.add(MonitoringStackConfig(name="stack-b"))

        stacks = manager.list_stacks()
        assert len(stacks) == 2
        names = {s.name for s in stacks}
        assert names == {"stack-a", "stack-b"}

    def test_list_stacks_empty(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)
        assert manager.list_stacks() == []

    def test_add_updates_existing(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        manager = MonitoringConfigManager(config_path)

        manager.add(MonitoringStackConfig(name="stack", grafana_port=3000))
        manager.add(MonitoringStackConfig(name="stack", grafana_port=3001))

        stacks = manager.list_stacks()
        assert len(stacks) == 1
        assert stacks[0].grafana_port == 3001
