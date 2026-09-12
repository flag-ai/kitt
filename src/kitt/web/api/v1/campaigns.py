"""Campaign REST API endpoints."""

import logging

from flask import Blueprint, jsonify, request

from kitt.web.auth import require_auth

logger = logging.getLogger(__name__)

bp = Blueprint("api_campaigns", __name__, url_prefix="/api/v1/campaigns")


def _get_campaign_service():
    from kitt.web.app import get_services

    return get_services()["campaign_service"]


@bp.route("/", methods=["GET"])
def list_campaigns():
    """List campaigns."""
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    svc = _get_campaign_service()
    result = svc.list_campaigns(status=status, page=page, per_page=per_page)
    return jsonify(result)


@bp.route("/", methods=["POST"])
@require_auth
def create_campaign():
    """Create a new campaign."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    name = data.get("name")
    if not name:
        return jsonify({"error": "Campaign name is required"}), 400

    config = data.get("config", {})

    # Validate config has models and engines when provided
    models = config.get("models", [])
    engines = config.get("engines", [])
    if models and not isinstance(models, list):
        return jsonify({"error": "config.models must be a list"}), 400
    if engines and not isinstance(engines, list):
        return jsonify({"error": "config.engines must be a list"}), 400

    # Validate each model has a name
    for i, model in enumerate(models):
        if not isinstance(model, dict) or not model.get("name"):
            return jsonify({"error": f"Model at index {i} must have a 'name'"}), 400

    # Validate each engine has a name
    for i, engine in enumerate(engines):
        if not isinstance(engine, dict) or not engine.get("name"):
            return jsonify({"error": f"Engine at index {i} must have a 'name'"}), 400

    agent_id = data.get("agent_id", "")
    if agent_id:
        from kitt.web.app import get_services

        agent_mgr = get_services()["agent_manager"]
        if agent_mgr.get_agent(agent_id) is None:
            return jsonify({"error": "Agent not found"}), 404

    svc = _get_campaign_service()
    campaign_id = svc.create(
        name=name,
        config_json=config,
        description=data.get("description", ""),
        agent_id=agent_id,
    )
    return jsonify({"id": campaign_id}), 201


@bp.route("/<campaign_id>", methods=["GET"])
def get_campaign(campaign_id):
    """Get campaign details."""
    svc = _get_campaign_service()
    campaign = svc.get(campaign_id)
    if campaign is None:
        return jsonify({"error": "Campaign not found"}), 404
    return jsonify(campaign)


@bp.route("/<campaign_id>", methods=["DELETE"])
@require_auth
def delete_campaign(campaign_id):
    """Delete a campaign."""
    svc = _get_campaign_service()
    if svc.delete(campaign_id):
        return jsonify({"deleted": True})
    return jsonify({"error": "Campaign not found"}), 404


@bp.route("/<campaign_id>/launch", methods=["POST"])
@require_auth
def launch_campaign(campaign_id):
    """Launch a campaign on the assigned agent."""
    svc = _get_campaign_service()
    campaign = svc.get(campaign_id)
    if campaign is None:
        return jsonify({"error": "Campaign not found"}), 404

    if campaign["status"] not in ("draft", "failed"):
        return (
            jsonify(
                {"error": f"Cannot launch campaign in '{campaign['status']}' status"}
            ),
            400,
        )

    if not campaign.get("agent_id"):
        return jsonify({"error": "No agent assigned to this campaign"}), 400

    svc.update_status(campaign_id, "queued")

    # If the assigned agent is a test agent, simulate the campaign
    from kitt.web.app import get_services

    services = get_services()
    agent_mgr = services["agent_manager"]

    if agent_mgr.is_test_agent(campaign["agent_id"]):
        from kitt.web.services.test_simulator import spawn_campaign_simulation

        spawn_campaign_simulation(
            campaign_id=campaign_id,
            agent_id=campaign["agent_id"],
            config=campaign.get("config", {}),
            db_conn=services["db_conn"],
            db_write_lock=services["db_write_lock"],
            result_service=services["result_service"],
            campaign_service=svc,
            agent_manager=agent_mgr,
        )
    else:
        from kitt.web.services.campaign_executor import spawn_campaign_execution

        spawn_campaign_execution(
            campaign_id=campaign_id,
            agent_id=campaign["agent_id"],
            config=campaign.get("config", {}),
            db_conn=services["db_conn"],
            db_write_lock=services["db_write_lock"],
            campaign_service=svc,
        )

    return jsonify({"status": "queued"}), 202


@bp.route("/<campaign_id>/cancel", methods=["POST"])
@require_auth
def cancel_campaign(campaign_id):
    """Cancel a running campaign."""
    svc = _get_campaign_service()
    campaign = svc.get(campaign_id)
    if campaign is None:
        return jsonify({"error": "Campaign not found"}), 404

    if campaign["status"] not in ("queued", "running"):
        return (
            jsonify(
                {"error": f"Cannot cancel campaign in '{campaign['status']}' status"}
            ),
            400,
        )

    svc.update_status(campaign_id, "cancelled")
    return jsonify({"status": "cancelled"})


@bp.route("/<campaign_id>/logs", methods=["GET"])
def get_campaign_logs(campaign_id):
    """Get stored log lines for a campaign."""
    from kitt.web.app import get_services

    db_conn = get_services()["db_conn"]
    rows = db_conn.execute(
        "SELECT line, created_at FROM campaign_logs WHERE campaign_id = ? ORDER BY id",
        (campaign_id,),
    ).fetchall()
    return jsonify(
        {"lines": [{"line": r["line"], "created_at": r["created_at"]} for r in rows]}
    )


@bp.route("/<campaign_id>/config", methods=["PUT"])
@require_auth
def update_config(campaign_id):
    """Update campaign configuration (draft only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    svc = _get_campaign_service()
    if svc.update_config(campaign_id, data):
        return jsonify({"updated": True})
    return jsonify({"error": "Campaign not found or not in draft status"}), 400
