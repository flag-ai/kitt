"""Tests for quick test API — engine-formats endpoint and format validation."""

import json
import sqlite3

import pytest

try:
    from flask import Flask

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FLASK_AVAILABLE, reason="flask not installed")


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT,
            hostname TEXT,
            port INTEGER DEFAULT 8090,
            token TEXT DEFAULT '',
            token_hash TEXT DEFAULT '',
            token_prefix TEXT DEFAULT '',
            status TEXT DEFAULT 'online',
            gpu_info TEXT DEFAULT '',
            gpu_count INTEGER DEFAULT 0,
            cpu_info TEXT DEFAULT '',
            cpu_arch TEXT DEFAULT '',
            ram_gb REAL DEFAULT 0,
            environment_type TEXT DEFAULT '',
            fingerprint TEXT DEFAULT '',
            kitt_version TEXT DEFAULT '',
            hardware_details TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            last_heartbeat TEXT,
            registered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_settings (
            agent_id TEXT,
            key TEXT,
            value TEXT,
            PRIMARY KEY (agent_id, key)
        );
        CREATE TABLE IF NOT EXISTS quick_tests (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            model_path TEXT,
            engine_name TEXT,
            benchmark_name TEXT,
            suite_name TEXT DEFAULT 'quick',
            status TEXT DEFAULT 'queued',
            command_id TEXT,
            engine_mode TEXT DEFAULT 'docker',
            profile_id TEXT DEFAULT '',
            error TEXT DEFAULT '',
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS quick_test_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id TEXT,
            line TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    return conn


@pytest.fixture
def app(db_conn, tmp_path):
    from kitt.web.api.v1.quicktest import bp
    from kitt.web.services.agent_manager import AgentManager
    from kitt.web.services.local_model_service import LocalModelService

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(bp)

    agent_mgr = AgentManager(db_conn)
    model_svc = LocalModelService(str(tmp_path))

    import threading

    _services = {
        "agent_manager": agent_mgr,
        "db_conn": db_conn,
        "db_write_lock": threading.Lock(),
        "local_model_service": model_svc,
    }

    import kitt.web.app

    original = getattr(kitt.web.app, "get_services", None)
    kitt.web.app.get_services = lambda: _services

    # Disable auth for testing
    from kitt.web import auth

    original_require_auth = auth.require_auth

    def _noop_auth(f):
        return f

    auth.require_auth = _noop_auth

    yield flask_app, agent_mgr, db_conn

    if original:
        kitt.web.app.get_services = original
    auth.require_auth = original_require_auth


@pytest.fixture
def client(app):
    flask_app, _, _ = app
    return flask_app.test_client()


class TestEngineFormatsEndpoint:
    def test_returns_format_mapping(self, client):
        resp = client.get("/api/v1/quicktest/engine-formats")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "vllm" in data
        assert "llama_cpp" in data
        # Each engine returns an object with formats, modes, and default_mode
        vllm_info = data["vllm"]
        assert "formats" in vllm_info
        assert "modes" in vllm_info
        assert "default_mode" in vllm_info
        assert "safetensors" in vllm_info["formats"]
        assert "gguf" in data["llama_cpp"]["formats"]

    def test_all_engines_present(self, client):
        resp = client.get("/api/v1/quicktest/engine-formats")
        data = resp.get_json()
        # At minimum these engines should be present
        for engine in ["vllm", "llama_cpp", "ollama"]:
            assert engine in data
            assert "formats" in data[engine]
            assert "modes" in data[engine]


class TestLaunchFormatValidation:
    def test_rejects_incompatible_format(self, app, tmp_path):
        """Launching a safetensors model with llama_cpp returns 400."""
        flask_app, agent_mgr, db_conn = app

        # Create a safetensors model directory
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)

        # Register an agent
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(name="test", hostname="test", port=8090)
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.post(
            "/api/v1/quicktest/",
            data=json.dumps(
                {
                    "agent_id": agent_id,
                    "model_path": str(model_dir),
                    "engine_name": "llama_cpp",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "safetensors" in data["error"]

    def test_accepts_compatible_format(self, app, tmp_path):
        """Launching a GGUF model with llama_cpp succeeds."""
        flask_app, agent_mgr, db_conn = app

        # Create a GGUF model file
        gguf = tmp_path / "model.gguf"
        gguf.write_bytes(b"\x00" * 100)

        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(name="test", hostname="test", port=8090)
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.post(
            "/api/v1/quicktest/",
            data=json.dumps(
                {
                    "agent_id": agent_id,
                    "model_path": str(gguf),
                    "engine_name": "llama_cpp",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 202


class TestAgentCapabilitiesEndpoint:
    def test_returns_capabilities_for_agent(self, app):
        """Agent capabilities include engine compatibility info."""
        flask_app, agent_mgr, _ = app

        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark", hostname="spark", port=8090, cpu_arch="aarch64"
        )
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.get("/api/v1/quicktest/agent-capabilities")
        assert resp.status_code == 200
        data = resp.get_json()
        assert agent_id in data
        agent_caps = data[agent_id]
        assert agent_caps["name"] == "spark"
        assert agent_caps["cpu_arch"] == "aarch64"
        assert "engines" in agent_caps
        # vLLM should be compatible
        assert agent_caps["engines"]["vllm"]["compatible"] is True

    def test_x86_agent_all_engines_compatible(self, app):
        """x86_64 agent should have all engines compatible."""
        flask_app, agent_mgr, _ = app

        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="x86-box", hostname="x86-box", port=8090, cpu_arch="x86_64"
        )
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.get("/api/v1/quicktest/agent-capabilities")
        data = resp.get_json()
        for engine_name, info in data[agent_id]["engines"].items():
            assert info["compatible"] is True, (
                f"{engine_name} should be compatible on x86_64"
            )

    def test_empty_agents_returns_empty(self, app):
        """No agents registered returns empty dict."""
        flask_app, _, _ = app
        client = flask_app.test_client()
        resp = client.get("/api/v1/quicktest/agent-capabilities")
        assert resp.status_code == 200
        assert resp.get_json() == {}


class TestForceFlag:
    def test_force_bypasses_format_validation(self, app, tmp_path):
        """force=true allows launching incompatible format."""
        flask_app, agent_mgr, _ = app

        # Create a safetensors model (incompatible with llama_cpp)
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)

        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(name="test", hostname="test", port=8090)
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.post(
            "/api/v1/quicktest/",
            data=json.dumps(
                {
                    "agent_id": agent_id,
                    "model_path": str(model_dir),
                    "engine_name": "llama_cpp",
                    "force": True,
                }
            ),
            content_type="application/json",
        )
        # Should succeed (202) instead of 400 because force bypasses validation
        assert resp.status_code == 202

    def test_without_force_still_rejects_incompatible(self, app, tmp_path):
        """Without force, incompatible format is still rejected."""
        flask_app, agent_mgr, _ = app

        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)

        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(name="test", hostname="test", port=8090)
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        client = flask_app.test_client()
        resp = client.post(
            "/api/v1/quicktest/",
            data=json.dumps(
                {
                    "agent_id": agent_id,
                    "model_path": str(model_dir),
                    "engine_name": "llama_cpp",
                }
            ),
            content_type="application/json",
        )
        assert resp.status_code == 400
