"""Models blueprint — local model directory browser."""

import logging

from flask import Blueprint, render_template

logger = logging.getLogger(__name__)

bp = Blueprint("models", __name__, url_prefix="/models")


@bp.route("/")
def index():
    """List locally available models from the configured model directory."""
    from kitt.web.app import get_services

    local_svc = get_services()["local_model_service"]
    models = local_svc.list_models()

    return render_template(
        "models/index.html",
        models=models,
        model_dir=str(local_svc.model_dir),
        configured=local_svc.configured,
    )
