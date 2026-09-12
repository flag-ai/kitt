"""Local model directory scanner for the web UI.

Scans a configured directory for downloaded model files and returns
structured metadata (name, format, size, path).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Known model file extensions grouped by format.
_FORMAT_EXTENSIONS: dict[str, list[str]] = {
    "gguf": [".gguf"],
    "safetensors": [".safetensors"],
    "pytorch": [".bin", ".pt", ".pth"],
}

# Flattened lookup: extension -> format name.
_EXT_TO_FORMAT: dict[str, str] = {}
for fmt, exts in _FORMAT_EXTENSIONS.items():
    for ext in exts:
        _EXT_TO_FORMAT[ext] = fmt


def _detect_formats_from_path(path: str) -> list[str]:
    """Detect model formats from filesystem when Devon metadata is missing."""
    p = Path(path)
    if not p.exists():
        return []

    if p.is_file():
        fmt = _EXT_TO_FORMAT.get(p.suffix.lower())
        return [fmt] if fmt else []

    formats: set[str] = set()
    for child in p.iterdir():
        if child.is_file():
            fmt = _EXT_TO_FORMAT.get(child.suffix.lower())
            if fmt:
                formats.add(fmt)
    return sorted(formats)


class LocalModelService:
    """Scans a local directory for model files."""

    def __init__(self, model_dir: str | Path) -> None:
        self.model_dir = Path(model_dir)

    @property
    def configured(self) -> bool:
        return self.model_dir.is_dir()

    def read_manifest(self) -> list[dict]:
        """Read Devon's manifest.json from the model directory.

        The manifest is keyed by ``{source}::{model_id}`` and each value
        contains at least ``path``, ``source``, and ``size_bytes``.

        Returns:
            List of dicts with keys: model_id, path, source, size_bytes.
            Returns empty list if manifest doesn't exist or is invalid.
        """
        manifest_path = self.model_dir / "manifest.json"
        if not manifest_path.is_file():
            logger.debug("No manifest.json found at %s", manifest_path)
            return []

        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read manifest.json: %s", e)
            return []

        models: list[dict] = []
        for key, entry in data.items():
            # Key format: "source::model_id"
            parts = key.split("::", 1)
            source = parts[0] if len(parts) == 2 else entry.get("source", "unknown")
            model_id = parts[1] if len(parts) == 2 else key

            # Extract format metadata from Devon manifest
            metadata = entry.get("metadata", {})
            formats = metadata.get("format", [])
            if not formats:
                formats = _detect_formats_from_path(entry.get("path", ""))

            models.append(
                {
                    "model_id": model_id,
                    "path": entry.get("path", ""),
                    "source": source,
                    "size_bytes": entry.get("size_bytes", 0),
                    "formats": formats,
                }
            )

        models.sort(key=lambda m: m["model_id"].lower())
        return models

    def list_models(self) -> list[dict]:
        """Scan model_dir and return a list of discovered models.

        Each model is a directory (or standalone file) containing at least
        one recognised model file.  Results are grouped by parent directory.

        Returns:
            List of dicts with keys: name, path, formats, size_gb, file_count.
        """
        if not self.configured:
            return []

        models: dict[Path, dict] = {}

        for path in self.model_dir.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            fmt = _EXT_TO_FORMAT.get(path.suffix.lower())
            if fmt is None:
                continue

            try:
                file_size = path.stat().st_size
            except (FileNotFoundError, OSError):
                continue

            # Group by immediate model directory.  If the file is directly
            # in model_dir, use the file itself as the key.
            model_root = path.parent if path.parent != self.model_dir else path

            if model_root not in models:
                models[model_root] = {
                    "name": _model_name(model_root, self.model_dir),
                    "path": str(model_root),
                    "formats": set(),
                    "size_bytes": 0,
                    "file_count": 0,
                }
            entry = models[model_root]
            entry["formats"].add(fmt)
            entry["size_bytes"] += file_size
            entry["file_count"] += 1

        # Convert sets to sorted lists and bytes to GB.
        result = []
        for entry in sorted(models.values(), key=lambda e: e["name"].lower()):
            result.append(
                {
                    "name": entry["name"],
                    "path": entry["path"],
                    "formats": sorted(entry["formats"]),
                    "size_gb": round(entry["size_bytes"] / (1024**3), 2),
                    "file_count": entry["file_count"],
                }
            )
        return result


def _model_name(model_root: Path, base_dir: Path) -> str:
    """Derive a human-readable model name from the path.

    Uses the relative path from base_dir, replacing path separators with
    slashes to mimic repo-style names (e.g. "meta-llama/Llama-3.1-8B").
    """
    try:
        rel = model_root.relative_to(base_dir)
        return str(rel)
    except ValueError:
        return model_root.name
