"""CLI for the KITT thin agent."""

import logging
import logging.handlers
import os
import pwd
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import yaml

logger = logging.getLogger(__name__)

# Log rotation: 5 MB per file, keep 3 backups (~20 MB max)
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


def _setup_logging() -> None:
    """Configure logging with console and rotating file handlers."""
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Console handler (captured by systemd/journalctl)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console)

    # Rotating file handler
    log_dir = Path.home() / ".kitt" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
    )
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)


@click.group()
@click.version_option()
def cli():
    """KITT thin agent — Docker orchestration daemon."""
    _setup_logging()


@cli.command()
@click.option(
    "--server", default="", help="KITT server URL (reads from agent.yaml if not set)"
)
@click.option("--tag", default="", help="Image tag override")
@click.option("--no-cache", "no_cache", is_flag=True, help="Build without Docker cache")
def build(server, tag, no_cache):
    """Build the KITT Docker image locally for this architecture."""
    import hashlib
    import json
    import tarfile
    import urllib.request

    # Resolve server URL from config if not provided
    config_file = Path.home() / ".kitt" / "agent.yaml"
    server_url = server
    default_image = "kitt:latest"
    if not server_url and config_file.exists():
        with open(config_file) as f:
            cfg = yaml.safe_load(f) or {}
        server_url = cfg.get("server_url", "")
        default_image = cfg.get("kitt_image", "") or default_image

    if not server_url:
        click.echo("No server URL. Provide --server or run 'kitt-agent init' first.")
        raise SystemExit(1)

    image_tag = tag or default_image
    base_api = f"{server_url.rstrip('/')}/api/v1/agent"

    # Download build context
    click.echo(f"Downloading build context from {server_url}...")
    with tempfile.NamedTemporaryFile(
        suffix=".tar.gz", prefix="kitt-build-ctx-", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        urllib.request.urlretrieve(f"{base_api}/build-context", str(tmp_path))
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        click.echo(f"Failed to download build context: {e}")
        raise SystemExit(1) from None

    # Verify SHA-256
    try:
        with urllib.request.urlopen(
            f"{base_api}/build-context/sha256", timeout=10
        ) as resp:
            digest_info = json.loads(resp.read())
        expected_sha = digest_info.get("sha256", "")
        actual_sha = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
        if expected_sha and actual_sha != expected_sha:
            tmp_path.unlink(missing_ok=True)
            click.echo(
                f"Integrity check failed: expected {expected_sha[:16]}... "
                f"got {actual_sha[:16]}..."
            )
            raise SystemExit(1)
        click.echo("Build context integrity verified (SHA-256).")
    except SystemExit:
        raise
    except Exception as e:
        click.echo(f"Warning: could not verify build context integrity: {e}")

    # Extract to temp directory
    extract_dir = Path(tempfile.mkdtemp(prefix="kitt-build-"))
    try:
        with tarfile.open(str(tmp_path), "r:gz") as tar:
            # filter="data" prevents tar path traversal (Python 3.12+/3.11.4+)
            try:
                tar.extractall(str(extract_dir), filter="data")
            except TypeError:
                tar.extractall(str(extract_dir))
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        click.echo(f"Failed to extract build context: {e}")
        raise SystemExit(1) from None
    finally:
        tmp_path.unlink(missing_ok=True)

    # Find the extracted context directory
    context_dir = extract_dir / "kitt-build-context"
    if not context_dir.exists():
        # Fall back to extract_dir itself if tarball root differs
        context_dir = extract_dir

    dockerfile = context_dir / "docker" / "web" / "Dockerfile"
    if not dockerfile.exists():
        click.echo(f"Dockerfile not found at {dockerfile}")
        raise SystemExit(1)

    # Run docker build
    click.echo(f"Building Docker image: {image_tag}")
    build_args = [
        "docker",
        "build",
        "-f",
        str(dockerfile),
        "-t",
        image_tag,
    ]
    if no_cache:
        build_args.append("--no-cache")
    build_args.append(str(context_dir))

    try:
        result = subprocess.run(build_args, timeout=1800)
        if result.returncode != 0:
            click.echo("Docker build failed.")
            raise SystemExit(1)
    except subprocess.TimeoutExpired:
        click.echo("Docker build timed out.")
        raise SystemExit(1) from None
    except FileNotFoundError:
        click.echo("Docker not found. Install Docker to build images.")
        raise SystemExit(1) from None
    finally:
        import shutil as _shutil

        _shutil.rmtree(str(extract_dir), ignore_errors=True)

    # Also tag as kitt:latest if the primary tag differs
    if image_tag != "kitt:latest":
        subprocess.run(
            ["docker", "tag", image_tag, "kitt:latest"],
            capture_output=True,
            timeout=10,
        )

    # Report architecture
    try:
        inspect_result = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{.Architecture}}", image_tag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        arch = inspect_result.stdout.strip() or "unknown"
    except Exception:
        arch = "unknown"

    click.echo("KITT Docker image built successfully.")
    click.echo(f"  Tag: {image_tag}")
    click.echo(f"  Architecture: {arch}")
    if image_tag != "kitt:latest":
        click.echo("  Also tagged: kitt:latest")


