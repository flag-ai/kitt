"""Flask web application for KITT — full UI and REST API.

This is the main app factory for the KITT web UI. It registers all blueprints,
sets up the database connection, and initializes services. The legacy read-only
dashboard is preserved via create_legacy_app().
"""

import atexit
import json
import logging
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Any

import kitt

logger = logging.getLogger(__name__)

try:
    from flask import Flask, jsonify, render_template_string, request

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# ---------------------------------------------------------------------------
# Service registry (accessed by blueprints via get_services())
# ---------------------------------------------------------------------------
_services: dict[str, Any] = {}


def get_services() -> dict[str, Any]:
    """Get the global service registry. Called by blueprints."""
    return _services


# ---------------------------------------------------------------------------
# Secret key management
# ---------------------------------------------------------------------------


def _get_or_create_secret_key() -> str:
    """Load or generate a persistent Flask secret key.

    Checks ~/.kitt/secret_key; if absent, generates a new key and writes it
    with restricted permissions (0600).
    """
    key_file = Path.home() / ".kitt" / "secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_hex(32)
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key)
    key_file.chmod(0o600)
    return key


# ---------------------------------------------------------------------------
# Main app factory
# ---------------------------------------------------------------------------


def create_app(
    results_dir: str | None = None,
    result_store: Any | None = None,
    db_path: Path | None = None,
    auth_token: str | None = None,
    insecure: bool = False,
    legacy: bool = False,
) -> "Flask":
    """Create the KITT Flask application.

    Args:
        results_dir: Directory to search for results. Defaults to cwd.
        result_store: Optional ResultStore backend. Falls back to auto-init.
        db_path: Path to SQLite database. Defaults to ~/.kitt/kitt.db.
        auth_token: Bearer token for API authentication.
        insecure: If True, skip TLS warnings.
        legacy: If True, return the legacy read-only dashboard.
    """
    if not FLASK_AVAILABLE:
        raise ImportError("Flask is not installed. Install with: pip install kitt[web]")

    if legacy:
        return create_legacy_app(results_dir, result_store)

    # --- Flask app setup ---
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = os.environ.get("KITT_SECRET_KEY") or _get_or_create_secret_key()

    # Trust reverse-proxy headers (X-Forwarded-Proto, X-Forwarded-Host, etc.)
    # so request.url_root reflects the external scheme/host behind Traefik.
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Store config values on app
    base_dir = Path(results_dir) if results_dir else Path.cwd()
    app.config["RESULTS_DIR"] = str(base_dir)
    app.config["AUTH_TOKEN"] = auth_token or os.environ.get("KITT_AUTH_TOKEN", "")
    app.config["INSECURE"] = insecure

    # --- Database connection ---
    _db_path = db_path or Path.home() / ".kitt" / "kitt.db"
    _db_path.parent.mkdir(parents=True, exist_ok=True)

    from kitt.storage.sqlite_store import SQLiteStore

    store = result_store or SQLiteStore(db_path=_db_path)
    app.config["DB_PATH"] = str(_db_path)

    # Get a raw connection for the new v2 tables (agents, campaigns, etc.)
    # Attach a write lock to prevent concurrent write conflicts across threads.
    db_conn = sqlite3.connect(str(_db_path), check_same_thread=False)
    db_conn.row_factory = sqlite3.Row
    db_conn.execute("PRAGMA journal_mode=WAL")
    db_conn.execute("PRAGMA foreign_keys=ON")
    db_write_lock = threading.Lock()

    # Ensure v2 schema is applied
    from kitt.storage.migrations import (
        get_current_version_sqlite,
        run_migrations_sqlite,
    )
    from kitt.storage.schema import SCHEMA_VERSION

    current = get_current_version_sqlite(db_conn)
    if current < SCHEMA_VERSION:
        run_migrations_sqlite(db_conn, current)

    # --- Initialize services ---
    from kitt.web.services.agent_manager import AgentManager
    from kitt.web.services.campaign_service import CampaignService
    from kitt.web.services.engine_service import EngineService
    from kitt.web.services.local_model_service import LocalModelService
    from kitt.web.services.model_service import ModelService
    from kitt.web.services.result_service import ResultService
    from kitt.web.services.settings_service import SettingsService

    devon_api_key = os.environ.get("DEVON_API_KEY")
    default_model_dir = str(Path.home() / ".kitt" / "models")

    settings_service = SettingsService(db_conn, db_write_lock)

    # Resolve effective values: DB (non-empty) > env var > fallback
    devon_url = settings_service.get_effective("devon_url", "DEVON_URL", "")
    model_dir = settings_service.get_effective(
        "model_dir", "KITT_MODEL_DIR", default_model_dir
    )
    effective_results_dir = settings_service.get_effective(
        "results_dir", "KITT_RESULTS_DIR", str(base_dir)
    )
    app.config["DEVON_URL"] = devon_url
    app.config["RESULTS_DIR"] = effective_results_dir

    global _services
    _services = {
        "result_service": ResultService(store),
        "agent_manager": AgentManager(db_conn, db_write_lock),
        "campaign_service": CampaignService(db_conn, db_write_lock),
        "engine_service": EngineService(db_conn, db_write_lock),
        "model_service": ModelService(devon_url=devon_url, devon_api_key=devon_api_key),
        "settings_service": settings_service,
        "local_model_service": LocalModelService(model_dir),
        "db_conn": db_conn,
        "db_write_lock": db_write_lock,
        "store": store,
    }

    # --- Register blueprints ---
    from kitt.web.blueprints.agents import bp as agents_bp
    from kitt.web.blueprints.campaigns import bp as campaigns_bp
    from kitt.web.blueprints.dashboard import bp as dashboard_bp
    from kitt.web.blueprints.devon import bp as devon_bp
    from kitt.web.blueprints.engines import bp as engines_bp
    from kitt.web.blueprints.models import bp as models_bp
    from kitt.web.blueprints.quicktest import bp as quicktest_bp
    from kitt.web.blueprints.results import bp as results_bp
    from kitt.web.blueprints.settings import bp as settings_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(agents_bp)
    app.register_blueprint(engines_bp)
    app.register_blueprint(devon_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(campaigns_bp)
    app.register_blueprint(quicktest_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(settings_bp)

    # --- Register API blueprints ---
    from kitt.web.api.v1.agent_install import bp as api_agent_install_bp
    from kitt.web.api.v1.agents import bp as api_agents_bp
    from kitt.web.api.v1.campaigns import bp as api_campaigns_bp
    from kitt.web.api.v1.devon import bp as api_devon_bp
    from kitt.web.api.v1.devon_proxy import bp as devon_proxy_bp
    from kitt.web.api.v1.engines import bp as api_engines_bp
    from kitt.web.api.v1.events import bp as api_events_bp
    from kitt.web.api.v1.health import bp as health_bp
    from kitt.web.api.v1.models import bp as api_models_bp
    from kitt.web.api.v1.quicktest import bp as api_quicktest_bp
    from kitt.web.api.v1.results import bp as api_results_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(api_agents_bp)
    app.register_blueprint(api_engines_bp)
    app.register_blueprint(api_devon_bp)
    app.register_blueprint(devon_proxy_bp)
    app.register_blueprint(api_agent_install_bp)
    app.register_blueprint(api_campaigns_bp)
    app.register_blueprint(api_results_bp)
    app.register_blueprint(api_models_bp)
    app.register_blueprint(api_quicktest_bp)
    app.register_blueprint(api_events_bp)

    # --- Template context processor ---
    @app.context_processor
    def inject_nav_settings():
        """Inject navigation visibility flags into all templates."""
        try:
            return {
                "devon_tab_visible": settings_service.get_bool(
                    "devon_tab_visible", default=True
                ),
                "kitt_version": kitt.__version__,
            }
        except Exception:
            return {"devon_tab_visible": True, "kitt_version": kitt.__version__}

    # --- HTMX partial routes ---
    @app.route("/partials/agent_cards")
    def partial_agent_cards():
        agents = _services["agent_manager"].list_agents()
        from flask import render_template

        return render_template("partials/agent_card.html", agents=agents)

    @app.route("/partials/campaign_rows")
    def partial_campaign_rows():
        from markupsafe import escape

        campaigns = _services["campaign_service"].list_campaigns(per_page=5)
        html_parts = []
        for c in campaigns["items"]:
            status_cls = {
                "running": "bg-blue-900/50 text-blue-300",
                "completed": "bg-green-900/50 text-green-300",
                "failed": "bg-red-900/50 text-red-300",
            }.get(c["status"], "bg-gray-800 text-gray-400")

            html_parts.append(
                f"""
            <div class="bg-kitt-bg/50 rounded-md p-3">
                <div class="flex items-center justify-between">
                    <a href="/campaigns/{escape(c["id"])}" class="text-sm font-medium hover:text-kitt-accent">{escape(c["name"])}</a>
                    <span class="text-xs px-2 py-0.5 rounded {status_cls}">{escape(c["status"])}</span>
                </div>
            </div>"""
            )
        return (
            "\n".join(html_parts)
            if html_parts
            else '<p class="text-kitt-dim text-sm">No campaigns</p>'
        )

    # --- Legacy compat: /api/health ---
    @app.route("/api/health")
    def legacy_health():
        import kitt

        return jsonify({"status": "ok", "version": kitt.__version__})

    # --- Shutdown cleanup ---
    def _shutdown():
        if db_conn:
            db_conn.close()

    atexit.register(_shutdown)

    logger.info("KITT web app created")
    return app


# ---------------------------------------------------------------------------
# Legacy app (read-only dashboard from v1)
# ---------------------------------------------------------------------------

INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KITT - Benchmark Dashboard</title>
    <style>
        :root {
            --bg: #1a1a2e;
            --surface: #16213e;
            --primary: #0f3460;
            --accent: #e94560;
            --text: #eee;
            --text-dim: #aaa;
            --success: #4caf50;
            --fail: #f44336;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        header {
            background: var(--surface);
            padding: 20px;
            border-bottom: 3px solid var(--accent);
            margin-bottom: 30px;
        }
        header h1 { font-size: 1.8em; }
        header h1 span { color: var(--accent); }
        header p { color: var(--text-dim); margin-top: 5px; }
        .filter-bar {
            background: var(--surface);
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            gap: 15px;
            align-items: center;
            flex-wrap: wrap;
        }
        .filter-bar label { color: var(--text-dim); font-size: 0.9em; }
        .filter-bar select {
            background: var(--primary);
            color: var(--text);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 0.9em;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--surface);
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid var(--primary);
        }
        .stat-card .value { font-size: 2em; font-weight: bold; color: var(--accent); }
        .stat-card .label { color: var(--text-dim); font-size: 0.9em; }
        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 30px;
        }
        th, td { padding: 12px 16px; text-align: left; }
        th { background: var(--primary); font-weight: 600; }
        tr:nth-child(even) { background: rgba(255,255,255,0.03); }
        tr:hover { background: rgba(255,255,255,0.06); }
        .pass { color: var(--success); font-weight: bold; }
        .fail { color: var(--fail); font-weight: bold; }
        .section-title {
            font-size: 1.4em;
            margin: 30px 0 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--primary);
        }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-dim);
        }
        .empty-state h2 { margin-bottom: 10px; }
        .metric-badge {
            background: var(--primary);
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.85em;
        }
        a { color: var(--accent); text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1><span>KITT</span> Benchmark Dashboard</h1>
            <p>Kirizan's Inference Testing Tools - Results Viewer</p>
        </div>
    </header>

    <div class="container">
        {% if all_models or all_engines %}
        <div class="filter-bar">
            <label>Model:</label>
            <select onchange="window.location.search='model='+this.value+(new URLSearchParams(window.location.search).get('engine')?'&engine='+new URLSearchParams(window.location.search).get('engine'):'')">
                <option value="">All Models</option>
                {% for m in all_models %}
                <option value="{{ m }}" {{ 'selected' if filter_model == m }}>{{ m }}</option>
                {% endfor %}
            </select>
            <label>Engine:</label>
            <select onchange="window.location.search='engine='+this.value+(new URLSearchParams(window.location.search).get('model')?'&model='+new URLSearchParams(window.location.search).get('model'):'')">
                <option value="">All Engines</option>
                {% for e in all_engines %}
                <option value="{{ e }}" {{ 'selected' if filter_engine == e }}>{{ e }}</option>
                {% endfor %}
            </select>
        </div>
        {% endif %}

        {% if results %}
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value">{{ results | length }}</div>
                <div class="label">Result Sets</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ engines | length }}</div>
                <div class="label">Engines Tested</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ models | length }}</div>
                <div class="label">Models Tested</div>
            </div>
            <div class="stat-card">
                <div class="value">{{ pass_rate }}%</div>
                <div class="label">Pass Rate</div>
            </div>
        </div>

        <h2 class="section-title">Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Model</th>
                    <th>Engine</th>
                    <th>Suite</th>
                    <th>Status</th>
                    <th>Benchmarks</th>
                    <th>Time</th>
                    <th>Timestamp</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
                {% for r in results %}
                <tr>
                    <td>{{ r.model }}</td>
                    <td>{{ r.engine }}</td>
                    <td>{{ r.suite_name }}</td>
                    <td class="{{ 'pass' if r.passed else 'fail' }}">
                        {{ 'PASS' if r.passed else 'FAIL' }}
                    </td>
                    <td>{{ r.passed_count }}/{{ r.total_benchmarks }}</td>
                    <td>{{ "%.1f" | format(r.total_time_seconds) }}s</td>
                    <td>{{ r.timestamp[:19] }}</td>
                    <td><a href="/api/results/{{ loop.index0 }}">JSON</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        {% for r in results %}
        <h2 class="section-title">{{ r.model }} ({{ r.engine }})</h2>
        <table>
            <thead>
                <tr>
                    <th>Benchmark</th>
                    <th>Run</th>
                    <th>Status</th>
                    <th>Key Metrics</th>
                </tr>
            </thead>
            <tbody>
                {% for bench in r.get('results', []) %}
                <tr>
                    <td>{{ bench.test_name }}</td>
                    <td>{{ bench.run_number }}</td>
                    <td class="{{ 'pass' if bench.passed else 'fail' }}">
                        {{ 'PASS' if bench.passed else 'FAIL' }}
                    </td>
                    <td>
                        {% for k, v in bench.get('metrics', {}).items() %}
                            {% if v is number %}
                            <span class="metric-badge">{{ k }}: {{ "%.2f" | format(v) }}</span>
                            {% endif %}
                        {% endfor %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% endfor %}

        {% else %}
        <div class="empty-state">
            <h2>No Results Found</h2>
            <p>Run benchmarks with <code>kitt run</code> to generate results.</p>
            <p>Results are searched in <code>kitt-results/</code> and <code>karr-*/</code> directories.</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


