"""Quick test blueprint — history, launch form, and detail pages."""

import math

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("quicktest", __name__, url_prefix="/quicktest")


def get_services():
    """Lazy import to avoid circular dependencies."""
    from kitt.web.app import get_services as _gs

    return _gs()


@bp.route("/")
def history():
    """Quick test history list page."""
    services = get_services()
    conn = services["db_conn"]

    status_filter = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    per_page = 20
    page = max(page, 1)

    where = ""
    params: list = []
    if status_filter:
        where = "WHERE qt.status = ?"
        params.append(status_filter)

    count_row = conn.execute(
        f"SELECT COUNT(*) FROM quick_tests qt {where}", params
    ).fetchone()
    total = count_row[0] if count_row else 0
    pages = math.ceil(total / per_page) if total > 0 else 1

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT qt.*, a.name AS agent_name
            FROM quick_tests qt
            LEFT JOIN agents a ON qt.agent_id = a.id
            {where}
            ORDER BY qt.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    tests = [dict(r) for r in rows]

    return render_template(
        "quicktest/history.html",
        tests=tests,
        total=total,
        page=page,
        pages=pages,
        current_status=status_filter,
    )


@bp.route("/new")
def form():
    """Quick test launch form."""
    services = get_services()
    agent_mgr = services["agent_manager"]
    agents = agent_mgr.list_agents()

    return render_template("quicktest/form.html", agents=agents)


@bp.route("/<test_id>")
def detail(test_id):
    """Quick test detail page with logs."""
    services = get_services()
    conn = services["db_conn"]

    row = conn.execute(
        """SELECT qt.*, a.name AS agent_name
           FROM quick_tests qt
           LEFT JOIN agents a ON qt.agent_id = a.id
           WHERE qt.id = ?""",
        (test_id,),
    ).fetchone()

    if row is None:
        flash("Quick test not found", "error")
        return redirect(url_for("quicktest.history"))

    test = dict(row)

    return render_template("quicktest/detail.html", test=test)
