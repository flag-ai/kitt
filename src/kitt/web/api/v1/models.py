"""Model REST API endpoints — Devon integration."""

from flask import Blueprint, jsonify, request

from kitt.web.auth import require_auth

bp = Blueprint("api_models", __name__, url_prefix="/api/v1/models")


def _get_model_service():
    from kitt.web.app import get_services

    return get_services()["model_service"]


@bp.route("/search", methods=["GET"])
def search():
    """Search for models via Devon."""
    query = request.args.get("q", "")
    limit = request.args.get("limit", 20, type=int)

    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    svc = _get_model_service()
    if not svc.configured:
        return jsonify({"error": "Devon is not configured"}), 503

    try:
        results = svc.search(query, limit=limit)
    except Exception:
        return jsonify({"error": "Devon search failed"}), 502

    return jsonify(results)


@bp.route("/local", methods=["GET"])
def list_local():
    """List locally available models."""
    svc = _get_model_service()
    models = svc.list_local()
    return jsonify(models)


@bp.route("/download", methods=["POST"])
@require_auth
def download():
    """Download a model via Devon."""
    data = request.get_json(silent=True)
    if not data or "repo_id" not in data:
        return jsonify({"error": "repo_id is required"}), 400

    svc = _get_model_service()
    try:
        path = svc.download(
            data["repo_id"],
            allow_patterns=data.get("allow_patterns"),
        )
        return jsonify({"path": path}), 202
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@bp.route("/<path:repo_id>", methods=["DELETE"])
@require_auth
def remove(repo_id):
    """Remove a locally downloaded model."""
    svc = _get_model_service()
    if svc.remove(repo_id):
        return jsonify({"deleted": True})
    return jsonify({"error": "Failed to remove model"}), 500
