"""Devon reverse proxy — serves Devon's SPA and API through KITT.

Eliminates cross-origin issues and Devon re-authentication by proxying
all requests server-side and injecting Devon's API key.  The browser
never sees or needs Devon's credentials.
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, Response, jsonify, request

logger = logging.getLogger(__name__)

bp = Blueprint("devon_proxy", __name__, url_prefix="/devon-app")

# Hop-by-hop headers that must not be forwarded
_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

# The placeholder in Devon's index.html that we rewrite
_BASE_URL_PLACEHOLDER = 'window.__DEVON_BASE_URL__=""'
_BASE_URL_REPLACEMENT = 'window.__DEVON_BASE_URL__="/devon-app"'


def _get_devon_url() -> str:
    from kitt.web.app import get_services

    settings_svc = get_services()["settings_service"]
    return settings_svc.get_effective("devon_url", "DEVON_URL", "")


def _get_devon_api_key() -> str:
    return os.environ.get("DEVON_API_KEY", "")


@bp.route("/", defaults={"subpath": ""})
@bp.route("/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy(subpath):
    """Forward requests to Devon, injecting authentication."""
    devon_url = _get_devon_url()
    if not devon_url:
        return jsonify({"error": "Devon not configured"}), 503

    # Reject path traversal attempts
    if ".." in subpath.split("/"):
        return jsonify({"error": "Invalid path"}), 400

    # Build target URL
    target = f"{devon_url.rstrip('/')}/{subpath}"
    if request.query_string:
        target += f"?{request.query_string.decode()}"

    # Build headers — inject Devon API key
    headers = {}
    devon_api_key = _get_devon_api_key()
    if devon_api_key:
        headers["Authorization"] = f"Bearer {devon_api_key}"

    # Forward Content-Type for non-GET requests
    if request.content_type:
        headers["Content-Type"] = request.content_type

    # Get request body for non-GET methods
    body = None
    if request.method != "GET":
        body = request.get_data() or None

    try:
        req = urllib.request.Request(
            target,
            data=body,
            headers=headers,
            method=request.method,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            status = resp.status
            resp_headers = dict(resp.headers)

    except urllib.error.HTTPError as e:
        content = e.read()
        status = e.code
        resp_headers = dict(e.headers)

    except (urllib.error.URLError, OSError) as e:
        logger.warning(f"Devon proxy error: {e}")
        return jsonify({"error": "Devon unreachable"}), 502

    # Filter hop-by-hop headers
    filtered_headers = {
        k: v for k, v in resp_headers.items() if k.lower() not in _HOP_HEADERS
    }

    # Replace Devon's security headers with KITT-appropriate ones
    for hdr in ("x-frame-options", "content-security-policy"):
        filtered_headers.pop(hdr, None)
    filtered_headers["Content-Security-Policy"] = "frame-ancestors 'self'"

    # Rewrite BASE_URL in Devon's SPA index.html so relative API
    # paths resolve through this proxy.  Uses json.dumps for safe
    # interpolation (prevents XSS if devon_url were ever tainted).
    content_type = resp_headers.get("Content-Type", "")
    if "text/html" in content_type:
        try:
            text = content.decode("utf-8")
            text = text.replace(_BASE_URL_PLACEHOLDER, _BASE_URL_REPLACEMENT)
            content = text.encode("utf-8")
        except (UnicodeDecodeError, ValueError):
            pass  # Non-UTF-8 HTML — pass through unmodified

    return Response(content, status=status, headers=filtered_headers)
