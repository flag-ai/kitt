"""Monitoring stack generator — creates customized docker-compose stacks."""

import json
import logging
import secrets
import shutil
from pathlib import Path

import yaml

from kitt.monitoring.config import MonitoringConfigManager, MonitoringStackConfig

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "docker" / "monitoring"
DEFAULT_STACKS_DIR = Path.home() / ".kitt" / "monitoring"


class MonitoringStackGenerator:
    """Generates a tailored docker-compose monitoring stack."""

    def __init__(
        self,
        name: str,
        scrape_targets: list[str],
        grafana_port: int = 3000,
        prometheus_port: int = 9090,
        influxdb_port: int = 8086,
        grafana_password: str = "",
        influxdb_token: str = "",
        stacks_dir: Path | None = None,
        config_manager: MonitoringConfigManager | None = None,
    ) -> None:
        self.name = name
        self.scrape_targets = scrape_targets
        self.grafana_port = grafana_port
        self.prometheus_port = prometheus_port
        self.influxdb_port = influxdb_port
        self.grafana_password = grafana_password or secrets.token_urlsafe(16)
        self.influxdb_token = influxdb_token or secrets.token_hex(32)
        self.stacks_dir = stacks_dir or DEFAULT_STACKS_DIR
        self.config_manager = config_manager or MonitoringConfigManager()

    def generate(self) -> Path:
        """Generate the monitoring stack directory.

        Returns:
            Path to the generated stack directory.
        """
        stack_dir = self.stacks_dir / self.name
        stack_dir.mkdir(parents=True, exist_ok=True)

        self._generate_docker_compose(stack_dir)
        self._generate_prometheus_config(stack_dir)
        self._copy_grafana_files(stack_dir)

        config = MonitoringStackConfig(
            name=self.name,
            scrape_targets=self.scrape_targets,
            local_dir=str(stack_dir),
            grafana_port=self.grafana_port,
            prometheus_port=self.prometheus_port,
            influxdb_port=self.influxdb_port,
            grafana_password=self.grafana_password,
            influxdb_token=self.influxdb_token,
        )
        self.config_manager.add(config)

        logger.info(f"Generated monitoring stack at {stack_dir}")
        return stack_dir

    def _generate_docker_compose(self, stack_dir: Path) -> None:
        """Generate docker-compose.yaml with custom ports and container names."""
        suffix = self.name
        compose = {
            "version": "3.8",
            "services": {
                "prometheus": {
                    "image": "prom/prometheus:latest",
                    "container_name": f"kitt-prometheus-{suffix}",
                    "volumes": [
                        "./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
                        "prometheus_data:/prometheus",
                    ],
                    "ports": [f"{self.prometheus_port}:9090"],
                    "restart": "unless-stopped",
                },
                "grafana": {
                    "image": "grafana/grafana:latest",
                    "container_name": f"kitt-grafana-{suffix}",
                    "environment": [
                        f"GF_SECURITY_ADMIN_PASSWORD={self.grafana_password}",
                        "GF_SECURITY_ADMIN_USER=admin",
                        "GF_USERS_ALLOW_SIGN_UP=false",
                    ],
                    "volumes": [
                        "grafana_data:/var/lib/grafana",
                        "./grafana/provisioning:/etc/grafana/provisioning:ro",
                        "./grafana/dashboards:/var/lib/grafana/dashboards:ro",
                    ],
                    "ports": [f"{self.grafana_port}:3000"],
                    "depends_on": ["prometheus"],
                    "restart": "unless-stopped",
                },
                "influxdb": {
                    "image": "influxdb:2",
                    "container_name": f"kitt-influxdb-{suffix}",
                    "environment": [
                        "DOCKER_INFLUXDB_INIT_MODE=setup",
                        "DOCKER_INFLUXDB_INIT_USERNAME=kitt",
                        f"DOCKER_INFLUXDB_INIT_PASSWORD={self.influxdb_token}",
                        "DOCKER_INFLUXDB_INIT_ORG=kitt",
                        "DOCKER_INFLUXDB_INIT_BUCKET=benchmarks",
                        f"DOCKER_INFLUXDB_INIT_ADMIN_TOKEN={self.influxdb_token}",
                    ],
                    "volumes": ["influxdb_data:/var/lib/influxdb2"],
                    "ports": [f"{self.influxdb_port}:8086"],
                    "restart": "unless-stopped",
                },
            },
            "volumes": {
                "prometheus_data": None,
                "grafana_data": None,
                "influxdb_data": None,
            },
        }

        compose_path = stack_dir / "docker-compose.yaml"
        compose_path.write_text(
            yaml.dump(compose, default_flow_style=False, sort_keys=False)
        )

    def _generate_prometheus_config(self, stack_dir: Path) -> None:
        """Generate prometheus.yml with dynamic scrape targets."""
        prom_dir = stack_dir / "prometheus"
        prom_dir.mkdir(parents=True, exist_ok=True)

        targets = self.scrape_targets if self.scrape_targets else ["localhost:9100"]
        config = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s",
            },
            "scrape_configs": [
                {
                    "job_name": f"kitt-{self.name}",
                    "static_configs": [{"targets": targets}],
                    "metrics_path": "/metrics",
                    "scrape_interval": "10s",
                }
            ],
        }

        prom_path = prom_dir / "prometheus.yml"
        prom_path.write_text(
            yaml.dump(config, default_flow_style=False, sort_keys=False)
        )

    def _copy_grafana_files(self, stack_dir: Path) -> None:
        """Copy Grafana provisioning and dashboard files from template."""
        template_dir = _find_template_dir()
        if not template_dir:
            logger.warning(
                "Template directory not found — generating minimal Grafana config"
            )
            self._generate_minimal_grafana(stack_dir)
            return

        grafana_src = template_dir / "grafana"
        grafana_dst = stack_dir / "grafana"

        if grafana_src.exists():
            if grafana_dst.exists():
                shutil.rmtree(grafana_dst)
            shutil.copytree(grafana_src, grafana_dst)
        else:
            self._generate_minimal_grafana(stack_dir)

    def _generate_minimal_grafana(self, stack_dir: Path) -> None:
        """Generate minimal Grafana provisioning when templates are unavailable."""
        # Provisioning — datasources
        ds_dir = stack_dir / "grafana" / "provisioning" / "datasources"
        ds_dir.mkdir(parents=True, exist_ok=True)
        datasource = {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": "Prometheus",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prometheus:9090",
                    "isDefault": True,
                    "editable": False,
                },
                {
                    "name": "InfluxDB",
                    "type": "influxdb",
                    "access": "proxy",
                    "url": "http://influxdb:8086",
                    "jsonData": {
                        "version": "Flux",
                        "organization": "kitt",
                        "defaultBucket": "benchmarks",
                    },
                    "secureJsonData": {"token": self.influxdb_token},
                    "editable": False,
                },
            ],
        }
        (ds_dir / "datasource.yaml").write_text(
            yaml.dump(datasource, default_flow_style=False, sort_keys=False)
        )

        # Provisioning — dashboards
        db_prov_dir = stack_dir / "grafana" / "provisioning" / "dashboards"
        db_prov_dir.mkdir(parents=True, exist_ok=True)
        dashboard_prov = {
            "apiVersion": 1,
            "providers": [
                {
                    "name": "KITT Dashboards",
                    "orgId": 1,
                    "folder": "KITT",
                    "type": "file",
                    "disableDeletion": False,
                    "editable": True,
                    "options": {
                        "path": "/var/lib/grafana/dashboards",
                        "foldersFromFilesStructure": False,
                    },
                }
            ],
        }
        (db_prov_dir / "dashboard.yaml").write_text(
            yaml.dump(dashboard_prov, default_flow_style=False, sort_keys=False)
        )

        # Empty dashboards directory
        dashboards_dir = stack_dir / "grafana" / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        # Write a minimal placeholder dashboard
        placeholder = {
            "annotations": {"list": []},
            "editable": True,
            "panels": [],
            "schemaVersion": 39,
            "tags": ["kitt"],
            "title": f"KITT {self.name}",
            "uid": f"kitt-{self.name}",
        }
        (dashboards_dir / "campaign-overview.json").write_text(
            json.dumps(placeholder, indent=2) + "\n"
        )


def _find_template_dir() -> Path | None:
    """Find the docker/monitoring template directory."""
    # Try relative to this file (installed package)
    if TEMPLATE_DIR.exists():
        return TEMPLATE_DIR

    # Try current working directory
    cwd_path = Path.cwd() / "docker" / "monitoring"
    if cwd_path.exists():
        return cwd_path

    return None
