"""Results blueprint — results browsing and comparison pages."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from kitt.web.auth import csrf_protect

bp = Blueprint("results", __name__, url_prefix="/results")


@bp.route("/")
def list_results():
    """Results list page with filters and pagination."""
    from kitt.web.app import get_services

    result_svc = get_services()["result_service"]

    model = request.args.get("model", "")
    engine = request.args.get("engine", "")
    suite = request.args.get("suite", "")
    page = request.args.get("page", 1, type=int)

    result = result_svc.list_results(
        model=model, engine=engine, suite_name=suite, page=page
    )

    # Get distinct values for filter dropdowns
    summary = result_svc.get_summary()

    return render_template(
        "results/list.html",
        results=result["items"],
        total=result["total"],
        page=result["page"],
        pages=result["pages"],
        filter_model=model,
        filter_engine=engine,
        filter_suite=suite,
        engines=summary.get("engines", []),
        models=summary.get("models", []),
    )


@bp.route("/<result_id>")
def detail(result_id):
    """Result detail page."""
    from kitt.web.app import get_services

    result_svc = get_services()["result_service"]
    result = result_svc.get_result(result_id)

    if result is None:
        flash("Result not found", "error")
        return redirect(url_for("results.list_results"))

    return render_template("results/detail.html", result=result)


@bp.route("/compare")
def compare():
    """Side-by-side comparison page."""
    from kitt.web.app import get_services

    result_svc = get_services()["result_service"]
    ids = request.args.getlist("id")
    results = result_svc.compare_results(ids) if ids else []

    return render_template("results/compare.html", results=results, ids=ids)


@bp.route("/<result_id>/delete", methods=["POST"])
@csrf_protect
def delete(result_id):
    """Delete a result."""
    from kitt.web.app import get_services

    result_svc = get_services()["result_service"]
    result_svc.delete_result(result_id)
    flash("Result deleted", "success")
    return redirect(url_for("results.list_results"))