@cli.command()
@click.option(
    "--server", required=True, help="KITT server URL (e.g., https://server:8080)"
)
@click.option("--token", default="", help="Bearer token for authentication (optional)")
@click.option("--name", default="", help="Agent name (defaults to hostname)")
@click.option("--port", default=8090, help="Agent listening port")
@click.option(
    "--model-dir",
    default="",
    help="Local model storage directory (default: ~/.kitt/models)",
)
@click.option(
    "--share-source", default="", help="NFS share source (e.g., nas:/volume1/models)"
)
@click.option(
    "--share-mount",
    default="",
    help="Local mount point for NFS share (e.g., /mnt/models)",
)
def init(server, token, name, port, model_dir, share_source, share_mount):
    """Initialize agent configuration."""
    agent_name = name or socket.gethostname()
    config_dir = Path.home() / ".kitt"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "agent.yaml"

    config = {
        "name": agent_name,
        "server_url": server,
        "token": token,
        "port": port,
    }

    if model_dir:
        config["model_storage_dir"] = model_dir
    if share_source:
        config["model_share_source"] = share_source
    if share_mount:
        config["model_share_mount"] = share_mount

    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    config_path.chmod(0o600)

    click.echo(f"Agent config saved: {config_path}")
    click.echo(f"  Name: {agent_name}")
    click.echo(f"  Server: {server}")
    click.echo(f"  Port: {port}")
    if model_dir:
        click.echo(f"  Model dir: {model_dir}")
    if share_source:
        click.echo(f"  Share source: {share_source}")
    if share_mount:
        click.echo(f"  Share mount: {share_mount}")
    click.echo()
    click.echo("Start the agent with: kitt-agent start")


@cli.command()
@click.option("--server", default="", help="KITT server URL to check connectivity")
@click.option("--port", default=8090, help="Agent port to check availability")
@click.option(
    "--model-dir", default="", help="Model storage directory to check disk space"
)
def preflight(server, port, model_dir):
    """Run prerequisite checks for KITT agent.

    Verifies Docker, GPU drivers, NFS utilities, disk space,
    server connectivity, and port availability.

    Exit code 1 if any required check fails.
    """
    from kitt_agent.preflight import print_results, run_all_checks

    results = run_all_checks(
        server_url=server,
        port=port,
        model_storage_dir=model_dir,
    )
    all_ok = print_results(results)
    if not all_ok:
        raise SystemExit(1)


