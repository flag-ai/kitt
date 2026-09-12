"""Native process lifecycle management for inference engines."""

import contextlib
import logging
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ProcessManager:
    """Manages native engine processes via subprocess.

    Mirrors DockerManager's static interface but for host processes
    instead of Docker containers.
    """

    @staticmethod
    def find_binary(name: str, search_paths: list[str] | None = None) -> str | None:
        """Locate an engine binary on the system.

        Args:
            name: Binary name (e.g. 'llama-server', 'ollama').
            search_paths: Additional directories to search beyond PATH.

        Returns:
            Absolute path to the binary, or None if not found.
        """
        # Check standard PATH first
        found = shutil.which(name)
        if found:
            return found

        # Check additional search paths
        for path in search_paths or []:
            candidate = os.path.join(path, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        return None

    @staticmethod
    def start_process(
        binary: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> subprocess.Popen:
        """Start an engine as a subprocess.

        Args:
            binary: Path to the engine binary.
            args: Command-line arguments.
            env: Environment variables (merged with current env).
            cwd: Working directory.

        Returns:
            The running Popen object.

        Raises:
            FileNotFoundError: If the binary doesn't exist.
            RuntimeError: If the process fails to start.
        """
        cmd = [binary] + (args or [])
        proc_env = {**os.environ, **(env or {})}

        logger.info("Starting native process: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                env=proc_env,
                cwd=cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Binary not found: {binary}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to start process: {exc}") from exc

        # Verify it didn't exit immediately
        time.sleep(0.5)
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(
                f"Process exited immediately (code {proc.returncode}): {stderr[:500]}"
            )

        logger.info("Native process started: PID %d", proc.pid)
        return proc

    @staticmethod
    def stop_process(proc: subprocess.Popen, timeout: int = 10) -> None:
        """Stop a native process gracefully, then force-kill if needed.

        Args:
            proc: The Popen object to stop.
            timeout: Seconds to wait after SIGTERM before SIGKILL.
        """
        if proc.poll() is not None:
            logger.info("Process already exited (PID %d)", proc.pid)
            return

        logger.info("Sending SIGTERM to PID %d", proc.pid)
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
            logger.info("Process stopped gracefully (PID %d)", proc.pid)
        except subprocess.TimeoutExpired:
            logger.warning("SIGTERM timeout, sending SIGKILL to PID %d", proc.pid)
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process PID %d did not exit after SIGKILL", proc.pid)

    @staticmethod
    def is_process_running(proc: subprocess.Popen) -> bool:
        """Check if a process is still running."""
        return proc.poll() is None

    @staticmethod
    def stream_logs(
        proc: subprocess.Popen,
        callback: Callable[[str], Any],
        source: str = "stdout",
    ) -> None:
        """Stream output from a process line-by-line.

        Args:
            proc: The running process.
            callback: Called with each line of output.
            source: Which stream to read ('stdout' or 'stderr').
        """
        stream = proc.stdout if source == "stdout" else proc.stderr
        if stream is None:
            return

        for line in iter(stream.readline, b""):
            text = line.decode(errors="replace").rstrip("\n")
            if text:
                callback(text)

    @staticmethod
    def check_pid(pid: int) -> bool:
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def kill_pid(pid: int, timeout: int = 10) -> None:
        """Kill a process by PID (SIGTERM then SIGKILL)."""
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.5)
            except (OSError, ProcessLookupError):
                return

        # Force kill
        with contextlib.suppress(OSError, ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
