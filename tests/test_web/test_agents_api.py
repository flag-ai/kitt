"""Tests for agent API endpoints — heartbeat hostname fallback and canonical ID."""

import json
import sqlite3

import pytest

from kitt.web.services.agent_manager import AgentManager

try:
    from flask import Flask

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FLASK_AVAILABLE, reason="flask not installed")


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal agents + agent_settings + quick_tests tables."""
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
def agent_mgr(db_conn):
    return AgentManager(db_conn)


@pytest.fixture
def app(db_conn, agent_mgr):
    """Create a minimal Flask app with agent API blueprint."""
    from kitt.web.api.v1.agents import bp

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.register_blueprint(bp)

    # Mock get_services to return our test instances
    _services = {
        "agent_manager": agent_mgr,
        "db_conn": db_conn,
        "result_service": type(
            "FakeResultService", (), {"save_result": lambda self, d: None}
        )(),
    }

    import kitt.web.app

    original_get_services = getattr(kitt.web.app, "get_services", None)
    kitt.web.app.get_services = lambda: _services

    yield flask_app

    if original_get_services:
        kitt.web.app.get_services = original_get_services


@pytest.fixture
def client(app):
    return app.test_client()


class TestHeartbeatHostnameFallback:
    def test_heartbeat_by_uuid(self, client, agent_mgr):
        """Normal heartbeat with UUID agent_id succeeds."""
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark",
            hostname="spark",
            port=8090,
        )
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        resp = client.post(
            f"/api/v1/agents/{agent_id}/heartbeat",
            data=json.dumps({"status": "idle"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ack"] is True
        assert data["agent_id"] == agent_id

    def test_heartbeat_by_hostname_fallback(self, client, agent_mgr):
        """Heartbeat with hostname falls back to name-based lookup."""
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark",
            hostname="spark",
            port=8090,
        )
        result = agent_mgr.register(reg, "")
        real_id = result["agent_id"]

        # Use hostname instead of UUID
        resp = client.post(
            "/api/v1/agents/spark/heartbeat",
            data=json.dumps({"status": "idle"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ack"] is True
        # Response includes canonical agent_id
        assert data["agent_id"] == real_id

    def test_heartbeat_unknown_id_returns_404(self, client):
        """Heartbeat with unknown ID and no matching name returns 404."""
        resp = client.post(
            "/api/v1/agents/nonexistent/heartbeat",
            data=json.dumps({"status": "idle"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_heartbeat_canonical_id_in_response(self, client, agent_mgr):
        """Heartbeat response always includes canonical agent_id."""
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="test-agent",
            hostname="test-agent",
            port=8090,
        )
        result = agent_mgr.register(reg, "")
        agent_id = result["agent_id"]

        resp = client.post(
            f"/api/v1/agents/{agent_id}/heartbeat",
            data=json.dumps({"status": "idle"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert "agent_id" in data
        assert data["agent_id"] == agent_id


class TestReportResultHostnameFallback:
    def test_report_result_by_hostname(self, client, agent_mgr):
        """Result reporting falls back to name-based lookup."""
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark",
            hostname="spark",
            port=8090,
        )
        agent_mgr.register(reg, "")

        resp = client.post(
            "/api/v1/agents/spark/results",
            data=json.dumps({"status": "completed"}),
            content_type="application/json",
        )
        assert resp.status_code == 202

    def test_report_result_unknown_returns_404(self, client):
        """Result reporting with unknown agent returns 404."""
        resp = client.post(
            "/api/v1/agents/nonexistent/results",
            data=json.dumps({"status": "completed"}),
            content_type="application/json",
        )
        assert resp.status_code == 404


class TestGetAgentByName:
    def test_found(self, agent_mgr):
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark",
            hostname="spark",
            port=8090,
        )
        result = agent_mgr.register(reg, "")
        agent = agent_mgr.get_agent_by_name("spark")
        assert agent is not None
        assert agent["id"] == result["agent_id"]
        assert agent["name"] == "spark"

    def test_not_found(self, agent_mgr):
        assert agent_mgr.get_agent_by_name("nonexistent") is None

    def test_sanitizes_sensitive_fields(self, agent_mgr):
        from kitt.web.models.agent import AgentRegistration

        reg = AgentRegistration(
            name="spark",
            hostname="spark",
            port=8090,
        )
        agent_mgr.register(reg, "")
        agent = agent_mgr.get_agent_by_name("spark")
        assert "token_hash" not in agent
        assert "token" not in agent
