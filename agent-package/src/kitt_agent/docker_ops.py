"""Docker container management for the thin agent.

Manages container lifecycle via the Docker CLI (no SDK dependency).
"""

import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Docker and the kernel use different names for the same architectures.
# Normalize to Docker conventions (amd64, arm64) for consistent comparison.
_ARCH_ALIASES: dict[str, str] = {
    "x86_64": "amd64",
    "aarch64": "arm64",
}


def normalize_arch(arch: str) -> str:
    """Normalize a CPU architecture string to Docker conventions.

    Maps kernel names (x86_64, aarch64) to Docker names (amd64, arm64).
    """
    return _ARCH_ALIASES.get(arch, arch)


@dataclass
class ContainerSpec:
    """Specification for running a Docker container."""

    image: str
    port: int = 0
    container_port: int = 0
    gpu: bool = True
    volumes: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)
    command_args: list[str] = field(default_factory=list)
    name: str = ""
    health_url: str = ""


_BLOCKED_DOCKER_FLAGS = {
    "--privileged",
    "--pid",
    "--cap-add",
    "--security-opt",
    "--device",
}


class DockerOps:
    """Docker operations for the thin agent."""

    @staticmethod
    def is_available() -> bool:
        """Check if Docker is installed and daemon is running."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def image_exists(image: str) -> bool:
        """Check if a Docker image exists locally."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def image_arch(image: str) -> str:
        """Return the normalized architecture of a local Docker image (e.g. 'amd64', 'arm64')."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", "--format", "{{.Architecture}}", image],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = result.stdout.strip() if result.returncode == 0 else ""
            return normalize_arch(raw) if raw else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def host_arch() -> str:
        """Return the normalized host architecture as Docker reports it (e.g. 'amd64', 'arm64')."""
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.Architecture}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            raw = result.stdout.strip() if result.returncode == 0 else ""
            return normalize_arch(raw) if raw else ""
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def pull_image(image: str, platform: str | None = None) -> bool:
        """Pull a Docker image.

        Args:
            image: Docker image reference.
            platform: Target platform (e.g. 'linux/arm64'). When set, passes
                ``--platform`` to ``docker pull``.
        """
        logger.info("Pulling image: %s (platform=%s)", image, platform or "default")
        cmd = ["docker", "pull"]
        if platform:
            cmd.extend(["--platform", platform])
        cmd.append(image)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            logger.error("Pull failed: %s", result.stderr)
            return False
        return True

    @staticmethod
    def run_container(
        spec: ContainerSpec,
        on_log: Callable[[str], None] | None = None,
    ) -> str:
        """Start a container and return the container ID.

        Args:
            spec: Container specification.
            on_log: Optional callback for log lines.

        Returns:
            Container ID string.
        """
        name = spec.name or f"kitt-agent-{int(time.time())}"
        args = ["docker", "run", "-d", "--name", name]

        if spec.gpu:
            args.extend(["--gpus", "all"])

        if spec.port and spec.container_port:
            args.extend(["-p", f"{spec.port}:{spec.container_port}"])

        for host_path, container_path in spec.volumes.items():
            args.extend(["-v", f"{host_path}:{container_path}"])

        for key, val in spec.env.items():
            args.extend(["-e", f"{key}={val}"])

        for arg in spec.extra_args:
            if any(arg.startswith(flag) for flag in _BLOCKED_DOCKER_FLAGS):
                raise ValueError(f"Blocked Docker flag: {arg}")
        args.extend(spec.extra_args)
        args.append(spec.image)
        args.extend(spec.command_args)

        # Redact -e values to avoid leaking secrets in logs
        safe_args = []
        redact_next = False
        for arg in args:
            if redact_next:
                key = arg.split("=", 1)[0] if "=" in arg else arg
                safe_args.append(f"{key}=***")
                redact_next = False
            elif arg == "-e":
                safe_args.append(arg)
                redact_next = True
            else:
                safe_args.append(arg)
        logger.info("Starting container: %s", " ".join(safe_args))
        result = subprocess.run(args, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            raise RuntimeError(f"Container start failed: {result.stderr.strip()}")

        container_id = result.stdout.strip()[:12]
        logger.info("Container started: %s (%s)", container_id, name)

        if on_log:
            on_log(f"Container started: {container_id}")

        return container_id

    @staticmethod
    def stop_container(container_id: str) -> bool:
        """Stop and remove a container."""
        logger.info("Stopping container: %s", container_id)
        subprocess.run(
            ["docker", "stop", container_id],
            capture_output=True,
            timeout=30,
        )
        result = subprocess.run(
            ["docker", "rm", "-f", container_id],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0

    @staticmethod
    def stream_logs(
        container_id: str,
        on_log: Callable[[str], None],
        follow: bool = True,
    ) -> None:
        """Stream container logs, calling on_log for each line."""
        args = ["docker", "logs", container_id]
        if follow:
            args.append("-f")

        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        try:
            for line in proc.stdout or []:
                on_log(line.rstrip())
        finally:
            proc.wait()

    @staticmethod
    def wait_for_healthy(url: str, timeout: float = 300, interval: float = 2.0) -> bool:
        """Poll a URL until it responds with < 500 status."""
        import urllib.request

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    if resp.status < 500:
                        return True
            except Exception:
                pass
            time.sleep(min(interval, 10.0))
            interval = min(interval * 1.5, 10.0)
        return False

    @staticmethod
    def container_running(container_id: str) -> bool:
        """Check if a container is running."""
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() == "true"
