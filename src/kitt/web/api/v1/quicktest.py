"""Quick test REST API endpoints."""

import logging
import math
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from kitt.web.auth import require_auth
from kitt.web.services.event_bus import event_bus

logger = logging.getLogger(__name__)

bp = Blueprint("api_quicktest", __name__, url_prefix="/api/v1/quicktest")


@bp.route("/models", methods=["GET"])
def models():
    """List available models from Devon manifest."""
    from kitt.web.app import get_services

    local_model_service = get_services()["local_model_service"]
    return jsonify(local_model_service.read_manifest())


@bp.route("/engine-formats", methods=["GET"])
def engine_formats():
    """Return supported model formats and modes per engine."""
    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()
    result = {}
    for name, cls in EngineRegistry.list_engines().items():
        result[name] = {
            "formats": cls.supported_formats(),
            "modes": [m.value for m in cls.supported_modes()],
            "default_mode": cls.default_mode().value,
        }
    return jsonify(result)


@bp.route("/engine-profiles", methods=["GET"])
def engine_profiles():
    """Return engine profiles for the quicktest form."""
    from kitt.web.app import get_services

    engine_svc = get_services()["engine_service"]
    profiles = engine_svc.list_profiles()
    return jsonify({"profiles": profiles})


@bp.route("/agent-capabilities", methods=["GET"])
def agent_capabilities():
    """Return per-agent engine compatibility based on CPU architecture.

    Response format::

        {
            "agent-id": {
                "name": "DGX Spark",
                "cpu_arch": "aarch64",
                "engines": {
                    "vllm": {"compatible": true},
                    "llama_cpp": {"compatible": false, "reason": "..."}
                }
            }
        }
    """
    from kitt.engines.image_resolver import get_engine_compatibility
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agents = agent_mgr.list_agents()

    result = {}
    for agent in agents:
        cpu_arch = agent.get("cpu_arch", "")
        result[agent["id"]] = {
            "name": agent.get("name", ""),
            "cpu_arch": cpu_arch,
            "engines": get_engine_compatibility(cpu_arch),
        }

    return jsonify(result)


