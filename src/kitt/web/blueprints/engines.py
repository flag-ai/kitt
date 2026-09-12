"""Web UI routes for engine profiles and engine overview."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for

from kitt.web.app import get_services
from kitt.web.auth import csrf_protect

logger = logging.getLogger(__name__)

bp = Blueprint("engines", __name__, url_prefix="/engines")


def _svc():
    return get_services()["engine_service"]


def _agent_mgr():
    return get_services()["agent_manager"]


def _get_engine_registry():
    """Load the engine registry and return engine metadata."""
    try:
        from kitt.engines.registry import EngineRegistry

        EngineRegistry.auto_discover()
        engines = []
        for name, cls in EngineRegistry.list_engines().items():
            engines.append(
                {
                    "name": name,
                    "supported_modes": [m.value for m in cls.supported_modes()],
                    "default_mode": cls.default_mode().value,
                }
            )
        return engines
    except Exception:
        return []


@bp.route("/")
def index():
    """Main engines page — registry, profiles, agent status."""
    registry = _get_engine_registry()
    profiles = _svc().list_profiles()
    agents = _agent_mgr().list_agents()
    matrix = _svc().get_engine_status_matrix()
    return render_template(
        "engines/index.html",
        registry=registry,
        profiles=profiles,
        agents=agents,
        matrix=matrix,
    )


@bp.route("/profiles/new")
def profile_new():
    """Show create profile form."""
    registry = _get_engine_registry()
    return render_template("engines/profile_form.html", registry=registry, profile=None)


@bp.route("/profiles", methods=["POST"])
@csrf_protect
def profile_create():
    """Create a new engine profile."""
    import json

    data = {
        "name": request.form.get("name", "").strip(),
        "engine": request.form.get("engine", "").strip(),
        "mode": request.form.get("mode", "docker"),
        "description": request.form.get("description", "").strip(),
    }

    # Parse JSON config fields.
    for field in ("build_config", "runtime_config"):
        raw = request.form.get(field, "").strip()
        if raw:
            try:
                data[field] = json.loads(raw)
            except json.JSONDecodeError:
                flash(f"Invalid JSON in {field}", "error")
                return redirect(url_for("engines.profile_new"))
        else:
            data[field] = {}

    if not data["name"] or not data["engine"]:
        flash("Name and engine are required", "error")
        return redirect(url_for("engines.profile_new"))

    existing = _svc().get_profile_by_name(data["name"])
    if existing:
        flash(f"Profile '{data['name']}' already exists", "error")
        return redirect(url_for("engines.profile_new"))

    _svc().create_profile(data)
    flash(f"Profile '{data['name']}' created", "success")
    return redirect(url_for("engines.index"))


@bp.route("/profiles/<profile_id>/edit")
def profile_edit(profile_id):
    """Show edit profile form."""
    profile = _svc().get_profile(profile_id)
    if profile is None:
        flash("Profile not found", "error")
        return redirect(url_for("engines.index"))
    registry = _get_engine_registry()
    return render_template(
        "engines/profile_form.html", registry=registry, profile=profile
    )


@bp.route("/profiles/<profile_id>", methods=["POST"])
@csrf_protect
def profile_update(profile_id):
    """Update an existing engine profile."""
    import json

    data = {
        "name": request.form.get("name", "").strip(),
        "engine": request.form.get("engine", "").strip(),
        "mode": request.form.get("mode", "docker"),
        "description": request.form.get("description", "").strip(),
    }

    for field in ("build_config", "runtime_config"):
        raw = request.form.get(field, "").strip()
        if raw:
            try:
                data[field] = json.loads(raw)
            except json.JSONDecodeError:
                flash(f"Invalid JSON in {field}", "error")
                return redirect(url_for("engines.profile_edit", profile_id=profile_id))
        else:
            data[field] = {}

    result = _svc().update_profile(profile_id, data)
    if result is None:
        flash("Profile not found", "error")
    else:
        flash(f"Profile '{data['name']}' updated", "success")
    return redirect(url_for("engines.index"))


@bp.route("/profiles/<profile_id>/delete", methods=["POST"])
@csrf_protect
def profile_delete(profile_id):
    """Delete an engine profile."""
    deleted = _svc().delete_profile(profile_id)
    if deleted:
        flash("Profile deleted", "success")
    else:
        flash("Profile not found", "error")
    return redirect(url_for("engines.index"))
