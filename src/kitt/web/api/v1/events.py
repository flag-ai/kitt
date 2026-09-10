"""SSE streaming API endpoint."""

import uuid

from flask import Blueprint, Response

bp = Blueprint("api_events", __name__, url_prefix="/api/v1/events")


@bp.route("/stream")
def global_stream():
    """Global SSE event stream — all events."""
    from kitt.web.services.event_bus import event_bus

    subscriber_id = f"web-{uuid.uuid4().hex[:8]}"

    return Response(
        event_bus.subscribe(subscriber_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@bp.route("/stream/<source_id>")
def filtered_stream(source_id):
    """SSE event stream filtered by source ID (agent, campaign, etc.)."""
    from kitt.web.services.event_bus import event_bus

    subscriber_id = f"web-{uuid.uuid4().hex[:8]}"

    return Response(
        event_bus.subscribe(subscriber_id, source_filter=source_id),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
