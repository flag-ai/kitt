"""Results REST API endpoints."""

from flask import Blueprint, jsonify, request

from kitt.web.auth import require_auth

bp = Blueprint("api_results", __name__, url_prefix="/api/v1/results")


def _get_result_service():
    from kitt.web.app import get_services

    return get_services()["result_service"]


@bp.route("/", methods=["GET"])
def list_results():
    """List results with filters and pagination."""
    model = request.args.get("model", "")
    engine = request.args.get("engine", "")
    suite = request.args.get("suite_name", "")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    svc = _get_result_service()
    result = svc.list_results(
        model=model, engine=engine, suite_name=suite, page=page, per_page=per_page
    )
    return jsonify(result)


@bp.route("/<result_id>", methods=["GET"])
def get_result(result_id):
    """Get a single result."""
    svc = _get_result_service()
    result = svc.get_result(result_id)
    if result is None:
        return jsonify({"error": "Result not found"}), 404
    return jsonify(result)


@bp.route("/<result_id>", methods=["DELETE"])
@require_auth
def delete_result(result_id):
    """Delete a result."""
    svc = _get_result_service()
    if svc.delete_result(result_id):
        return jsonify({"deleted": True})
    return jsonify({"error": "Result not found"}), 404


@bp.route("/aggregate", methods=["GET"])
@require_auth
def aggregate():
    """Aggregate results by a field."""
    group_by = request.args.get("group_by", "model")
    metrics = request.args.getlist("metric")

    svc = _get_result_service()
    try:
        result = svc.aggregate(group_by=group_by, metrics=metrics or None)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.route("/compare", methods=["POST"])
@require_auth
def compare():
    """Compare multiple results."""
    data = request.get_json(silent=True)
    if not data or "ids" not in data:
        return jsonify({"error": "Provide 'ids' array in body"}), 400

    svc = _get_result_service()
    results = svc.compare_results(data["ids"])
    return jsonify(results)
