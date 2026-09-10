"""Dashboard blueprint — main landing page."""

from flask import Blueprint, render_template

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    """Main dashboard page."""
    from kitt.web.app import get_services

    services = get_services()
    result_svc = services["result_service"]
    agent_mgr = services["agent_manager"]
    campaign_svc = services["campaign_service"]

    summary = result_svc.get_summary()
    agents = agent_mgr.list_agents()
    campaigns = campaign_svc.list_campaigns(per_page=5)
    recent_results = result_svc.get_recent(limit=5)

    return render_template(
        "dashboard.html",
        summary=summary,
        agents=agents,
        campaigns=campaigns["items"],
        recent_results=recent_results,
    )
