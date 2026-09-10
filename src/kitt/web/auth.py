"""Authentication middleware for KITT web API."""

import hmac
import logging
from functools import wraps
from urllib.parse import urlparse

from flask import current_app, jsonify, request

logger = logging.getLogger(__name__)


def require_auth(f):
    """Decorator that enforces Bearer token authentication.

    Uses timing-safe comparison to prevent timing attacks.
    When AUTH_TOKEN is empty, auth is disabled (development mode).
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        configured_token = current_app.config.get("AUTH_TOKEN", "")
        if not configured_token:
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization"}), 401

        provided_token = auth_header[7:]
        if not hmac.compare_digest(provided_token, configured_token):
            return jsonify({"error": "Invalid authentication token"}), 403

        return f(*args, **kwargs)

    return decorated


def csrf_protect(f):
    """Decorator that validates Origin/Referer on state-changing requests.

    Rejects POST/PUT/DELETE requests whose Origin or Referer header
    does not match the server's own host. API endpoints authenticated
    via Bearer token are exempt (programmatic clients don't send Origin).
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        # Bearer-authenticated requests are exempt (programmatic clients),
        # but the token must be valid to prevent CSRF bypass with a fake header.
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            configured_token = current_app.config.get("AUTH_TOKEN", "")
            provided_token = auth_header[7:]
            if configured_token and hmac.compare_digest(
                provided_token, configured_token
            ):
                return f(*args, **kwargs)
            # Invalid token — fall through to Origin/Referer check

        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")

        if not origin and not referer:
            return "CSRF validation failed: missing Origin header", 403

        server_host = request.host  # includes port if non-standard
        if origin:
            parsed = urlparse(origin)
            request_host = parsed.netloc or parsed.path
        else:
            parsed = urlparse(referer)
            request_host = parsed.netloc

        if request_host != server_host:
            logger.warning(
                "CSRF rejected: origin=%s server=%s", request_host, server_host
            )
            return "CSRF validation failed: origin mismatch", 403

        return f(*args, **kwargs)

    return decorated