@bp.route("/", methods=["GET"])
def list_tests():
    """List quick tests with pagination and optional status filter."""
    from kitt.web.app import get_services

    conn = get_services()["db_conn"]

    status_filter = request.args.get("status", "")
    agent_name_filter = request.args.get("agent_name", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = max(min(per_page, 100), 1)
    page = max(page, 1)

    conditions: list[str] = []
    params: list = []
    if status_filter:
        conditions.append("qt.status = ?")
        params.append(status_filter)
    if agent_name_filter:
        conditions.append("a.name = ?")
        params.append(agent_name_filter)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    # Count total (join needed for agent_name filter)
    count_row = conn.execute(
        f"""SELECT COUNT(*) FROM quick_tests qt
            LEFT JOIN agents a ON qt.agent_id = a.id
            {where}""",
        params,
    ).fetchone()
    total = count_row[0] if count_row else 0
    pages = math.ceil(total / per_page) if total > 0 else 1

    # Fetch page with agent name join
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT qt.*, a.name AS agent_name
            FROM quick_tests qt
            LEFT JOIN agents a ON qt.agent_id = a.id
            {where}
            ORDER BY qt.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    items = [dict(r) for r in rows]

    return jsonify(
        {
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
        }
    )


@bp.route("/", methods=["POST"])
@require_auth
def launch():
    """Launch a quick test."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    required = ["agent_id", "model_path", "engine_name"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"'{field}' is required"}), 400

    from kitt.web.app import get_services

    services = get_services()
    agent_mgr = services["agent_manager"]

    agent = agent_mgr.get_agent(data["agent_id"])
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404

    # Validate model/engine format compatibility (safety net).
    # Users can bypass validation with force=true for testing
    # unsupported configurations on purpose.
    force = data.get("force", False)

    from kitt.engines.registry import EngineRegistry

    EngineRegistry.auto_discover()
    engine_cls = EngineRegistry.get(data["engine_name"])
    if engine_cls and not force:
        error = engine_cls.validate_model(data["model_path"])
        if error:
            return jsonify({"error": error}), 400

    if force:
        logger.info(
            "Force flag set — skipping validation for %s on %s",
            data["engine_name"],
            data["agent_id"],
        )

    # Create quick test record with command_id for heartbeat dispatch
    test_id = uuid.uuid4().hex[:16]
    command_id = uuid.uuid4().hex[:16]
    now = datetime.now().isoformat()
    engine_mode = data.get("engine_mode", "docker")
    profile_id = data.get("profile_id", "")

    conn = services["db_conn"]
    db_write_lock = services["db_write_lock"]
    with db_write_lock:
        conn.execute(
            """INSERT INTO quick_tests
               (id, agent_id, model_path, engine_name, benchmark_name, suite_name,
                status, command_id, engine_mode, profile_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
            (
                test_id,
                data["agent_id"],
                data["model_path"],
                data["engine_name"],
                data.get("benchmark_name", "throughput"),
                data.get("suite_name", "quick"),
                command_id,
                engine_mode,
                profile_id,
                now,
            ),
        )
        conn.commit()

    # Publish queued event for SSE subscribers
    event_bus.publish(
        "status",
        test_id,
        {"status": "queued", "test_id": test_id, "command_id": command_id},
    )

    # If this is a test agent, simulate execution instead of waiting for heartbeat
    if agent_mgr.is_test_agent(data["agent_id"]):
        from kitt.web.services.test_simulator import spawn_test_simulation

        spawn_test_simulation(
            test_id=test_id,
            agent_id=data["agent_id"],
            model_path=data["model_path"],
            engine_name=data["engine_name"],
            benchmark_name=data.get("benchmark_name", "throughput"),
            suite_name=data.get("suite_name", "quick"),
            db_conn=conn,
            db_write_lock=services["db_write_lock"],
            result_service=services["result_service"],
            agent=agent,
        )

    return jsonify({"id": test_id, "status": "queued", "command_id": command_id}), 202


@bp.route("/<test_id>", methods=["GET"])
def status(test_id):
    """Get quick test status."""
    from kitt.web.app import get_services

    conn = get_services()["db_conn"]
    row = conn.execute("SELECT * FROM quick_tests WHERE id = ?", (test_id,)).fetchone()

    if row is None:
        return jsonify({"error": "Quick test not found"}), 404

    return jsonify(dict(row))


@bp.route("/<test_id>/logs", methods=["GET"])
def get_logs(test_id):
    """Return stored log lines for a test."""
    from kitt.web.app import get_services

    conn = get_services()["db_conn"]
    row = conn.execute("SELECT id FROM quick_tests WHERE id = ?", (test_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Quick test not found"}), 404

    rows = conn.execute(
        "SELECT line, created_at FROM quick_test_logs WHERE test_id = ? ORDER BY id",
        (test_id,),
    ).fetchall()

    return jsonify({"lines": [dict(r) for r in rows]})


@bp.route("/<test_id>/logs", methods=["POST"])
@require_auth
def post_log(test_id):
    """Agent POSTs log lines here during test execution."""
    from kitt.web.app import get_services

    conn = get_services()["db_conn"]
    row = conn.execute("SELECT id FROM quick_tests WHERE id = ?", (test_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Quick test not found"}), 404

    data = request.get_json(silent=True)
    if not data or "line" not in data:
        return jsonify({"error": "'line' is required"}), 400

    # Persist log line to database
    db_write_lock = get_services()["db_write_lock"]
    with db_write_lock:
        conn.execute(
            "INSERT INTO quick_test_logs (test_id, line) VALUES (?, ?)",
            (test_id, data["line"]),
        )
        conn.commit()

    # Publish log line to SSE subscribers
    event_bus.publish(
        "log",
        test_id,
        {"line": data["line"], "test_id": test_id},
    )

    return jsonify({"ok": True})


@bp.route("/<test_id>/status", methods=["POST"])
@require_auth
def update_status(test_id):
    """Agent updates test status (running, completed, failed)."""
    from kitt.web.app import get_services

    conn = get_services()["db_conn"]
    row = conn.execute("SELECT id FROM quick_tests WHERE id = ?", (test_id,)).fetchone()
    if row is None:
        return jsonify({"error": "Quick test not found"}), 404

    data = request.get_json(silent=True)
    if not data or "status" not in data:
        return jsonify({"error": "'status' is required"}), 400

    new_status = data["status"]
    allowed = {"running", "completed", "failed"}
    if new_status not in allowed:
        return jsonify({"error": f"Status must be one of: {allowed}"}), 400

    now = datetime.now().isoformat()

    db_write_lock = get_services()["db_write_lock"]
    with db_write_lock:
        if new_status == "running":
            conn.execute(
                "UPDATE quick_tests SET status = ?, started_at = ? WHERE id = ?",
                (new_status, now, test_id),
            )
        elif new_status in ("completed", "failed"):
            error = data.get("error", "")
            conn.execute(
                "UPDATE quick_tests SET status = ?, completed_at = ?, error = ? WHERE id = ?",
                (new_status, now, error, test_id),
            )
        conn.commit()

    # Publish status event for SSE subscribers
    event_bus.publish(
        "status",
        test_id,
        {"status": new_status, "test_id": test_id},
    )

    return jsonify({"ok": True, "status": new_status})
