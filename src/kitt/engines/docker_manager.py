"""Docker container lifecycle management for inference engines."""

import logging
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ContainerConfig:
    """Configuration for launching a Docker container."""

    image: str
    port: int  # Host port (used with --network host, engine binds here)
    container_port: int  # Port inside container
    gpu: bool = True
    volumes: dict[str, str] = field(default_factory=dict)  # host_path -> container_path
    env: dict[str, str] = field(default_factory=dict)
    extra_args: list[str] = field(default_factory=list)  # e.g. --shm-size=8g
    command_args: list[str] = field(default_factory=list)  # args after image name
    name_prefix: str = "kitt"


class DockerManager:
    """Manages Docker container lifecycle via the docker CLI.

    All methods are static and use subprocess to call the docker binary.
    No Python Docker SDK dependency required.
    """

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker is installed and the daemon is running."""
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
        """Check if a Docker image is available locally."""
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
    def pull_image(
        image: str, quiet: bool = False, platform: str | None = None
    ) -> None:
        """Pull a Docker image from a registry.

        Args:
            image: Docker image reference (e.g. 'vllm/vllm-openai:latest').
            quiet: Suppress pull progress output.
            platform: Target platform (e.g. 'linux/arm64'). When set, passes
                ``--platform`` to ``docker pull`` to select the correct
                manifest from multi-arch images.

        Raises:
            RuntimeError: If the pull fails.
        """
        cmd = ["docker", "pull"]
        if platform:
            cmd.extend(["--platform", platform])
        if quiet:
            cmd.append("-q")
        cmd.append(image)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to pull Docker image '{image}': {result.stderr.strip()}"
            )

    @staticmethod
    def run_container(config: ContainerConfig) -> str:
        """Start a Docker container and return the container ID.

        Uses --network host so the engine binds directly to host ports.

        Raises:
            RuntimeError: If the container fails to start.
        """
        timestamp = int(time.time())
        container_name = f"{config.name_prefix}-{timestamp}"

        cmd = ["docker", "run", "-d", "--network", "host", "--name", container_name]

        if config.gpu:
            cmd.extend(["--gpus", "all"])

        for host_path, container_path in config.volumes.items():
            cmd.extend(["-v", f"{host_path}:{container_path}"])

        for key, value in config.env.items():
            cmd.extend(["-e", f"{key}={value}"])

        for arg in config.extra_args:
            cmd.append(arg)

        cmd.append(config.image)
        cmd.extend(config.command_args)

        logger.info(f"Starting container: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr.strip()}")

        container_id = result.stdout.strip()
        logger.info(f"Container started: {container_id[:12]} ({container_name})")
        return container_id

    @staticmethod
    def stop_container(container_id: str, timeout: int = 10) -> None:
        """Stop and remove a Docker container."""
        try:
            subprocess.run(
                ["docker", "stop", "-t", str(timeout), container_id],
                capture_output=True,
                timeout=timeout + 15,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Timeout stopping container {container_id[:12]}, forcing kill"
            )
            subprocess.run(
                ["docker", "kill", container_id],
                capture_output=True,
                timeout=10,
            )

        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout removing container {container_id[:12]}")

    @staticmethod
    def container_logs(container_id: str, tail: int = 50) -> str:
        """Retrieve recent logs from a container."""
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout + result.stderr
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    @staticmethod
    def wait_for_healthy(
        url: str,
        timeout: float = 600.0,
        interval: float = 2.0,
        container_id: str | None = None,
    ) -> bool:
        """Poll a health endpoint until it responds or timeout is reached.

        Uses exponential backoff: interval doubles each attempt, capped at 10s.

        Args:
            url: Health check URL to poll.
            timeout: Maximum seconds to wait.
            interval: Initial polling interval in seconds.
            container_id: Optional container ID for log retrieval on failure.

        Returns:
            True if the endpoint responded successfully.

        Raises:
            RuntimeError: If the timeout is reached without a healthy response.
        """
        deadline = time.monotonic() + timeout
        current_interval = interval

        while time.monotonic() < deadline:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status < 500:
                        logger.info(f"Health check passed: {url}")
                        return True
            except (urllib.error.URLError, OSError, TimeoutError):
                pass

            time.sleep(min(current_interval, 10.0))
            current_interval = min(current_interval * 2, 10.0)

        # Timeout reached - gather logs for diagnostics
        logs = ""
        if container_id:
            logs = DockerManager.container_logs(container_id, tail=30)

        raise RuntimeError(
            f"Engine failed to become healthy within {timeout}s at {url}\n"
            f"Container logs:\n{logs}"
            if logs
            else f"Engine failed to become healthy within {timeout}s at {url}"
        )

    @staticmethod
    def build_image(
        image: str,
        dockerfile: str,
        context_dir: str,
        target: str | None = None,
        build_args: dict[str, str] | None = None,
        timeout: int = 3600,
        platform: str | None = None,
    ) -> None:
        """Build a Docker image from a Dockerfile.

        Args:
            image: Tag for the built image (e.g. 'kitt/llama-cpp:spark').
            dockerfile: Path to the Dockerfile.
            context_dir: Build context directory.
            target: Optional multi-stage build target.
            build_args: Optional dict of --build-arg key=value pairs.
            timeout: Build timeout in seconds (default 3600 for CUDA builds).
            platform: Target platform (e.g. 'linux/arm64'). When set, passes
                ``--platform`` to ``docker build``.

        Raises:
            RuntimeError: If the build fails.
        """
        cmd = ["docker", "build", "-f", dockerfile, "-t", image]

        if platform:
            cmd.extend(["--platform", platform])

        if target:
            cmd.extend(["--target", target])

        for key, value in (build_args or {}).items():
            cmd.extend(["--build-arg", f"{key}={value}"])

        cmd.append(context_dir)

        logger.info(f"Building image: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to build Docker image '{image}': {result.stderr.strip()}"
            )

        logger.info(f"Successfully built image: {image}")

    @staticmethod
    def exec_in_container(
        container_id: str,
        command: list[str],
        stdin_data: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Execute a command inside a running container.

        Args:
            container_id: Container to exec into.
            command: Command and arguments.
            stdin_data: Optional string to pipe to the command's stdin.

        Raises:
            RuntimeError: If the exec fails.
        """
        cmd = ["docker", "exec"]
        if stdin_data is not None:
            cmd.append("-i")
        cmd += [container_id] + command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            input=stdin_data,
        )

        if result.returncode != 0:
            raise RuntimeError(f"docker exec failed: {result.stderr.strip()}")

        return result
