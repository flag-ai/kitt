"""Agent REST API endpoints."""

import logging

from flask import Blueprint, jsonify, request

from kitt.web.auth import require_auth
from kitt.web.models.agent import AgentHeartbeat, AgentRegistration

logger = logging.getLogger(__name__)

bp = Blueprint("api_agents", __name__, url_prefix="/api/v1/agents")


def _get_agent_manager():
    from kitt.web.app import get_services

    return get_services()["agent_manager"]


def _resolve_agent_id(mgr, agent_id: str, token: str | None):
    """Resolve agent_id with name-based fallback on 404.

    Returns ``(resolved_id, None)`` on success or
    ``(None, (response, status_code))`` on auth failure.
    """
    ok, error, status = mgr.check_agent_auth(agent_id, token)
    if ok:
        return agent_id, None
    if status == 404:
        agent = mgr.get_agent_by_name(agent_id)
        if agent:
            real_id = agent["id"]
            ok2, error2, status2 = mgr.check_agent_auth(real_id, token)
            if not ok2:
                return None, (jsonify({"error": error2}), status2)
            return real_id, None
    return None, (jsonify({"error": error}), status)


def _extract_bearer_token() -> str:
    """Extract bearer token from Authorization header, or empty string."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


@bp.route("/register", methods=["POST"])
def register():
    """Register a new agent.

    The agent must provide a Bearer token that matches its provisioned
    token hash.  If the agent has no token_hash stored (legacy or dev
    mode), registration succeeds without a token.
    """
    token = _extract_bearer_token()

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    try:
        reg = AgentRegistration(**data)
    except Exception as e:
        return jsonify({"error": f"Invalid registration data: {e}"}), 400

    mgr = _get_agent_manager()

    ok, error, status = mgr.check_agent_auth_by_name(reg.name, token)
    if not ok:
        return jsonify({"error": error}), status

    result = mgr.register(reg, token)
    return jsonify(result), 201


@bp.route("/<agent_id>/heartbeat", methods=["POST"])
def heartbeat(agent_id):
    """Process agent heartbeat.

    Verifies the agent's Bearer token against its stored hash.
    Agents with no token configured (empty hash) are allowed through.

    When the agent_id is not found (404), treats it as a hostname and
    falls back to a name-based lookup.  This handles the case where
    registration failed and the agent is using its hostname as agent_id.
    """
    token = _extract_bearer_token()
    mgr = _get_agent_manager()

    agent_id, err = _resolve_agent_id(mgr, agent_id, token)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    try:
        hb = AgentHeartbeat(**data)
    except Exception:
        return jsonify({"error": "Invalid heartbeat payload"}), 400
    result = mgr.heartbeat(agent_id, hb)
    # Include canonical agent_id so the agent can sync
    result["agent_id"] = agent_id
    return jsonify(result)


@bp.route("/", methods=["GET"])
def list_agents():
    """List all agents."""
    mgr = _get_agent_manager()
    agents = mgr.list_agents()
    return jsonify(agents)


@bp.route("/<agent_id>", methods=["GET"])
def get_agent(agent_id):
    """Get agent details."""
    mgr = _get_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify(agent)


@bp.route("/<agent_id>", methods=["DELETE"])
@require_auth
def delete_agent(agent_id):
    """Remove an agent."""
    mgr = _get_agent_manager()
    if mgr.delete_agent(agent_id):
        return jsonify({"deleted": True})
    return jsonify({"error": "Agent not found"}), 404


@bp.route("/<agent_id>", methods=["PATCH"])
@require_auth
def update_agent(agent_id):
    """Update agent fields."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    mgr = _get_agent_manager()
    if mgr.update_agent(agent_id, data):
        return jsonify({"updated": True})
    return jsonify({"error": "No valid fields to update"}), 400


@bp.route("/<agent_id>/results", methods=["POST"])
def report_result(agent_id):
    """Agent reports benchmark result.

    Verifies the agent's Bearer token against its stored hash.
    Agents with no token configured (empty hash) are allowed through.

    Falls back to name-based lookup when agent_id is not found (404).
    """
    token = _extract_bearer_token()
    mgr = _get_agent_manager()

    agent_id, err = _resolve_agent_id(mgr, agent_id, token)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    # Store the result if result_data is provided
    from kitt.web.app import get_services

    result_svc = get_services()["result_service"]
    result_data = data.get("result_data")
    if result_data:
        result_svc.save_result(result_data)

    return jsonify({"accepted": True}), 202


@bp.route("/<agent_id>/cleanup", methods=["POST"])
@require_auth
def trigger_cleanup(agent_id):
    """Queue a cleanup_storage command for the agent."""
    mgr = _get_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404

    data = request.get_json(silent=True) or {}
    model_path = data.get("model_path", "")

    command_id = mgr.queue_cleanup_command(agent_id, model_path)
    return jsonify({"queued": True, "command_id": command_id}), 202


@bp.route("/<agent_id>/settings", methods=["GET"])
@require_auth
def get_agent_settings(agent_id):
    """Get all settings for an agent."""
    mgr = _get_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404
    settings = mgr.get_agent_settings(agent_id)
    return jsonify(settings)


@bp.route("/<agent_id>/settings", methods=["PUT"])
@require_auth
def update_agent_settings(agent_id):
    """Update agent settings."""
    mgr = _get_agent_manager()
    agent = mgr.get_agent(agent_id)
    if agent is None:
        return jsonify({"error": "Agent not found"}), 404

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body — expected {key: value}"}), 400

    # Validate heartbeat_interval_s range
    if "heartbeat_interval_s" in data:
        try:
            val = int(data["heartbeat_interval_s"])
            if not (10 <= val <= 300):
                return jsonify({"error": "heartbeat_interval_s must be 10-300"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "heartbeat_interval_s must be an integer"}), 400

    if mgr.update_agent_settings(agent_id, data):
        return jsonify({"updated": True})
    return jsonify({"error": "No valid settings to update"}), 400


@bp.route("/<agent_id>/rotate-token", methods=["POST"])
@require_auth
def rotate_token(agent_id):
    """Generate a new token for an agent. Admin-only."""
    mgr = _get_agent_manager()
    result = mgr.rotate_token(agent_id)
    if result is None:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify(result)
