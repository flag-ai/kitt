"""Health and version API endpoints."""

from flask import Blueprint, jsonify

import kitt

bp = Blueprint("api_health", __name__)


@bp.route("/api/v1/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@bp.route("/api/v1/version")
def version():
    """Version info endpoint."""
    return jsonify(
        {
            "version": kitt.__version__,
            "api_version": "v1",
            "name": "KITT",
        }
    )
