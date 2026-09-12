"""SSH-based deployment for monitoring stacks."""

import logging

from kitt.monitoring.config import MonitoringConfigManager, MonitoringStackConfig
from kitt.remote.host_config import HostConfig
from kitt.remote.ssh_connection import SSHConnection

logger = logging.getLogger(__name__)


class MonitoringDeployer:
    """Deploy and manage monitoring stacks on remote hosts."""

    def __init__(
        self,
        host_config: HostConfig,
        config_manager: MonitoringConfigManager | None = None,
    ) -> None:
        self.host_config = host_config
        self.config_manager = config_manager or MonitoringConfigManager()
        self.ssh = SSHConnection(
            host=host_config.hostname,
            user=host_config.user or None,
            ssh_key=host_config.ssh_key or None,
            port=host_config.port,
        )

    def deploy(self, stack_config: MonitoringStackConfig) -> bool:
        """Deploy a monitoring stack to the remote host.

        Args:
            stack_config: The stack configuration to deploy.

        Returns:
            True if deployment succeeded.
        """
        if not self.ssh.check_connection():
            logger.error(f"Cannot connect to {self.host_config.hostname}")
            return False

        remote_dir = f"~/kitt-monitoring/{stack_config.name}"

        # Create remote directory
        rc, _, stderr = self.ssh.run_command(f"mkdir -p {remote_dir}")
        if rc != 0:
            logger.error(f"Failed to create remote directory: {stderr}")
            return False

        # Upload stack files via scp -r
        local_dir = stack_config.local_dir
        if not local_dir:
            logger.error("Stack has no local directory")
            return False

        success = self._upload_directory(local_dir, remote_dir)
        if not success:
            logger.error("Failed to upload stack files")
            return False

        # Start the stack
        rc, stdout, stderr = self.ssh.run_command(
            f"cd {remote_dir} && docker compose up -d",
            timeout=120,
        )
        if rc != 0:
            logger.error(f"Failed to start remote stack: {stderr}")
            return False

        # Update config with deployment info
        stack_config.deployed_to = self.host_config.name
        stack_config.remote_dir = remote_dir
        self.config_manager.add(stack_config)

        logger.info(
            f"Stack '{stack_config.name}' deployed to {self.host_config.hostname}"
        )
        return True

    def start(self, remote_dir: str) -> tuple[int, str, str]:
        """Start a deployed monitoring stack.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        return self.ssh.run_command(
            f"cd {remote_dir} && docker compose up -d",
            timeout=120,
        )

    def stop(self, remote_dir: str) -> tuple[int, str, str]:
        """Stop a deployed monitoring stack.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        return self.ssh.run_command(
            f"cd {remote_dir} && docker compose down",
            timeout=120,
        )

    def status(self, remote_dir: str) -> tuple[int, str, str]:
        """Check status of a deployed monitoring stack.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        return self.ssh.run_command(
            f"cd {remote_dir} && docker compose ps --format table",
            timeout=30,
        )

    def _upload_directory(self, local_dir: str, remote_dir: str) -> bool:
        """Upload a directory via scp -r.

        Uses the SSHConnection's underlying SSH settings for auth.
        """
        import subprocess

        args = [
            "scp",
            "-r",
            "-o",
            "BatchMode=yes",
            "-P",
            str(self.ssh.port),
        ]
        if self.ssh.ssh_key:
            args.extend(["-i", self.ssh.ssh_key])
        # Upload contents of local_dir into remote_dir
        args.extend([f"{local_dir}/.", f"{self.ssh.target}:{remote_dir}"])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=300)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Directory upload failed: {e}")
            return False
