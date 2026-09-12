"""Tests for monitoring stack deployer."""

from pathlib import Path
from unittest.mock import patch

from kitt.monitoring.config import MonitoringConfigManager, MonitoringStackConfig
from kitt.monitoring.deployer import MonitoringDeployer
from kitt.remote.host_config import HostConfig


def _make_host_config() -> HostConfig:
    return HostConfig(
        name="testhost",
        hostname="192.168.1.100",
        user="admin",
        port=22,
    )


def _make_stack_config(tmp_path: Path) -> MonitoringStackConfig:
    local_dir = tmp_path / "stack"
    local_dir.mkdir(parents=True, exist_ok=True)
    (local_dir / "docker-compose.yaml").write_text("version: '3.8'")
    return MonitoringStackConfig(
        name="test-stack",
        scrape_targets=["localhost:9100"],
        local_dir=str(local_dir),
    )


class TestMonitoringDeployer:
    """Tests for MonitoringDeployer."""

    def test_deploy_checks_connection(self, tmp_path: Path):
        host_config = _make_host_config()
        config_manager = MonitoringConfigManager(tmp_path / "monitoring.yaml")
        deployer = MonitoringDeployer(host_config, config_manager)

        stack_config = _make_stack_config(tmp_path)

        with patch.object(deployer.ssh, "check_connection", return_value=False):
            result = deployer.deploy(stack_config)
            assert result is False

    def test_deploy_success(self, tmp_path: Path):
        host_config = _make_host_config()
        config_manager = MonitoringConfigManager(tmp_path / "monitoring.yaml")
        config_manager.add(
            MonitoringStackConfig(
                name="test-stack",
                scrape_targets=["localhost:9100"],
                local_dir=str(tmp_path / "stack"),
            )
        )
        deployer = MonitoringDeployer(host_config, config_manager)
        stack_config = _make_stack_config(tmp_path)

        with (
            patch.object(deployer.ssh, "check_connection", return_value=True),
            patch.object(deployer.ssh, "run_command", return_value=(0, "ok", "")),
            patch.object(deployer, "_upload_directory", return_value=True),
        ):
            result = deployer.deploy(stack_config)
            assert result is True

        # Verify config was updated with deployment info
        updated = config_manager.get("test-stack")
        assert updated is not None
        assert updated.deployed_to == "testhost"
        assert updated.remote_dir == "~/kitt-monitoring/test-stack"

    def test_deploy_fails_on_mkdir_error(self, tmp_path: Path):
        host_config = _make_host_config()
        config_manager = MonitoringConfigManager(tmp_path / "monitoring.yaml")
        deployer = MonitoringDeployer(host_config, config_manager)
        stack_config = _make_stack_config(tmp_path)

        with (
            patch.object(deployer.ssh, "check_connection", return_value=True),
            patch.object(
                deployer.ssh, "run_command", return_value=(1, "", "permission denied")
            ),
        ):
            result = deployer.deploy(stack_config)
            assert result is False

    def test_deploy_fails_on_upload_error(self, tmp_path: Path):
        host_config = _make_host_config()
        config_manager = MonitoringConfigManager(tmp_path / "monitoring.yaml")
        deployer = MonitoringDeployer(host_config, config_manager)
        stack_config = _make_stack_config(tmp_path)

        with (
            patch.object(deployer.ssh, "check_connection", return_value=True),
            patch.object(deployer.ssh, "run_command", return_value=(0, "ok", "")),
            patch.object(deployer, "_upload_directory", return_value=False),
        ):
            result = deployer.deploy(stack_config)
            assert result is False

    def test_start_calls_docker_compose_up(self, tmp_path: Path):
        host_config = _make_host_config()
        deployer = MonitoringDeployer(host_config)

        with patch.object(
            deployer.ssh, "run_command", return_value=(0, "started", "")
        ) as mock_run:
            rc, stdout, stderr = deployer.start("~/kitt-monitoring/test")
            assert rc == 0
            mock_run.assert_called_once_with(
                "cd ~/kitt-monitoring/test && docker compose up -d",
                timeout=120,
            )

    def test_stop_calls_docker_compose_down(self, tmp_path: Path):
        host_config = _make_host_config()
        deployer = MonitoringDeployer(host_config)

        with patch.object(
            deployer.ssh, "run_command", return_value=(0, "stopped", "")
        ) as mock_run:
            rc, stdout, stderr = deployer.stop("~/kitt-monitoring/test")
            assert rc == 0
            mock_run.assert_called_once_with(
                "cd ~/kitt-monitoring/test && docker compose down",
                timeout=120,
            )

    def test_status_calls_docker_compose_ps(self, tmp_path: Path):
        host_config = _make_host_config()
        deployer = MonitoringDeployer(host_config)

        with patch.object(
            deployer.ssh, "run_command", return_value=(0, "NAME  STATUS", "")
        ) as mock_run:
            rc, stdout, stderr = deployer.status("~/kitt-monitoring/test")
            assert rc == 0
            assert "STATUS" in stdout
            mock_run.assert_called_once_with(
                "cd ~/kitt-monitoring/test && docker compose ps --format table",
                timeout=30,
            )

    def test_deploy_no_local_dir(self, tmp_path: Path):
        host_config = _make_host_config()
        config_manager = MonitoringConfigManager(tmp_path / "monitoring.yaml")
        deployer = MonitoringDeployer(host_config, config_manager)

        stack_config = MonitoringStackConfig(name="no-dir", local_dir="")

        with (
            patch.object(deployer.ssh, "check_connection", return_value=True),
            patch.object(deployer.ssh, "run_command", return_value=(0, "ok", "")),
        ):
            result = deployer.deploy(stack_config)
            assert result is False