@cli.command()
@click.option("--config", "config_path", type=click.Path(), help="Path to agent.yaml")
@click.option("--insecure", is_flag=True, help="Disable TLS verification")
@click.option(
    "--preflight/--no-preflight",
    "run_preflight",
    default=False,
    help="Run preflight checks before starting",
)
def start(config_path, insecure, run_preflight):
    """Start the KITT agent daemon."""
    config_file = (
        Path(config_path) if config_path else Path.home() / ".kitt" / "agent.yaml"
    )

    if not config_file.exists():
        click.echo("Agent not configured. Run: kitt-agent init --server <URL>")
        raise SystemExit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    agent_name = config.get("name", "unknown")
    server_url = config.get("server_url", "")
    token = config.get("token", "")
    port = config.get("port", 8090)

    if not server_url:
        click.echo("Invalid agent config — missing server_url")
        raise SystemExit(1)

    # Run preflight checks if requested
    if run_preflight:
        from kitt_agent.preflight import print_results, run_all_checks

        click.echo("Running preflight checks...")
        results = run_all_checks(
            server_url=server_url,
            port=port,
            model_storage_dir=config.get("model_storage_dir", ""),
        )
        all_ok = print_results(results)
        if not all_ok:
            click.echo("Preflight checks failed. Fix the issues above and retry.")
            raise SystemExit(1)
        click.echo()

    click.echo(f"KITT Agent: {agent_name}")
    click.echo(f"  Server: {server_url}")
    click.echo(f"  Port: {port}")

    # TLS config (before try so variables are always defined)
    tls_config = config.get("tls", {})
    verify: str | bool = tls_config.get("ca", True)
    client_cert = None
    if tls_config.get("cert") and tls_config.get("key"):
        client_cert = (tls_config["cert"], tls_config["key"])
    if insecure:
        verify = False

    # Register
    try:
        from kitt_agent.registration import register_with_server

        result = register_with_server(
            server_url=server_url,
            token=token,
            name=agent_name,
            port=port,
            verify=verify,
            client_cert=client_cert,
        )
        agent_id = result.get("agent_id", "")
        heartbeat_interval = result.get("heartbeat_interval_s", 30)
        click.echo(f"  Registered: {agent_id}")
    except Exception as e:
        click.echo(f"  Registration failed: {e}")
        click.echo("  Starting anyway — will retry on heartbeat")
        agent_id = agent_name
        heartbeat_interval = 30

    # Model storage manager
    from kitt_agent.model_storage import ModelStorageManager

    default_model_dir = str(Path.home() / ".kitt" / "models")
    model_storage = ModelStorageManager(
        storage_dir=config.get("model_storage_dir", default_model_dir),
        share_source=config.get("model_share_source", ""),
        share_mount=config.get("model_share_mount", ""),
        auto_cleanup=config.get("auto_cleanup", True),
    )

    # Flask app (created first so heartbeat can dispatch commands to it)
    from kitt_agent.daemon import create_agent_app

    app = create_agent_app(
        name=agent_name,
        server_url=server_url,
        token=token,
        port=port,
        insecure=insecure,
        model_storage=model_storage,
        agent_id=agent_id,
    )

    # Callback for syncing settings from heartbeat response
    def _on_settings(settings: dict) -> None:
        model_storage.update_settings(
            storage_dir=settings.get("model_storage_dir", ""),
            share_source=settings.get("model_share_source", ""),
            share_mount=settings.get("model_share_mount", ""),
            auto_cleanup=str(settings.get("auto_cleanup", "")).lower() == "true"
            if "auto_cleanup" in settings
            else None,
        )
        if "kitt_image" in settings:
            app.set_kitt_image(settings["kitt_image"])

    # Re-registration closure: called by heartbeat thread on 404
    def _register_retry() -> str | None:
        try:
            from kitt_agent.registration import register_with_server

            result = register_with_server(
                server_url=server_url,
                token=token,
                name=agent_name,
                port=port,
                verify=verify,
                client_cert=client_cert,
            )
            new_id = result.get("agent_id", "")
            if new_id:
                logger.info("Re-registered with server, new agent_id: %s", new_id)
                app.set_agent_id(new_id)
                return new_id
        except Exception as e:
            logger.warning("Re-registration failed: %s", e)
        return None

    # Callback when heartbeat syncs a canonical agent_id
    def _on_agent_id_change(new_id: str) -> None:
        app.set_agent_id(new_id)

    # Heartbeat
    from kitt_agent.heartbeat import HeartbeatThread

    hb = HeartbeatThread(
        server_url=server_url,
        agent_id=agent_id,
        token=token,
        interval_s=heartbeat_interval,
        verify=verify if not insecure else False,
        client_cert=client_cert if not insecure else None,
        on_command=app.handle_command,
        on_settings=_on_settings,
        storage_dir=config.get("model_storage_dir", default_model_dir),
        register_fn=_register_retry,
        on_agent_id_change=_on_agent_id_change,
    )
    hb.start()

    ssl_ctx = None
    if not insecure:
        tls_config = config.get("tls", {})
        if tls_config.get("cert") and tls_config.get("key"):
            ssl_ctx = (tls_config["cert"], tls_config["key"])

    click.echo(f"  Listening on port {port}")
    click.echo()

    pid_file = Path.home() / ".kitt" / "agent.pid"
    pid_file.write_text(str(os.getpid()))
    try:
        app.run(host="0.0.0.0", port=port, ssl_context=ssl_ctx, use_reloader=False)
    except KeyboardInterrupt:
        click.echo("\nAgent stopped")
    finally:
        hb.stop()
        pid_file.unlink(missing_ok=True)


