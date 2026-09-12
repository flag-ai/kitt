"""Tests for stack generator."""

from pathlib import Path

import yaml

from kitt.stack.config import StackConfig, StackConfigManager
from kitt.stack.generator import StackGenerator


class TestStackGenerator:
    """Tests for StackGenerator."""

    def _make_generator(
        self,
        tmp_path: Path,
        name: str = "test-stack",
        **kwargs,
    ) -> StackGenerator:
        stacks_dir = tmp_path / "stacks"
        config_path = tmp_path / "stacks.yaml"
        config_manager = StackConfigManager(config_path)
        config = StackConfig(name=name, **kwargs)
        return StackGenerator(
            config=config,
            stacks_dir=stacks_dir,
            config_manager=config_manager,
        )

    def test_web_only(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True)
        stack_dir = gen.generate()

        assert stack_dir.exists()
        assert (stack_dir / "docker-compose.yaml").exists()
        assert (stack_dir / ".env").exists()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        assert "kitt-web" in compose["services"]
        assert "kitt-reporting" not in compose["services"]
        assert "kitt-agent" not in compose["services"]
        assert "postgres" not in compose["services"]

    def test_reporting_only(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, reporting=True)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        assert "kitt-reporting" in compose["services"]
        assert "kitt-web" not in compose["services"]
        # Reporting uses --legacy command override
        svc = compose["services"]["kitt-reporting"]
        assert "--legacy" in svc["command"]

    def test_agent_only(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, agent=True)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        assert "kitt-agent" in compose["services"]
        svc = compose["services"]["kitt-agent"]
        # GPU reservation
        assert "deploy" in svc
        assert "resources" in svc["deploy"]
        # Docker socket mount
        assert "/var/run/docker.sock:/var/run/docker.sock" in svc["volumes"]

    def test_web_with_postgres(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True, postgres=True)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]

        assert "kitt-web" in services
        assert "postgres" in services

        # Web should depend on postgres
        web_deps = services["kitt-web"].get("depends_on", {})
        assert "postgres" in web_deps
        assert web_deps["postgres"]["condition"] == "service_healthy"

        # Web should have DATABASE_URL
        env = services["kitt-web"]["environment"]
        db_urls = [e for e in env if e.startswith("DATABASE_URL=")]
        assert len(db_urls) == 1

        # Postgres healthcheck uses pg_isready
        pg_health = services["postgres"]["healthcheck"]
        assert "pg_isready" in pg_health["test"][1]

    def test_reporting_with_postgres(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, reporting=True, postgres=True)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]

        # Reporting should depend on postgres
        reporting_deps = services["kitt-reporting"].get("depends_on", {})
        assert "postgres" in reporting_deps

    def test_full_stack(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path, web=True, agent=True, postgres=True, monitoring=True
        )
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]

        assert "kitt-web" in services
        assert "kitt-agent" in services
        assert "postgres" in services
        assert "prometheus" in services
        assert "grafana" in services
        assert "influxdb" in services

        # Monitoring config files should exist
        assert (stack_dir / "prometheus" / "prometheus.yml").exists()
        assert (stack_dir / "grafana" / "provisioning").exists()

    def test_custom_ports(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path,
            web=True,
            postgres=True,
            monitoring=True,
            web_port=9000,
            postgres_port=5433,
            grafana_port=3001,
            prometheus_port=9091,
            influxdb_port=8087,
        )
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]

        assert "9000:8080" in services["kitt-web"]["ports"]
        assert "5433:5432" in services["postgres"]["ports"]
        assert "3001:3000" in services["grafana"]["ports"]
        assert "9091:9090" in services["prometheus"]["ports"]
        assert "8087:8086" in services["influxdb"]["ports"]

    def test_container_name_suffixes(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path,
            name="prod",
            web=True,
            postgres=True,
            monitoring=True,
        )
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        services = compose["services"]

        assert services["kitt-web"]["container_name"] == "kitt-web-prod"
        assert services["postgres"]["container_name"] == "kitt-postgres-prod"
        assert services["prometheus"]["container_name"] == "kitt-prometheus-prod"
        assert services["grafana"]["container_name"] == "kitt-grafana-prod"
        assert services["influxdb"]["container_name"] == "kitt-influxdb-prod"

    def test_env_file_generation(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path,
            web=True,
            postgres=True,
            auth_token="mytoken",
            secret_key="mysecret",
            postgres_password="strongpw",
        )
        stack_dir = gen.generate()

        env_content = (stack_dir / ".env").read_text()
        assert "KITT_AUTH_TOKEN=mytoken" in env_content
        assert "KITT_SECRET_KEY=mysecret" in env_content
        assert "POSTGRES_PASSWORD=strongpw" in env_content

    def test_env_file_agent_server_url(self, tmp_path: Path):
        gen = self._make_generator(
            tmp_path,
            agent=True,
            server_url="https://server:8080",
        )
        stack_dir = gen.generate()

        env_content = (stack_dir / ".env").read_text()
        assert "KITT_SERVER_URL=https://server:8080" in env_content

    def test_config_registration(self, tmp_path: Path):
        config_path = tmp_path / "stacks.yaml"
        config_manager = StackConfigManager(config_path)
        config = StackConfig(name="registered", web=True)
        gen = StackGenerator(
            config=config,
            stacks_dir=tmp_path / "stacks",
            config_manager=config_manager,
        )
        gen.generate()

        retrieved = config_manager.get("registered")
        assert retrieved is not None
        assert retrieved.name == "registered"
        assert retrieved.web is True
        assert retrieved.local_dir != ""

    def test_monitoring_config_files(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True, monitoring=True)
        stack_dir = gen.generate()

        # Prometheus config
        prom_config = yaml.safe_load(
            (stack_dir / "prometheus" / "prometheus.yml").read_text()
        )
        assert prom_config["scrape_configs"][0]["job_name"] == "kitt-test-stack"
        targets = prom_config["scrape_configs"][0]["static_configs"][0]["targets"]
        assert "kitt-web:8080" in targets

        # Grafana provisioning
        assert (
            stack_dir / "grafana" / "provisioning" / "datasources" / "datasource.yaml"
        ).exists()
        assert (
            stack_dir / "grafana" / "provisioning" / "dashboards" / "dashboard.yaml"
        ).exists()
        assert (stack_dir / "grafana" / "dashboards" / "overview.json").exists()

    def test_idempotent(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True)
        stack_dir1 = gen.generate()
        stack_dir2 = gen.generate()
        assert stack_dir1 == stack_dir2
        assert (stack_dir2 / "docker-compose.yaml").exists()

    def test_agent_custom_port(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, agent=True, agent_port=9999)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        assert "9999:8090" in compose["services"]["kitt-agent"]["ports"]

    def test_no_monitoring_dir_without_flag(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True)
        stack_dir = gen.generate()

        assert not (stack_dir / "prometheus").exists()
        assert not (stack_dir / "grafana").exists()

    def test_volumes_merged(self, tmp_path: Path):
        gen = self._make_generator(tmp_path, web=True, postgres=True, monitoring=True)
        stack_dir = gen.generate()

        compose = yaml.safe_load((stack_dir / "docker-compose.yaml").read_text())
        volumes = compose.get("volumes", {})
        assert "kitt-data" in volumes
        assert "kitt-certs" in volumes
        assert "kitt-results" in volumes
        assert "postgres-data" in volumes
        assert "prometheus_data" in volumes
        assert "grafana_data" in volumes
        assert "influxdb_data" in volumes
