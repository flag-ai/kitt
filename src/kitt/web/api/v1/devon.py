"""Devon integration API endpoints."""

import logging
import time
import urllib.request

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint("api_devon", __name__, url_prefix="/api/v1/devon")

# Simple cache to avoid hammering Devon on every request.
_status_cache: dict = {"ts": 0.0, "result": None}
_CACHE_TTL_S = 10


def clear_status_cache() -> None:
    """Invalidate the Devon status cache (called when devon_url changes)."""
    _status_cache["ts"] = 0.0
    _status_cache["result"] = None


def _get_devon_url() -> str:
    from kitt.web.app import get_services

    settings_svc = get_services()["settings_service"]
    return settings_svc.get_effective("devon_url", "DEVON_URL", "")


@bp.route("/status")
def status():
    """Check if the Devon web UI is reachable (cached 10s)."""
    now = time.monotonic()
    if _status_cache["result"] is not None and now - _status_cache["ts"] < _CACHE_TTL_S:
        return jsonify(_status_cache["result"])

    devon_url = _get_devon_url()
    if not devon_url:
        result = {"available": False, "url": "", "reason": "not_configured"}
    else:
        try:
            req = urllib.request.Request(devon_url, method="GET")
            with urllib.request.urlopen(req, timeout=3):
                pass
            result = {"available": True, "url": devon_url}
        except Exception as e:
            logger.debug(f"Devon health check failed: {e}")
            result = {"available": False, "url": devon_url, "reason": "unreachable"}

    _status_cache["ts"] = now
    _status_cache["result"] = result
    return jsonify(result)
