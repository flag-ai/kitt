"""KITT thin agent daemon — Flask mini-app that receives Docker commands."""

from __future__ import annotations

import hmac
import json
import logging
import shutil as _shutil
import ssl
import subprocess as sp
import tempfile
import threading
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _post_json(
    url: str,
    data: dict[str, Any],
    token: str,
    insecure: bool = False,
) -> None:
    """POST JSON to a URL with bearer auth. Errors are logged, not raised."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    ctx = None
    if url.startswith("https"):
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            response.read()
    except Exception as e:
        logger.warning("POST %s failed: %s", url, e)


try:
    from flask import Flask, Response, jsonify, request

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


def create_agent_app(
    name: str,
    server_url: str,
    token: str,
    port: int = 8090,
    insecure: bool = False,
    model_storage: Any = None,
    agent_id: str = "",
) -> Flask:
    """Create the thin agent Flask app.

    The thin agent receives Docker orchestration commands from the
    KITT server rather than running benchmarks locally.
    """
    if not FLASK_AVAILABLE:
        raise ImportError("Flask is required. Install with: pip install kitt-agent")

    app = Flask(__name__)

    from kitt_agent.docker_ops import ContainerSpec, DockerOps
    from kitt_agent.engine_ops import EngineOps
    from kitt_agent.log_streamer import LogStreamer

    log_streamers: dict[str, LogStreamer] = {}
    active_containers: dict[str, str] = {}  # command_id -> container_id
    _lock = threading.Lock()

    # KITT Docker image used for running benchmarks (mutable so settings can update it).
    _DEFAULT_KITT_IMAGE = (
        "registry.internal.kirby.network/kirizan/infrastructure/kitt:latest"
    )
    _kitt_image_ref: list[str] = [_DEFAULT_KITT_IMAGE]

    # Agent identifier for server API calls (agent_id is the DB primary key)
    _agent_report_id = agent_id or name

    # ---------------------------------------------------------------
    # Shared callback factories and execution helpers
    # ---------------------------------------------------------------

    def _make_callbacks(
        command_id: str, test_id: str
    ) -> tuple[LogStreamer, Callable[[str], None], Callable[[str, str], None]]:
        """Create a log streamer, on_log callback, and status updater."""
        streamer = LogStreamer(command_id)
        log_streamers[command_id] = streamer
        base_url = server_url.rstrip("/")

        def on_log(line: str) -> None:
            streamer.emit(line)
            if test_id:
                _post_json(
                    f"{base_url}/api/v1/quicktest/{test_id}/logs",
                    {"line": line},
                    token,
                    insecure,
                )

        def update_status(status: str, error: str = "") -> None:
            if test_id:
                _post_json(
                    f"{base_url}/api/v1/quicktest/{test_id}/status",
                    {"status": status, "error": error},
                    token,
                    insecure,
                )

        return streamer, on_log, update_status

    def _execute_container(
        payload: dict[str, Any],
        command_id: str,
        on_log: Callable[[str], None],
        update_status: Callable[[str, str], None],
    ) -> None:
        """Execute a run_container command (Docker orchestration)."""
        try:
            spec = ContainerSpec(
                image=payload.get("image", ""),
                port=payload.get("port", 0),
                container_port=payload.get("container_port", 0),
                gpu=payload.get("gpu", True),
                volumes=payload.get("volumes", {}),
                env=payload.get("env", {}),
                extra_args=payload.get("extra_args", []),
                command_args=payload.get("command_args", []),
                name=payload.get("name", ""),
                health_url=payload.get("health_url", ""),
            )

            update_status("running")
            on_log(f"Pulling image: {spec.image}")
            DockerOps.pull_image(spec.image)
            on_log("Starting container...")
            container_id = DockerOps.run_container(spec, on_log=on_log)

            with _lock:
                active_containers[command_id] = container_id

            if spec.health_url:
                on_log(f"Waiting for health: {spec.health_url}")
                healthy = DockerOps.wait_for_healthy(spec.health_url)
                if not healthy:
                    on_log("Health check timed out — stopping container")
                    DockerOps.stop_container(container_id)
                    update_status("failed", error="Health check timeout")
                    _report(
                        server_url,
                        token,
                        _agent_report_id,
                        command_id,
                        {
                            "status": "failed",
                            "error": "Health check timeout",
                            "container_id": container_id,
                        },
                        insecure,
                    )
                    return

            on_log(f"Container healthy: {container_id}")
            DockerOps.stream_logs(container_id, on_log=on_log)
            on_log("--- Container exited ---")
            update_status("completed")
            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": "completed", "container_id": container_id},
                insecure,
            )
        except Exception as e:
            on_log(f"Error: {e}")
            update_status("failed", error=str(e))
            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": "failed", "error": str(e)},
                insecure,
            )
        finally:
            with _lock:
                active_containers.pop(command_id, None)
                log_streamers.pop(command_id, None)

    def _execute_test(
        payload: dict[str, Any],
        command_id: str,
        on_log: Callable[[str], None],
        update_status: Callable[[str, str], None],
    ) -> None:
        """Execute a run_test command via Docker container.

        The thin agent doesn't have the full KITT package installed, so
        benchmarks run inside the KITT Docker image. The model is mounted
        at the same host path so engine containers (launched by KITT via
        the host Docker socket) can also access it.
        """
        engine = payload.get("engine_name", "vllm")
        suite = payload.get("suite_name", "quick")
        model_path = payload.get("model_path", "")
        benchmark = payload.get("benchmark_name", "throughput")
        engine_mode = payload.get("engine_mode", "")

        update_status("running")
        on_log(f"Agent starting benchmark: {benchmark}")
        on_log(f"Engine: {engine}")
        on_log(f"Model: {model_path}")

        # Resolve model to local storage
        local_model_path = model_path
        if model_storage:
            local_model_path = model_storage.resolve_model(model_path, on_log=on_log)

        # Writable output directory for benchmark results
        output_dir = Path(tempfile.gettempdir()) / f"kitt-results-{command_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Decide execution method: Docker container (preferred) or local CLI (fallback).
        import shutil
        import sys

        with _lock:
            kitt_image = _kitt_image_ref[0]
        use_docker = DockerOps.image_exists(kitt_image)

        # Verify architecture matches the host (avoid exec format errors)
        if use_docker:
            host_arch = DockerOps.host_arch()
            img_arch = DockerOps.image_arch(kitt_image)
            if host_arch and img_arch and host_arch != img_arch:
                on_log(
                    f"Image {kitt_image} is {img_arch}, host is {host_arch} — skipping"
                )
                use_docker = False

        if (
            not use_docker
            and kitt_image != "kitt:latest"
            and DockerOps.image_exists("kitt:latest")
        ):
            # Verify kitt:latest arch matches host before using as fallback
            fallback_arch = DockerOps.image_arch("kitt:latest")
            host_arch = DockerOps.host_arch()
            if not host_arch or not fallback_arch or host_arch == fallback_arch:
                kitt_image = "kitt:latest"
                use_docker = True
            else:
                on_log(
                    f"kitt:latest is {fallback_arch}, host is {host_arch} — "
                    "run 'kitt-agent build' to build a compatible image"
                )

        if use_docker:
            # Docker container is the preferred execution method.
            # Mount: model at same host path (so engine sibling containers see it),
            # Docker socket (so KITT can launch engine containers).
            args = [
                "docker",
                "run",
                "--rm",
                "--name",
                f"kitt-run-{command_id[:8]}",
                "--gpus",
                "all",
                "--network",
                "host",
                "--entrypoint",
                "kitt",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                "-v",
                f"{output_dir}:{output_dir}",
            ]
            # Only mount model path if it looks like a filesystem path
            # (Ollama registry names like "qwen2.5:7b" aren't mountable)
            if local_model_path.startswith("/"):
                args.extend(["-v", f"{local_model_path}:{local_model_path}:ro"])
            args.extend(
                [
                    kitt_image,
                    "run",
                    "-m",
                    local_model_path,
                    "-e",
                    engine,
                    "-s",
                    suite,
                    "-o",
                    str(output_dir),
                    "--auto-pull",
                ]
            )
            if engine_mode:
                args.extend(["--mode", engine_mode])
            on_log(f"Running KITT benchmark in container ({kitt_image})")
        else:
            # Fallback: local kitt CLI
            venv_kitt = Path(sys.prefix) / "bin" / "kitt"
            kitt_bin = str(venv_kitt) if venv_kitt.exists() else shutil.which("kitt")
            if kitt_bin:
                args = [
                    kitt_bin,
                    "run",
                    "-m",
                    local_model_path,
                    "-e",
                    engine,
                    "-s",
                    suite,
                    "-o",
                    str(output_dir),
                ]
                if engine_mode:
                    args.extend(["--mode", engine_mode])
                on_log(f"Running KITT benchmark locally ({kitt_bin})")
            else:
                msg = (
                    "No KITT Docker image or local CLI found. "
                    "Run 'kitt-agent build' to build the Docker image."
                )
                on_log(f"Error: {msg}")
                update_status("failed", error=msg)
                _report(
                    server_url,
                    token,
                    _agent_report_id,
                    command_id,
                    {"status": "failed", "error": msg},
                    insecure,
                )
                return

        try:
            proc = sp.Popen(
                args,
                stdout=sp.PIPE,
                stderr=sp.STDOUT,
                text=True,
                bufsize=1,
            )
            tracking_id = f"kitt-run-{command_id[:8]}" if use_docker else str(proc.pid)
            with _lock:
                active_containers[command_id] = tracking_id
            for line in proc.stdout or []:
                on_log(line.rstrip())
            proc.wait()
            final_status = "completed" if proc.returncode == 0 else "failed"
            error_msg = "" if final_status == "completed" else f"Exit {proc.returncode}"
            on_log(f"--- Finished: {final_status} ---")
            update_status(final_status, error=error_msg)

            # Read benchmark results if the run succeeded
            result_data = None
            if final_status == "completed":
                metrics_path = output_dir / "metrics.json"
                if metrics_path.exists():
                    try:
                        result_data = json.loads(metrics_path.read_text())
                        on_log("Benchmark results captured — forwarding to server")
                    except (json.JSONDecodeError, OSError) as e:
                        on_log(f"Warning: Could not read metrics.json: {e}")

            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": final_status, "error": error_msg},
                insecure,
                result_data=result_data,
            )
        except Exception as e:
            on_log(f"Error: {e}")
            update_status("failed", error=str(e))
            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": "failed", "error": str(e)},
                insecure,
            )
        finally:
            # Clean up temp output directory
            _shutil.rmtree(output_dir, ignore_errors=True)
            with _lock:
                active_containers.pop(command_id, None)
                log_streamers.pop(command_id, None)
            if (
                model_storage
                and model_storage.auto_cleanup
                and local_model_path != model_path
            ):
                model_storage.cleanup_model(local_model_path)

    def _execute_cleanup(payload: dict[str, Any]) -> None:
        """Execute a cleanup_storage command."""
        if not model_storage:
            logger.warning("cleanup_storage: no model_storage configured")
            return

        target = payload.get("model_path", "")
        if target:
            local_path = str(model_storage.storage_dir / Path(target).name)
            logger.info("Cleaning up specific model: %s", local_path)
            model_storage.cleanup_model(local_path)
        else:
            # Clean all models in storage (evict everything)
            logger.info("Cleaning all models from storage")
            if model_storage.storage_dir.exists():
                for item in model_storage.storage_dir.iterdir():
                    if not item.name.startswith("."):
                        model_storage.cleanup_model(str(item))

    def _execute_start_engine(
        payload: dict[str, Any],
        command_id: str,
        on_log: Callable[[str], None],
        update_status: Callable[[str, str], None],
    ) -> None:
        """Execute a start_engine command in a background thread."""
        engine_name = payload.get("engine_name", "")
        runtime_config = payload.get("runtime_config", {})
        model_path = payload.get("model_path", "")

        try:
            update_status("running")
            result = EngineOps.start_engine(
                engine_name, runtime_config, model_path, on_log=on_log
            )
            if result["success"]:
                on_log(f"Engine {engine_name} started (PID {result['pid']})")
                update_status("completed")
                _report(
                    server_url,
                    token,
                    _agent_report_id,
                    command_id,
                    {
                        "status": "completed",
                        "pid": result["pid"],
                        "port": result["port"],
                    },
                    insecure,
                )
            else:
                on_log(f"Failed to start {engine_name}: {result['error']}")
                update_status("failed", error=result["error"])
                _report(
                    server_url,
                    token,
                    _agent_report_id,
                    command_id,
                    {"status": "failed", "error": result["error"]},
                    insecure,
                )
        except Exception as e:
            on_log(f"Error starting engine: {e}")
            update_status("failed", error=str(e))
            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": "failed", "error": str(e)},
                insecure,
            )
        finally:
            with _lock:
                log_streamers.pop(command_id, None)

    def _execute_install_engine(
        payload: dict[str, Any],
        command_id: str,
        on_log: Callable[[str], None],
        update_status: Callable[[str, str], None],
    ) -> None:
        """Execute an install_engine command in a background thread."""
        engine_name = payload.get("engine_name", "")

        try:
            update_status("running")
            result = EngineOps.install_engine(engine_name, on_log=on_log)

            if result["success"]:
                update_status("completed")
                _report(
                    server_url,
                    token,
                    _agent_report_id,
                    command_id,
                    {
                        "status": "completed",
                        "version": result.get("version", ""),
                        "already_installed": result.get("already_installed", False),
                    },
                    insecure,
                )
            else:
                error = result.get("error", "Unknown error")
                on_log(f"Install failed: {error}")
                update_status("failed", error=error)
                _report(
                    server_url,
                    token,
                    _agent_report_id,
                    command_id,
                    {"status": "failed", "error": error},
                    insecure,
                )
        except Exception as e:
            on_log(f"Error: {e}")
            update_status("failed", error=str(e))
            _report(
                server_url,
                token,
                _agent_report_id,
                command_id,
                {"status": "failed", "error": str(e)},
                insecure,
            )
        finally:
            with _lock:
                log_streamers.pop(command_id, None)

    def _dispatch_command(
        cmd_type: str,
        payload: dict[str, Any],
        command_id: str,
        test_id: str,
    ) -> None:
        """Dispatch a command to the appropriate executor in a background thread."""
        if cmd_type == "run_container":
            _, on_log, update_status = _make_callbacks(command_id, test_id)
            threading.Thread(
                target=_execute_container,
                args=(payload, command_id, on_log, update_status),
                daemon=True,
            ).start()

        elif cmd_type == "run_test":
            _, on_log, update_status = _make_callbacks(command_id, test_id)
            threading.Thread(
                target=_execute_test,
                args=(payload, command_id, on_log, update_status),
                daemon=True,
            ).start()

        elif cmd_type == "cleanup_storage":
            threading.Thread(
                target=_execute_cleanup,
                args=(payload,),
                daemon=True,
            ).start()

        elif cmd_type == "start_engine":
            _, on_log, update_status = _make_callbacks(command_id, test_id)
            threading.Thread(
                target=_execute_start_engine,
                args=(payload, command_id, on_log, update_status),
                daemon=True,
            ).start()

        elif cmd_type == "install_engine":
            _, on_log, update_status = _make_callbacks(command_id, test_id)
            threading.Thread(
                target=_execute_install_engine,
                args=(payload, command_id, on_log, update_status),
                daemon=True,
            ).start()

        else:
            logger.warning("Unknown command type: %s", cmd_type)

    # ---------------------------------------------------------------
    # Flask routes
    # ---------------------------------------------------------------

    _VALID_ENGINES = {"vllm", "llama_cpp", "ollama", "exllamav2", "mlx"}
    _VALID_SUITES = {"quick", "standard", "performance"}

    def _check_auth():
        auth = request.headers.get("Authorization", "")
        return hmac.compare_digest(auth, f"Bearer {token}")

    @app.route("/api/commands", methods=["POST"])
    def receive_command():
        """Receive a command from the server."""
        if not _check_auth():
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Invalid JSON body"}), 400

        command_id = data.get("command_id", uuid.uuid4().hex[:16])
        cmd_type = data.get("type", "")
        payload = data.get("payload", {})
        test_id = data.get("test_id", "")

        # Validate run_test inputs
        if cmd_type == "run_test":
            engine = payload.get("engine_name", "vllm")
            suite = payload.get("suite_name", "quick")
            if engine not in _VALID_ENGINES:
                return jsonify({"error": f"Invalid engine: {engine}"}), 400
            if suite not in _VALID_SUITES:
                return jsonify({"error": f"Invalid suite: {suite}"}), 400

        # Synchronous commands
        if cmd_type == "stop_container":
            target_cmd = payload.get("command_id", "")
            with _lock:
                cid = active_containers.get(target_cmd)
            if cid:
                DockerOps.stop_container(cid)
                return jsonify({"stopped": True})
            return jsonify({"error": "No active container for this command"}), 404

        if cmd_type == "check_docker":
            return jsonify({"available": DockerOps.is_available()})

        if cmd_type == "engine_status":
            engine_name = payload.get("engine_name", "")
            if engine_name:
                return jsonify(EngineOps.engine_status(engine_name))
            return jsonify({"engines": EngineOps.all_engine_status()})

        if cmd_type == "stop_engine":
            engine_name = payload.get("engine_name", "")
            result = EngineOps.stop_engine(engine_name)
            return jsonify(result)

        # Async commands
        if cmd_type in (
            "run_container",
            "run_test",
            "cleanup_storage",
            "start_engine",
            "install_engine",
        ):
            _dispatch_command(cmd_type, payload, command_id, test_id)
            return jsonify({"accepted": True, "command_id": command_id}), 202

        return jsonify({"error": f"Unknown command type: {cmd_type}"}), 400

    @app.route("/api/logs/<command_id>")
    def stream_logs_endpoint(command_id):
        """Stream logs for a command as SSE."""
        if not _check_auth():
            return jsonify({"error": "Unauthorized"}), 401
        streamer = log_streamers.get(command_id)
        if streamer is None:
            return jsonify({"error": "No logs for this command"}), 404

        subscriber_id = f"log-{uuid.uuid4().hex[:8]}"
        return Response(
            streamer.subscribe(subscriber_id),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.route("/api/status")
    def agent_status():
        """Agent status endpoint."""
        with _lock:
            container_count = len(active_containers)
            stream_count = len(log_streamers)
        result: dict[str, Any] = {
            "name": name,
            "running": container_count > 0,
            "active_containers": container_count,
            "active_streams": stream_count,
        }
        if model_storage:
            result["storage"] = model_storage.get_storage_usage()
        return jsonify(result)

    @app.route("/api/engines")
    def engine_list():
        """List all engines with their status."""
        if not _check_auth():
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify({"engines": EngineOps.all_engine_status()})

    # ---------------------------------------------------------------
    # Heartbeat command handler
    # ---------------------------------------------------------------

    def handle_command(command: dict[str, Any]) -> None:
        """Handle a command received via heartbeat."""
        cmd_type = command.get("type", "")
        payload = command.get("payload", {})
        command_id = command.get("command_id", uuid.uuid4().hex[:16])
        test_id = command.get("test_id", "")
        _dispatch_command(cmd_type, payload, command_id, test_id)

    app.handle_command = handle_command  # type: ignore[attr-defined]

    def set_kitt_image(image: str) -> None:
        """Update the KITT Docker image used for benchmarks."""
        if image:
            with _lock:
                _kitt_image_ref[0] = image

    app.set_kitt_image = set_kitt_image  # type: ignore[attr-defined]

    def set_agent_id(new_id: str) -> None:
        """Update the agent ID used for server API calls."""
        nonlocal _agent_report_id
        if new_id:
            _agent_report_id = new_id

    app.set_agent_id = set_agent_id  # type: ignore[attr-defined]

    return app


def _report(
    server_url: str,
    token: str,
    agent_name: str,
    command_id: str,
    result: dict[str, Any],
    insecure: bool = False,
    result_data: dict[str, Any] | None = None,
) -> None:
    """Report a result back to the server."""
    from urllib.parse import quote

    url = f"{server_url.rstrip('/')}/api/v1/agents/{quote(agent_name, safe='')}/results"
    payload = {
        "command_id": command_id,
        "status": result.get("status", ""),
        "container_id": result.get("container_id", ""),
        "error": result.get("error", ""),
    }
    if result_data is not None:
        payload["result_data"] = result_data
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    ctx = None
    if server_url.startswith("https"):
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            response.read()
    except Exception as e:
        logger.error("Failed to report result: %s", e)
