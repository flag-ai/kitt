"""SSH connection wrapper for remote execution."""

import logging
import subprocess

logger = logging.getLogger(__name__)


class SSHConnection:
    """Wrapper around SSH subprocess calls for remote operations."""

    def __init__(
        self,
        host: str,
        user: str | None = None,
        ssh_key: str | None = None,
        port: int = 22,
        strict_host_key: bool = True,
    ) -> None:
        self.host = host
        self.user = user
        self.port = port
        self.ssh_key = ssh_key
        self.strict_host_key = strict_host_key

    @property
    def target(self) -> str:
        """Return user@host or host."""
        if self.user:
            return f"{self.user}@{self.host}"
        return self.host

    def _ssh_base_args(self) -> list:
        """Build common SSH arguments."""
        args = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes"
            if self.strict_host_key
            else "StrictHostKeyChecking=accept-new",
            "-p",
            str(self.port),
        ]
        if self.ssh_key:
            args.extend(["-i", self.ssh_key])
        return args

    def check_connection(self, timeout: int = 10) -> bool:
        """Test SSH connectivity.

        Returns:
            True if connection succeeds.
        """
        args = self._ssh_base_args() + [self.target, "echo", "kitt-ok"]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode == 0 and "kitt-ok" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.debug(f"Connection check failed: {e}")
            return False

    def run_command(
        self,
        command: str,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        """Execute a command on the remote host.

        Args:
            command: Command string to run remotely.
            timeout: Optional timeout in seconds.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        args = self._ssh_base_args() + [self.target, command]
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", "ssh not found"

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
    ) -> bool:
        """Upload a file via SCP.

        Returns:
            True if upload succeeded.
        """
        args = [
            "scp",
            "-o",
            "BatchMode=yes",
            "-P",
            str(self.port),
        ]
        if self.ssh_key:
            args.extend(["-i", self.ssh_key])
        args.extend([local_path, f"{self.target}:{remote_path}"])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Upload failed: {e}")
            return False

    def download_file(
        self,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Download a file via SCP.

        Returns:
            True if download succeeded.
        """
        args = [
            "scp",
            "-o",
            "BatchMode=yes",
            "-P",
            str(self.port),
        ]
        if self.ssh_key:
            args.extend(["-i", self.ssh_key])
        args.extend([f"{self.target}:{remote_path}", local_path])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Download failed: {e}")
            return False

    def download_directory(
        self,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Download a directory recursively via SCP.

        Returns:
            True if download succeeded.
        """
        args = [
            "scp",
            "-r",
            "-o",
            "BatchMode=yes",
            "-P",
            str(self.port),
        ]
        if self.ssh_key:
            args.extend(["-i", self.ssh_key])
        args.extend([f"{self.target}:{remote_path}", local_path])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=300)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"Directory download failed: {e}")
            return False
