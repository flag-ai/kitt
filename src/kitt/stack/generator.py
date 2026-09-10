"""Stack generator — creates customized docker-compose stacks."""

import json
import logging
import shutil
from pathlib import Path

import yaml

from kitt.stack.config import StackConfig, StackConfigManager

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_STACKS_DIR = Path.home() / ".kitt" / "stacks"


class StackGenerator:
    """Generates a composable docker-compose deployment stack."""

    def __init__(
        self,
        config: StackConfig,
        stacks_dir: Path | None = None,
        config_manager: StackConfigManager | None = None,
    ) -> None:
        self.config = config
        self.stacks_dir = stacks_dir or DEFAULT_STACKS_DIR
        self.config_manager = config_manager or StackConfigManager()

    def generate(self) -> Path:
        """Generate the stack directory.

        Returns:
            Path to the generated stack directory.
        """
        stack_dir = self.stacks_dir / self.config.name
        stack_dir.mkdir(parents=True, exist_ok=True)

        compose = self._build_compose()
        compose_path = stack_dir / "docker-compose.yaml"
        compose_path.write_text(
            yaml.dump(compose, default_flow_style=False, sort_keys=False)
        )

        self._generate_env_file(stack_dir)
        self._copy_dockerfiles(stack_dir)

        if self.config.monitoring:
            self._generate_monitoring_configs(stack_dir)

        self.config.local_dir = str(stack_dir)
        self.config_manager.add(self.config)

        logger.info(f"Generated stack at {stack_dir}")
        return stack_dir

    def _build_compose(self) -> dict:
        """Merge service and volume dicts from enabled components."""
        services: dict = {}
        volumes: dict = {}

        if self.config.web:
            svc, vol = self._web_service()
            services.update(svc)
            volumes.update(vol)

        if self.config.reporting:
            svc, vol = self._reporting_service()
            services.update(svc)
            volumes.update(vol)

        if self.config.postgres:
            svc, vol = self._postgres_service()
            services.update(svc)
            volumes.update(vol)

        if self.config.agent:
            svc, vol = self._agent_service()
            services.update(svc)
            volumes.update(vol)

        if self.config.monitoring:
            svc, vol = self._monitoring_services()
            services.update(svc)
            volumes.update(vol)

        # Wire up postgres dependency
        if self.config.postgres:
            web_key = "kitt-web" if self.config.web else None
            if not web_key and self.config.reporting:
                web_key = "kitt-reporting"
            if web_key and web_key in services:
                deps = services[web_key].get("depends_on", {})
                deps["postgres"] = {"condition": "service_healthy"}
                services[web_key]["depends_on"] = deps
                env = services[web_key].get("environment", [])
                env.append(
                    "DATABASE_URL=postgresql://kitt:${POSTGRES_PASSWORD}"
                    "@postgres:5432/kitt"
                )
                services[web_key]["environment"] = env

        compose: dict = {"services": services}
        if volumes:
            compose["volumes"] = volumes
        return compose

    def _web_service(self) -> tuple[dict, dict]:
        """Web UI + REST API service."""
        suffix = self.config.name
        services = {
            "kitt-web": {
                "build": {
                    "context": ".",
                    "dockerfile": "Dockerfile.web",
                },
                "container_name": f"kitt-web-{suffix}",
                "ports": [f"{self.config.web_port}:8080"],
                "volumes": [
                    "kitt-data:/data",
                    "kitt-certs:/root/.kitt/certs",
                    "kitt-results:/app/kitt-results",
                ],
                "environment": [
                    "KITT_SECRET_KEY=${KITT_SECRET_KEY}",
                    "KITT_AUTH_TOKEN=${KITT_AUTH_TOKEN}",
                ],
                "restart": "unless-stopped",
                "healthcheck": {
                    "test": [
                        "CMD",
                        "curl",
                        "-f",
                        "-k",
                        "https://localhost:8080/api/v1/health",
                    ],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                    "start_period": "10s",
                },
            }
        }
        volumes = {
            "kitt-data": None,
            "kitt-certs": None,
            "kitt-results": None,
        }
        return services, volumes

    def _reporting_service(self) -> tuple[dict, dict]:
        """Lightweight read-only reporting dashboard."""
        suffix = self.config.name
        services = {
            "kitt-reporting": {
                "build": {
                    "context": ".",
                    "dockerfile": "Dockerfile.web",
                },
                "container_name": f"kitt-reporting-{suffix}",
                "command": ["--host", "0.0.0.0", "--port", "8080", "--legacy"],
                "ports": [f"{self.config.web_port}:8080"],
                "volumes": [
                    "kitt-data:/data",
                    "kitt-results:/app/kitt-results",
                ],
                "environment": [
                    "KITT_AUTH_TOKEN=${KITT_AUTH_TOKEN}",
                ],
                "restart": "unless-stopped",
                "healthcheck": {
                    "test": [
                        "CMD",
                        "curl",
                        "-f",
                        "http://localhost:8080/api/v1/health",
                    ],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 3,
                    "start_period": "10s",
                },
            }
        }
        volumes = {
            "kitt-data": None,
            "kitt-results": None,
        }
        return services, volumes

    def _agent_service(self) -> tuple[dict, dict]:
        """Agent daemon for GPU servers."""
        suffix = self.config.name
        services = {
            "kitt-agent": {
                "build": {
                    "context": ".",
                    "dockerfile": "Dockerfile.agent",
                },
                "container_name": f"kitt-agent-{suffix}",
                "ports": [f"{self.config.agent_port}:8090"],
                "volumes": [
                    "/var/run/docker.sock:/var/run/docker.sock",
                ],
                "environment": [
                    "KITT_AUTH_TOKEN=${KITT_AUTH_TOKEN}",
                    "KITT_SERVER_URL=${KITT_SERVER_URL}",
                ],
                "restart": "unless-stopped",
                "deploy": {
                    "resources": {
                        "reservations": {
                            "devices": [
                                {
                                    "driver": "nvidia",
                                    "count": "all",
                                    "capabilities": ["gpu"],
                                }
                            ]
                        }
                    }
                },
            }
        }
        volumes: dict = {}
        return services, volumes

    def _postgres_service(self) -> tuple[dict, dict]:
        """PostgreSQL database service."""
        suffix = self.config.name
        services = {
            "postgres": {
                "image": "postgres:16-alpine",
                "container_name": f"kitt-postgres-{suffix}",
                "environment": [
                    "POSTGRES_DB=kitt",
                    "POSTGRES_USER=kitt",
                    "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}",
                ],
                "volumes": [
                    "postgres-data:/var/lib/postgresql/data",
                ],
                "ports": [f"{self.config.postgres_port}:5432"],
                "restart": "unless-stopped",
                "healthcheck": {
                    "test": ["CMD-SHELL", "pg_isready -U kitt"],
                    "interval": "10s",
                    "timeout": "5s",
                    "retries": 5,
                },
            }
        }
        volumes = {"postgres-data": None}
        return services, volumes

    def _monitoring_services(self) -> tuple[dict, dict]:
        """Prometheus + Grafana + InfluxDB monitoring stack."""
        suffix = self.config.name
        services = {
            "prometheus": {
                "image": "prom/prometheus:latest",
                "container_name": f"kitt-prometheus-{suffix}",
                "volumes": [
                    "./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro",
                    "prometheus_data:/prometheus",
                ],
                "ports": [f"{self.config.prometheus_port}:9090"],
                "restart": "unless-stopped",
            },
            "grafana": {
                "image": "grafana/grafana:latest",
                "container_name": f"kitt-grafana-{suffix}",
                "environment": [
                    "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}",
                    "GF_SECURITY_ADMIN_USER=admin",
                    "GF_USERS_ALLOW_SIGN_UP=false",
                ],
                "volumes": [
                    "grafana_data:/var/lib/grafana",
                    "./grafana/provisioning:/etc/grafana/provisioning:ro",
                    "./grafana/dashboards:/var/lib/grafana/dashboards:ro",
                ],
                "ports": [f"{self.config.grafana_port}:3000"],
                "depends_on": ["prometheus"],
                "restart": "unless-stopped",
            },
            "influxdb": {
                "image": "influxdb:2",
                "container_name": f"kitt-influxdb-{suffix}",
                "environment": [
                    "DOCKER_INFLUXDB_INIT_MODE=setup",
                    "DOCKER_INFLUXDB_INIT_USERNAME=kitt",
                    "DOCKER_INFLUXDB_INIT_PASSWORD=${INFLUXDB_PASSWORD}",
                    "DOCKER_INFLUXDB_INIT_ORG=kitt",
                    "DOCKER_INFLUXDB_INIT_BUCKET=benchmarks",
                    f"DOCKER_INFLUXDB_INIT_ADMIN_TOKEN={self.config.influxdb_token}",
                ],
                "volumes": ["influxdb_data:/var/lib/influxdb2"],
                "ports": [f"{self.config.influxdb_port}:8086"],
                "restart": "unless-stopped",
            },
        }
        volumes = {
            "prometheus_data": None,
            "grafana_data": None,
            "influxdb_data": None,
        }
        return services, volumes

    def _generate_env_file(self, stack_dir: Path) -> None:
        """Write secrets to .env file."""
        lines = [
            f"KITT_AUTH_TOKEN={self.config.auth_token}",
            f"KITT_SECRET_KEY={self.config.secret_key}",
        ]
        if self.config.postgres:
            lines.append(f"POSTGRES_PASSWORD={self.config.postgres_password}")
        if self.config.monitoring:
            lines.append(f"INFLUXDB_PASSWORD={self.config.influxdb_token}")
            lines.append(f"GRAFANA_PASSWORD={self.config.grafana_password}")
        if self.config.agent and self.config.server_url:
            lines.append(f"KITT_SERVER_URL={self.config.server_url}")
        env_path = stack_dir / ".env"
        env_path.write_text("\n".join(lines) + "\n")
        env_path.chmod(0o600)

    def _copy_dockerfiles(self, stack_dir: Path) -> None:
        """Copy needed Dockerfiles into the stack directory."""
        if self.config.web or self.config.reporting:
            src = _find_dockerfile("docker/web/Dockerfile")
            if src:
                shutil.copy2(src, stack_dir / "Dockerfile.web")

    def _generate_monitoring_configs(self, stack_dir: Path) -> None:
        """Generate Prometheus and Grafana configs for monitoring component."""
        # Prometheus config
        prom_dir = stack_dir / "prometheus"
        prom_dir.mkdir(parents=True, exist_ok=True)

        # Scrape the web/reporting service if present
        targets = []
        if self.config.web:
            targets.append("kitt-web:8080")
        elif self.config.reporting:
            targets.append("kitt-reporting:8080")
        if self.config.agent:
            targets.append("kitt-agent:8090")
        if not targets:
            targets = ["localhost:9100"]

        prom_config = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s",
            },
            "scrape_configs": [
                {
                    "job_name": f"kitt-{self.config.name}",
                    "static_configs": [{"targets": targets}],
                    "metrics_path": "/metrics",
                    "scrape_interval": "10s",
                }
            ],
        }
        (prom_dir / "prometheus.yml").write_text(
            yaml.dump(prom_config, default_flow_style=False, sort_keys=False)
        )

        # Grafana provisioning — datasources
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
                    "secureJsonData": {"token": self.config.influxdb_token},
                    "editable": False,
                },
            ],
        }
        (ds_dir / "datasource.yaml").write_text(
            yaml.dump(datasource, default_flow_style=False, sort_keys=False)
        )

        # Grafana provisioning — dashboards
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

        # Placeholder dashboard
        dashboards_dir = stack_dir / "grafana" / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        placeholder = {
            "annotations": {"list": []},
            "editable": True,
            "panels": [],
            "schemaVersion": 39,
            "tags": ["kitt"],
            "title": f"KITT {self.config.name}",
            "uid": f"kitt-{self.config.name}",
        }
        (dashboards_dir / "overview.json").write_text(
            json.dumps(placeholder, indent=2) + "\n"
        )


def _find_dockerfile(relative_path: str) -> Path | None:
    """Locate a Dockerfile relative to the project root."""
    # Try relative to this file (installed package)
    candidate = PROJECT_ROOT / relative_path
    if candidate.exists():
        return candidate

    # Try current working directory
    cwd_candidate = Path.cwd() / relative_path
    if cwd_candidate.exists():
        return cwd_candidate

    return None