@cli.command()
def status():
    """Check agent status."""
    config_file = Path.home() / ".kitt" / "agent.yaml"

    if not config_file.exists():
        click.echo("Agent not configured")
        return

    with open(config_file) as f:
        config = yaml.safe_load(f)

    click.echo("KITT Agent Status")
    click.echo(f"  Name: {config.get('name', 'unknown')}")
    click.echo(f"  Server: {config.get('server_url', 'not set')}")
    click.echo(f"  Port: {config.get('port', 8090)}")

    import json
    import urllib.request

    port = config.get("port", 8090)
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/status", timeout=2
        ) as resp:
            data = json.loads(resp.read())
            click.echo("  Running: yes")
            click.echo(f"  Active containers: {data.get('active_containers', 0)}")
    except Exception:
        click.echo("  Running: no")


@cli.command()
@click.option("--config", "config_path", type=click.Path(), help="Path to agent.yaml")
@click.option("--restart", is_flag=True, help="Restart the agent after update")
def update(config_path, restart):
    """Update the agent to the latest version from the server."""
    config_file = (
        Path(config_path) if config_path else Path.home() / ".kitt" / "agent.yaml"
    )

    if not config_file.exists():
        click.echo("Agent not configured. Run: kitt-agent init --server <URL>")
        raise SystemExit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    server_url = config.get("server_url", "")
    if not server_url:
        click.echo("Invalid agent config — missing server_url")
        raise SystemExit(1)

    from kitt_agent import __version__

    click.echo(f"Current version: {__version__}")
    click.echo(f"Downloading latest agent package from {server_url}...")

    # Download the package and verify integrity
    base_api = f"{server_url.rstrip('/')}/api/v1/agent"
    package_url = f"{base_api}/package"
    digest_url = f"{base_api}/package/sha256"

    with tempfile.NamedTemporaryFile(
        suffix=".tar.gz", prefix="kitt-agent-", delete=False
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        import hashlib
        import json
        import urllib.request

        urllib.request.urlretrieve(package_url, str(tmp_path))

        # Verify SHA-256 digest
        try:
            with urllib.request.urlopen(digest_url, timeout=10) as resp:
                digest_info = json.loads(resp.read())
            expected_sha = digest_info.get("sha256", "")
            actual_sha = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
            if expected_sha and actual_sha != expected_sha:
                tmp_path.unlink(missing_ok=True)
                click.echo(
                    f"Integrity check failed: expected {expected_sha[:16]}... "
                    f"got {actual_sha[:16]}..."
                )
                raise SystemExit(1)
            click.echo("Package integrity verified (SHA-256).")
        except (urllib.error.URLError, OSError) as e:
            click.echo(f"Warning: could not verify package integrity: {e}")
    except SystemExit:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        click.echo(f"Failed to download package: {e}")
        raise SystemExit(1) from None

    # Install using the current venv's pip
    venv_pip = Path(sys.prefix) / "bin" / "pip"
    if not venv_pip.exists():
        venv_pip = Path(sys.prefix) / "Scripts" / "pip.exe"  # Windows

    click.echo("Installing update...")
    try:
        result = subprocess.run(
            [str(venv_pip), "install", "--upgrade", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            click.echo(f"Installation failed:\n{result.stderr}")
            raise SystemExit(1)
    finally:
        tmp_path.unlink(missing_ok=True)

    click.echo("Update installed successfully.")

    if restart:
        # Stop the running agent and re-exec
        pid_file = Path.home() / ".kitt" / "agent.pid"
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, signal.SIGTERM)
                click.echo(f"Stopped running agent (PID {pid})")
                pid_file.unlink(missing_ok=True)
            except ProcessLookupError:
                pid_file.unlink(missing_ok=True)

        click.echo("Starting updated agent...")
        agent_bin = Path(sys.prefix) / "bin" / "kitt-agent"
        os.execv(str(agent_bin), [str(agent_bin), "start"])
    else:
        click.echo("Restart the agent to use the new version:")
        click.echo("  kitt-agent stop && kitt-agent start")


@cli.command()
def stop():
    """Stop the KITT agent daemon."""
    pid_file = Path.home() / ".kitt" / "agent.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            click.echo(f"Agent stopped (PID {pid})")
            pid_file.unlink()
        except ProcessLookupError:
            click.echo("Agent process not found")
            pid_file.unlink()
    else:
        click.echo("No PID file found — agent may not be running")


def _load_agent_config(config_path=None):
    """Load agent config from ~/.kitt/agent.yaml."""
    config_file = (
        Path(config_path) if config_path else Path.home() / ".kitt" / "agent.yaml"
    )
    if not config_file.exists():
        click.echo("Agent not configured. Run: kitt-agent init --server <URL>")
        raise SystemExit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    if not config.get("server_url"):
        click.echo("Invalid agent config — missing server_url")
        raise SystemExit(1)

    return config


def _server_request(method, path, config, data=None):
    """Make an authenticated request to the KITT server."""
    import json
    import ssl
    import urllib.request

    server_url = config["server_url"].rstrip("/")
    token = config.get("token", "")
    url = f"{server_url}{path}"

    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    ctx = None
    if server_url.startswith("https"):
        ctx = ssl.create_default_context()
        tls_config = config.get("tls", {})
        ca = tls_config.get("ca")
        if ca:
            ctx.load_verify_locations(ca)
        cert = tls_config.get("cert")
        key = tls_config.get("key")
        if cert and key:
            ctx.load_cert_chain(cert, key)

    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# --- test subgroup ---


@cli.group()
def test():
    """Manage tests running on this agent."""


@test.command("list")
@click.option(
    "--status",
    "status_filter",
    default="",
    help="Filter by status (e.g., running, completed, failed)",
)
@click.option("--limit", default=20, type=int, help="Max results to return")
def test_list(status_filter, limit):
    """List tests for this agent."""
    config = _load_agent_config()
    agent_name = config.get("name", "unknown")

    path = f"/api/v1/quicktest/?agent_name={agent_name}&per_page={limit}"
    if status_filter:
        path += f"&status={status_filter}"

    try:
        result = _server_request("GET", path, config)
    except Exception as e:
        click.echo(f"Failed to fetch tests: {e}")
        raise SystemExit(1) from None

    items = result.get("items", [])
    if not items:
        click.echo("No tests found.")
        return

    # Simple table output
    header = f"{'ID':<18} {'Model':<30} {'Engine':<12} {'Status':<12} {'Created'}"
    click.echo(f"Tests for agent: {agent_name}")
    click.echo(header)
    click.echo("-" * len(header))

    for item in items:
        model = item.get("model_path", "")
        if "/" in model:
            model = model.rsplit("/", 1)[-1]
        if len(model) > 28:
            model = model[:25] + "..."

        click.echo(
            f"{item.get('id', ''):<18} "
            f"{model:<30} "
            f"{item.get('engine_name', ''):<12} "
            f"{item.get('status', ''):<12} "
            f"{item.get('created_at', '')}"
        )

    click.echo(f"\nTotal: {result.get('total', len(items))}")


@test.command("stop")
@click.argument("test_id")
def test_stop(test_id):
    """Stop a running test by ID."""
    import json
    import urllib.request

    config = _load_agent_config()
    agent_name = config.get("name", "unknown")

    # Fetch the test to verify it exists and belongs to this agent
    try:
        test_data = _server_request("GET", f"/api/v1/quicktest/{test_id}", config)
    except Exception as e:
        click.echo(f"Failed to fetch test {test_id}: {e}")
        raise SystemExit(1) from None

    # Check agent ownership
    test_agent = test_data.get("agent_name", "")
    if test_agent and test_agent != agent_name:
        click.echo(
            f"Test {test_id} belongs to agent '{test_agent}', not '{agent_name}'"
        )
        raise SystemExit(1)

    # Check if already terminal
    current_status = test_data.get("status", "")
    if current_status in ("completed", "failed"):
        click.echo(f"Test {test_id} is already {current_status} — nothing to do.")
        return

    # Mark as failed on the server
    try:
        _server_request(
            "POST",
            f"/api/v1/quicktest/{test_id}/status",
            config,
            data={"status": "failed", "error": "Cancelled by user"},
        )
        click.echo(f"Test {test_id} marked as cancelled on server.")
    except Exception as e:
        click.echo(f"Failed to update test status: {e}")

    # Best-effort: kill local process via agent daemon
    port = config.get("port", 8090)
    try:
        cancel_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/commands",
            data=json.dumps({"type": "cancel"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.get('token', '')}",
            },
            method="POST",
        )
        with urllib.request.urlopen(cancel_req, timeout=5) as resp:
            resp.read()
        click.echo("Local process cancellation sent.")
    except Exception:
        click.echo("Local daemon unreachable — skipped process cancel.")


_SERVICE_NAME = "kitt-agent"
_UNIT_PATH = Path(f"/etc/systemd/system/{_SERVICE_NAME}.service")

_UNIT_TEMPLATE = """\
[Unit]
Description=KITT Agent
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=HOME={home}
ExecStart={venv}/bin/kitt-agent start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


@cli.group()
def service():
    """Manage the KITT agent systemd service."""


@service.command()
@click.option("--no-start", is_flag=True, help="Install and enable without starting")
def install(no_start):
    """Install the KITT agent as a systemd service."""
    config_file = Path.home() / ".kitt" / "agent.yaml"
    if not config_file.exists():
        click.echo("Agent not configured. Run 'kitt-agent init' first.")
        raise SystemExit(1)

    if _UNIT_PATH.exists():
        click.echo(f"Service already installed at {_UNIT_PATH}")
        click.echo("Run 'kitt-agent service uninstall' first to reinstall.")
        raise SystemExit(1)

    venv = sys.prefix
    user = pwd.getpwuid(os.getuid()).pw_name
    home = str(Path.home())

    unit_content = _UNIT_TEMPLATE.format(venv=venv, user=user, home=home)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".service", delete=False) as tmp:
        tmp.write(unit_content)
        tmp_path = tmp.name

    try:
        click.echo(f"Installing systemd service as user '{user}'")
        click.echo(f"  ExecStart: {venv}/bin/kitt-agent start")

        subprocess.run(["sudo", "cp", tmp_path, str(_UNIT_PATH)], check=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)

        enable_cmd = ["sudo", "systemctl", "enable", _SERVICE_NAME]
        if not no_start:
            enable_cmd.append("--now")
        subprocess.run(enable_cmd, check=True)

        click.echo()
        if no_start:
            click.echo("Service installed and enabled (not started).")
            click.echo(f"  Start with: sudo systemctl start {_SERVICE_NAME}")
        else:
            click.echo("Service installed, enabled, and started.")
        click.echo(f"  Status: sudo systemctl status {_SERVICE_NAME}")
        click.echo(f"  Logs:   journalctl -u {_SERVICE_NAME} -f")
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to install service: {e}")
        raise SystemExit(1) from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@service.command()
def uninstall():
    """Uninstall the KITT agent systemd service."""
    if not _UNIT_PATH.exists():
        click.echo("Service is not installed.")
        return

    try:
        subprocess.run(
            ["sudo", "systemctl", "stop", _SERVICE_NAME],
            check=False,
        )
        subprocess.run(
            ["sudo", "systemctl", "disable", _SERVICE_NAME],
            check=False,
        )
        subprocess.run(["sudo", "rm", str(_UNIT_PATH)], check=True)
        subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
        click.echo("Service stopped, disabled, and removed.")
    except subprocess.CalledProcessError as e:
        click.echo(f"Failed to uninstall service: {e}")
        raise SystemExit(1) from e


@service.command("status")
def service_status():
    """Show the KITT agent systemd service status."""
    result = subprocess.run(
        ["systemctl", "status", _SERVICE_NAME],
        capture_output=True,
        text=True,
    )
    click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr)
