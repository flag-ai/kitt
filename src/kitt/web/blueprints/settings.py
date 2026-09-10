"""Settings blueprint — server configuration page."""

import logging
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, render_template, render_template_string, request

from kitt.web.auth import csrf_protect

logger = logging.getLogger(__name__)

bp = Blueprint("settings", __name__, url_prefix="/settings")

# Only these keys can be toggled via the settings UI.
_ALLOWED_TOGGLE_KEYS = {"devon_tab_visible"}

# Keys that can be updated via the settings UI (string values).
_ALLOWED_SETTINGS = {"model_dir", "devon_url", "results_dir"}

_TOGGLE_TEMPLATE = """\
<button type="button" hx-post="/settings/toggle" hx-vals='{"key": "{{ key }}"}' hx-swap="outerHTML"
        class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors {{ 'bg-kitt-accent' if value else 'bg-kitt-primary' }}"
        role="switch" aria-checked="{{ 'true' if value else 'false' }}">
    <span class="inline-block h-4 w-4 rounded-full bg-white transition-transform {{ 'translate-x-5' if value else 'translate-x-0' }}"></span>
</button>
<span class="text-sm ml-2 {{ 'text-green-400' if value else 'text-kitt-dim' }}">{{ 'Visible' if value else 'Hidden' }}</span>"""


def _get_effective_config(settings_svc) -> dict:
    """Build config dict with effective values and their sources."""
    from flask import current_app

    default_model_dir = str(Path.home() / ".kitt" / "models")
    default_results_dir = str(Path.cwd())

    return {
        "host": current_app.config.get("HOST", "0.0.0.0"),
        "port": current_app.config.get("PORT", 8080),
        "debug": current_app.config.get("DEBUG", False),
        "tls_enabled": current_app.config.get("TLS_ENABLED", True),
        "insecure": current_app.config.get("INSECURE", False),
        "db_path": str(current_app.config.get("DB_PATH", "")),
        # Editable settings — use effective resolution
        "results_dir": settings_svc.get_effective(
            "results_dir", "KITT_RESULTS_DIR", default_results_dir
        ),
        "results_dir_source": settings_svc.get_source(
            "results_dir", "KITT_RESULTS_DIR"
        ),
        "devon_url": settings_svc.get_effective("devon_url", "DEVON_URL", ""),
        "devon_url_source": settings_svc.get_source("devon_url", "DEVON_URL"),
        "model_dir": settings_svc.get_effective(
            "model_dir", "KITT_MODEL_DIR", default_model_dir
        ),
        "model_dir_source": settings_svc.get_source("model_dir", "KITT_MODEL_DIR"),
    }


@bp.route("/")
def index():
    """Settings page."""
    from kitt.web.app import get_services

    settings_svc = get_services()["settings_service"]
    config = _get_effective_config(settings_svc)
    web_settings = settings_svc.get_all()

    return render_template(
        "settings/index.html", config=config, web_settings=web_settings
    )


@bp.route("/toggle", methods=["POST"])
@csrf_protect
def toggle():
    """Toggle a boolean web setting."""
    from kitt.web.app import get_services

    settings_svc = get_services()["settings_service"]

    key = request.form.get("key", "")
    if key not in _ALLOWED_TOGGLE_KEYS:
        return "Invalid key", 400

    current = settings_svc.get_bool(key, default=True)
    settings_svc.set(key, "false" if current else "true")

    return render_template_string(_TOGGLE_TEMPLATE, key=key, value=not current)


@bp.route("/update", methods=["POST"])
@csrf_protect
def update():
    """Update a string setting and apply it live."""
    from flask import current_app

    from kitt.web.app import get_services

    settings_svc = get_services()["settings_service"]
    services = get_services()

    key = request.form.get("key", "")
    value = request.form.get("value", "").strip()

    if key not in _ALLOWED_SETTINGS:
        return '<span class="text-xs text-red-400">Invalid setting</span>', 400

    # Validate URL schemes (allow empty to clear)
    if key == "devon_url" and value:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            return (
                '<span class="text-xs text-red-400">URL must use http:// or https://</span>',
                400,
            )

    # Save to DB
    settings_svc.set(key, value)

    # Apply live
    warning = ""
    if key == "model_dir":
        default_model_dir = str(Path.home() / ".kitt" / "models")
        effective = settings_svc.get_effective(
            "model_dir", "KITT_MODEL_DIR", default_model_dir
        )
        services["local_model_service"].model_dir = Path(effective)
        if effective and not Path(effective).is_dir():
            warning = "Directory does not exist yet"

    elif key == "devon_url":
        effective = settings_svc.get_effective("devon_url", "DEVON_URL", "")
        services["model_service"]._devon_url = effective or None
        current_app.config["DEVON_URL"] = effective
        # Invalidate Devon status cache
        from kitt.web.api.v1.devon import clear_status_cache

        clear_status_cache()

    elif key == "results_dir":
        default_results_dir = str(Path.cwd())
        effective = settings_svc.get_effective(
            "results_dir", "KITT_RESULTS_DIR", default_results_dir
        )
        current_app.config["RESULTS_DIR"] = effective
        if effective and not Path(effective).is_dir():
            warning = "Directory does not exist yet"

    source = settings_svc.get_source(
        key,
        {
            "model_dir": "KITT_MODEL_DIR",
            "devon_url": "DEVON_URL",
            "results_dir": "KITT_RESULTS_DIR",
        }.get(key, ""),
    )

    source_label = {"saved": "Saved", "env": "From env", "default": "Default"}.get(
        source, source
    )
    source_class = {
        "saved": "bg-kitt-accent/20 text-kitt-accent",
        "env": "bg-blue-900/50 text-blue-300",
        "default": "bg-gray-800 text-gray-400",
    }.get(source, "bg-gray-800 text-gray-400")

    warning_html = ""
    if warning:
        warning_html = f'<span class="text-xs text-yellow-400 ml-2">{warning}</span>'

    return f"""<span class="inline-flex items-center gap-2">
    <span class="text-xs text-green-400">Saved</span>
    <span class="text-xs px-1.5 py-0.5 rounded {source_class}">{source_label}</span>
    {warning_html}
</span>"""
