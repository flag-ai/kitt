"""Agents blueprint — agent management pages."""

import contextlib
import json

from flask import Blueprint, flash, redirect, render_template, request, url_for
from markupsafe import Markup

from kitt.web.auth import csrf_protect

bp = Blueprint("agents", __name__, url_prefix="/agents")


@bp.route("/")
def list_agents():
    """Agent list page."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agents = agent_mgr.list_agents()

    return render_template("agents/list.html", agents=agents)


@bp.route("/<agent_id>")
def detail(agent_id):
    """Agent detail page."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agent = agent_mgr.get_agent(agent_id)

    if agent is None:
        flash("Agent not found", "error")
        return redirect(url_for("agents.list_agents"))

    # Parse hardware_details JSON for the template
    hw_details = {}
    raw_details = agent.get("hardware_details", "")
    if raw_details:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            hw_details = json.loads(raw_details)

    settings = agent_mgr.get_agent_settings(agent_id)
    return render_template(
        "agents/detail.html", agent=agent, hw=hw_details, settings=settings
    )


@bp.route("/add")
def add():
    """Add agent page with setup instructions."""
    server_url = request.host_url.rstrip("/")

    return render_template("agents/add.html", server_url=server_url)


@bp.route("/create-test", methods=["GET"])
def create_test_form():
    """Show form to create a virtual test agent."""
    return render_template("agents/create_test.html")


@bp.route("/create-test", methods=["POST"])
@csrf_protect
def create_test():
    """Create a virtual test agent."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]

    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required", "error")
        return redirect(url_for("agents.create_test_form"))

    # Check for duplicate name
    if agent_mgr.get_agent_by_name(name):
        flash("An agent with that name already exists", "error")
        return redirect(url_for("agents.create_test_form"))

    try:
        gpu_count = int(request.form.get("gpu_count", "1"))
        ram_gb = int(request.form.get("ram_gb", "64"))
    except (ValueError, TypeError):
        flash("GPU count and RAM must be numbers", "error")
        return redirect(url_for("agents.create_test_form"))

    result = agent_mgr.create_test_agent(
        name=name,
        gpu_info=request.form.get("gpu_info", "NVIDIA RTX 4090 24GB"),
        gpu_count=gpu_count,
        cpu_info=request.form.get("cpu_info", "Intel Core i9-13900K"),
        cpu_arch=request.form.get("cpu_arch", "x86_64"),
        ram_gb=ram_gb,
        environment_type=request.form.get("environment_type", "native_linux"),
    )

    flash("Test agent created", "success")
    return redirect(url_for("agents.detail", agent_id=result["agent_id"]))


@bp.route("/<agent_id>/settings", methods=["POST"])
@csrf_protect
def update_settings(agent_id):
    """HTMX endpoint: save a single agent setting."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agent = agent_mgr.get_agent(agent_id)
    if agent is None:
        return Markup('<span class="text-xs text-red-400">Agent not found</span>')

    key = request.form.get("key", "")
    value = request.form.get("value", "")

    if not key:
        return Markup('<span class="text-xs text-red-400">Missing key</span>')

    # Validate heartbeat_interval_s range
    if key == "heartbeat_interval_s":
        try:
            val = int(value)
            if not (10 <= val <= 300):
                return Markup(
                    '<span class="text-xs text-red-400">Must be 10-300</span>'
                )
        except (ValueError, TypeError):
            return Markup('<span class="text-xs text-red-400">Must be a number</span>')

    if agent_mgr.update_agent_settings(agent_id, {key: value}):
        return Markup('<span class="text-xs text-green-400">Saved</span>')
    return Markup('<span class="text-xs text-red-400">Unknown setting</span>')


@bp.route("/<agent_id>/cleanup", methods=["POST"])
@csrf_protect
def cleanup_storage(agent_id):
    """HTMX endpoint: queue cleanup_storage command for agent."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agent = agent_mgr.get_agent(agent_id)
    if agent is None:
        return Markup('<span class="text-xs text-red-400">Agent not found</span>')

    agent_mgr.queue_cleanup_command(agent_id)

    return Markup('<span class="text-xs text-green-400">Cleanup command queued</span>')


@bp.route("/<agent_id>/engines")
def agent_engines(agent_id):
    """HTMX partial: engine status table for an agent."""
    from kitt.web.app import get_services

    engine_svc = get_services()["engine_service"]
    engines = engine_svc.get_agent_engines(agent_id)
    return render_template("partials/agent_engines.html", engines=engines)


@bp.route("/<agent_id>/delete", methods=["POST"])
@csrf_protect
def delete(agent_id):
    """Delete an agent."""
    from kitt.web.app import get_services

    agent_mgr = get_services()["agent_manager"]
    agent_mgr.delete_agent(agent_id)
    flash("Agent removed", "success")
    return redirect(url_for("agents.list_agents"))
