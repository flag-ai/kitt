"""Remote host setup and provisioning for KITT."""

import logging

from .host_config import HostConfig, HostManager
from .ssh_connection import SSHConnection

logger = logging.getLogger(__name__)


class RemoteSetup:
    """Provision a remote machine for KITT execution."""

    def __init__(self, connection: SSHConnection) -> None:
        self.conn = connection

    def check_prerequisites(self) -> dict[str, bool | str]:
        """Check what's available on the remote host.

        Returns:
            Dict of capability checks.
        """
        checks: dict[str, bool | str] = {}

        # SSH connectivity
        checks["ssh"] = self.conn.check_connection()
        if not checks["ssh"]:
            return checks

        # Python
        rc, out, _ = self.conn.run_command("python3 --version")
        checks["python"] = rc == 0
        checks["python_version"] = out.strip() if rc == 0 else ""

        # Docker
        rc, _, _ = self.conn.run_command("docker --version")
        checks["docker"] = rc == 0

        # GPU
        rc, out, _ = self.conn.run_command(
            "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits"
        )
        checks["gpu"] = rc == 0
        checks["gpu_info"] = out.strip() if rc == 0 else ""

        # Disk space
        rc, out, _ = self.conn.run_command("df -BG --output=avail ~ | tail -1")
        checks["disk_info"] = out.strip() if rc == 0 else ""

        return checks

    def install_kitt(self, method: str = "pip") -> bool:
        """Install KITT on the remote host.

        Args:
            method: Installation method ("pip" or "clone").

        Returns:
            True if installation succeeded.
        """
        if method == "pip":
            rc, _, err = self.conn.run_command(
                "pip install --user kitt-llm || pip3 install --user kitt-llm"
            )
        elif method == "clone":
            rc, _, err = self.conn.run_command(
                "git clone https://github.com/kirizan/kitt.git ~/kitt && "
                "cd ~/kitt && pip install --user poetry && poetry install"
            )
        else:
            logger.error(f"Unknown install method: {method}")
            return False

        if rc != 0:
            logger.error(f"KITT installation failed: {err}")
            return False

        return True

    def verify_kitt(self) -> str | None:
        """Verify KITT is installed and return version.

        Returns:
            Version string or None.
        """
        rc, out, _ = self.conn.run_command(
            "kitt --version || python3 -m kitt --version"
        )
        if rc == 0:
            return out.strip()
        return None

    def detect_hardware(self) -> dict[str, str]:
        """Run KITT fingerprint on remote host.

        Returns:
            Dict with hardware info.
        """
        info = {}
        rc, out, _ = self.conn.run_command(
            "kitt fingerprint --verbose 2>/dev/null || echo 'not-available'"
        )
        info["fingerprint"] = out.strip()

        rc, out, _ = self.conn.run_command(
            "nvidia-smi --query-gpu=name,memory.total,count --format=csv,noheader,nounits 2>/dev/null"
        )
        if rc == 0:
            info["gpu"] = out.strip()
            info["gpu_count"] = str(len(out.strip().splitlines()))

        return info

    def setup_engines(
        self,
        engines: list[str],
        dry_run: bool = False,
    ) -> dict[str, bool]:
        """Set up engine images on the remote host.

        Runs ``kitt engines setup <name>`` for each engine over SSH.

        Args:
            engines: List of engine names to set up.
            dry_run: If True, pass --dry-run to kitt engines setup.

        Returns:
            Dict mapping engine name to success bool.
        """
        import shlex

        results: dict[str, bool] = {}
        for engine_name in engines:
            cmd = f"kitt engines setup {shlex.quote(engine_name)}"
            if dry_run:
                cmd += " --dry-run"
            logger.info("Setting up engine '%s' on %s", engine_name, self.conn.target)
            rc, out, err = self.conn.run_command(cmd)
            results[engine_name] = rc == 0
            if rc != 0:
                logger.warning(
                    "Engine setup failed for '%s': %s", engine_name, err or out
                )
            else:
                logger.info("Engine '%s' ready on %s", engine_name, self.conn.target)
        return results

    def setup_host(
        self,
        name: str,
        host_manager: HostManager | None = None,
        install: bool = True,
    ) -> HostConfig | None:
        """Full setup flow for a remote host.

        1. Check connectivity
        2. Detect prerequisites
        3. Install KITT if needed
        4. Detect hardware
        5. Save host config

        Returns:
            HostConfig if setup succeeded, None otherwise.
        """
        logger.info(f"Setting up remote host: {self.conn.target}")

        # Check prerequisites
        prereqs = self.check_prerequisites()
        if not prereqs.get("ssh"):
            logger.error("Cannot connect to remote host")
            return None

        # Install KITT
        if install:
            kitt_version = self.verify_kitt()
            if not kitt_version:
                logger.info("KITT not found on remote, installing...")
                if not self.install_kitt():
                    logger.error("Failed to install KITT")
                    return None
                kitt_version = self.verify_kitt()

        # Detect hardware
        hw_info = self.detect_hardware()

        # Build config
        config = HostConfig(
            name=name,
            hostname=self.conn.host,
            user=self.conn.user or "",
            ssh_key=self.conn.ssh_key or "",
            port=self.conn.port,
            gpu_info=hw_info.get("gpu", prereqs.get("gpu_info", "")),  # type: ignore[arg-type]
            gpu_count=int(hw_info.get("gpu_count", "0") or "0"),
            python_version=prereqs.get("python_version", ""),  # type: ignore[arg-type]
        )

        # Save
        if host_manager is None:
            host_manager = HostManager()
        host_manager.add(config)

        logger.info(f"Host '{name}' setup complete")
        return config
