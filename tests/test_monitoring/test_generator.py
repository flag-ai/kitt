"""Tests for monitoring stack generator."""

from pathlib import Path

import yaml

from kitt.monitoring.config import MonitoringConfigManager
from kitt.monitoring.generator import MonitoringStackGenerator


class TestMonitoringStackGenerator:
    """Tests for MonitoringStackGenerator."""

    def _make_generator(
        self,
        tmp_path: Path,
        name: str = "test-stack",
        targets: list[str] | None = None,
        **kwargs,
    ) -> MonitoringStackGenerator:
        stacks_dir = tmp_path / "stacks"
        config_path = tmp_path / "monitoring.yaml"
        config_manager = MonitoringConfigManager(config_path)
        return MonitoringStackGenerator(
            name=name,
            scrape_targets=targets or ["192.168.1.10:9100"],
            stacks_dir=stacks_dir,
            config_manager=config_manager,
            **kwargs,
        )

    def test_generate_creates_directory_structure(self, tmp_path: Path):
        gen = self._make_generator(tmp_path)
        stack_dir = gen.generate()

        assert stack_dir.exists()
        assert (stack_dir / "docker-compose.yaml").exists()
        assert (stack_dir / "prometheus" / "prometheus.yml").exists()
        assert (stack_dir / "grafana").exists()

    def test_generate_prometheus_targets(self, tmp_path: Path):
        targets = ["192.168.1.10:9100", "192.168.1.11:9100", "10.0.0.5:9100"]
        gen = self._make_generator(tmp_path, targets=targets)
        stack_dir = gen.generate()

        prom_config = yaml.safe_load(
            (stack_dir / "prometheus" / "prometheus.yml").read_text()
        )
        scrape_targets = prom_config["scrape_configs"][0]["static_configs"][0][
            "targets"
        ]
        assert scrape_targets == targets

    def test_generate_custom_ports(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path,
            grafana_port=3001,
            prometheus_port=9091,
            influxdb_port=8087,
        )
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]
        assert "3001:3000" in services["grafana"]["ports"]
        assert "9091:9090" in services["prometheus"]["ports"]
        assert "8087:8086" in services["influxdb"]["ports"]

    def test_generate_container_names_suffixed(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, name="dgx01")
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]
        assert services["prometheus"]["container_name"] == "kitt-prometheus-dgx01"
        assert services["grafana"]["container_name"] == "kitt-grafana-dgx01"
        assert services["influxdb"]["container_name"] == "kitt-influxdb-dgx01"

    def test_generate_registers_config(self, tmp_path: Path):
        config_path = tmp_path / "monitoring.yaml"
        config_manager = MonitoringConfigManager(config_path)
        gen = MonitoringStackGenerator(
            name="registered",
            scrape_targets=["localhost:9100"],
            stacks_dir=tmp_path / "stacks",
            config_manager=config_manager,
        )
        gen.generate()

        config = config_manager.get("registered")
        assert config is not None
        assert config.name == "registered"
        assert config.scrape_targets == ["localhost:9100"]
        assert config.local_dir != ""

    def test_generate_prometheus_job_name(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, name="mylab")
        stack_dir = gen.generate()

        prom_config = yaml.safe_load(
            (stack_dir / "prometheus" / "prometheus.yml").read_text()
        )
        assert prom_config["scrape_configs"][0]["job_name"] == "kitt-mylab"

    def test_generate_grafana_provisioning(self, tmp_path: Path):
        gen = self._make_generator(tmp_path)
        stack_dir = gen.generate()

        # Should have at least provisioning directories
        grafana_dir = stack_dir / "grafana"
        assert grafana_dir.exists()
        # Either copied from template or generated minimally
        provisioning = grafana_dir / "provisioning"
        assert provisioning.exists()

    def test_generate_idempotent(self, tmp_path: Path):
        gen = self._make_generator(tmp_path)
        stack_dir1 = gen.generate()
        stack_dir2 = gen.generate()
        assert stack_dir1 == stack_dir2
        assert (stack_dir2 / "docker-compose.yaml").exists()

    def test_generate_default_targets(self, tmp_path: Path):
        """When no targets provided, uses localhost:9100."""
        stacks_dir = tmp_path / "stacks"
        config_path = tmp_path / "monitoring.yaml"
        config_manager = MonitoringConfigManager(config_path)
        gen = MonitoringStackGenerator(
            name="empty-targets",
            scrape_targets=[],
            stacks_dir=stacks_dir,
            config_manager=config_manager,
        )
        stack_dir = gen.generate()

        prom_config = yaml.safe_load(
            (stack_dir / "prometheus" / "prometheus.yml").read_text()
        )
        targets = prom_config["scrape_configs"][0]["static_configs"][0]["targets"]
        assert targets == ["localhost:9100"]
