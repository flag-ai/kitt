"""Campaigns blueprint — campaign management pages."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from kitt.web.auth import csrf_protect

bp = Blueprint("campaigns", __name__, url_prefix="/campaigns")


@bp.route("/")
def list_campaigns():
    """Campaign list page."""
    from kitt.web.app import get_services

    campaign_svc = get_services()["campaign_service"]
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)

    result = campaign_svc.list_campaigns(status=status, page=page)

    return render_template(
        "campaigns/list.html",
        campaigns=result["items"],
        total=result["total"],
        page=result["page"],
        pages=result["pages"],
        current_status=status,
    )


@bp.route("/create")
def create():
    """Campaign creation wizard."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agents = agent_mgr.list_agents()

    return render_template("campaigns/create.html", agents=agents)


@bp.route("/<campaign_id>")
def detail(campaign_id):
    """Campaign detail page with live monitoring."""
    from kitt.web.app import get_services

    campaign_svc = get_services()["campaign_service"]
    campaign = campaign_svc.get(campaign_id)

    if campaign is None:
        flash("Campaign not found", "error")
        return redirect(url_for("campaigns.list_campaigns"))

    return render_template("campaigns/detail.html", campaign=campaign)


@bp.route("/<campaign_id>/delete", methods=["POST"])
@csrf_protect
def delete(campaign_id):
    """Delete a campaign."""
    from kitt.web.app import get_services

    campaign_svc = get_services()["campaign_service"]
    campaign_svc.delete(campaign_id)
    flash("Campaign deleted", "success")
    return redirect(url_for("campaigns.list_campaigns"))