def create_legacy_app(
    results_dir: str | None = None,
    result_store: Any | None = None,
) -> "Flask":
    """Create the legacy read-only Flask dashboard.

    This is the original KITT dashboard from v1. Kept for backward compatibility.
    Use ``kitt web --legacy`` to launch this version.
    """
    if not FLASK_AVAILABLE:
        raise ImportError("Flask is not installed. Install with: pip install kitt[web]")

    app = Flask(__name__)
    base_dir = Path(results_dir) if results_dir else Path.cwd()
    store = result_store

    def _get_results() -> list[dict[str, Any]]:
        if store is not None:
            return store.query()
        return _scan_results(base_dir)

    @app.route("/")
    def index():
        all_results = _get_results()
        all_engines = sorted(set(r.get("engine", "") for r in all_results))
        all_models = sorted(set(r.get("model", "") for r in all_results))

        filter_model = request.args.get("model", "")
        filter_engine = request.args.get("engine", "")
        results = all_results
        if filter_model:
            results = [r for r in results if r.get("model") == filter_model]
        if filter_engine:
            results = [r for r in results if r.get("engine") == filter_engine]

        engines = set(r.get("engine", "") for r in results)
        models = set(r.get("model", "") for r in results)
        total = len(results)
        passed = sum(1 for r in results if r.get("passed", False))
        pass_rate = round(passed / total * 100) if total > 0 else 0

        return render_template_string(
            INDEX_TEMPLATE,
            results=results,
            engines=engines,
            models=models,
            all_engines=all_engines,
            all_models=all_models,
            filter_model=filter_model,
            filter_engine=filter_engine,
            pass_rate=pass_rate,
        )

    @app.route("/api/results")
    def api_results():
        return jsonify(_get_results())

    @app.route("/api/results/<int:idx>")
    def api_result_detail(idx):
        results = _get_results()
        if 0 <= idx < len(results):
            return jsonify(results[idx])
        return jsonify({"error": "Not found"}), 404

    @app.route("/api/campaigns")
    def api_campaigns():
        results = _get_results()
        filter_model = request.args.get("model", "")
        filter_engine = request.args.get("engine", "")
        if filter_model:
            results = [r for r in results if r.get("model") == filter_model]
        if filter_engine:
            results = [r for r in results if r.get("engine") == filter_engine]

        groups: dict[str, dict[str, Any]] = {}
        for r in results:
            model = r.get("model", "unknown")
            engine = r.get("engine", "unknown")
            key = f"{model}|{engine}"
            if key not in groups:
                groups[key] = {
                    "model": model,
                    "engine": engine,
                    "runs": 0,
                    "passed": 0,
                    "failed": 0,
                }
            groups[key]["runs"] += 1
            if r.get("passed", False):
                groups[key]["passed"] += 1
            else:
                groups[key]["failed"] += 1

        return jsonify(list(groups.values()))

    @app.route("/api/health")
    def health():
        import kitt

        return jsonify({"status": "ok", "version": kitt.__version__})

    return app


# ---------------------------------------------------------------------------
# File-scan helpers (used by legacy app)
# ---------------------------------------------------------------------------


def _scan_results(base_dir: Path) -> list[dict[str, Any]]:
    """Scan for result files in kitt-results/ and karr-* directories."""
    results = []

    for metrics_file in sorted(base_dir.glob("kitt-results/**/metrics.json")):
        data = _load_json(metrics_file)
        if data:
            results.append(data)

    for karr_dir in sorted(base_dir.glob("karr-*")):
        if karr_dir.is_dir():
            for metrics_file in sorted(karr_dir.glob("**/metrics.json")):
                data = _load_json(metrics_file)
                if data:
                    results.append(data)

    return results


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None on error."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None
