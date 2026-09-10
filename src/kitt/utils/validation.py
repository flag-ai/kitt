"""Input validation utilities."""

from pathlib import Path


def validate_model_path(path: str) -> str | None:
    """Validate a model path exists.

    Returns error message or None if valid.
    """
    p = Path(path)
    if not p.exists():
        return f"Model path does not exist: {path}"
    return None


def validate_engine_name(name: str, available: list[str]) -> str | None:
    """Validate an engine name.

    Returns error message or None if valid.
    """
    if name not in available:
        return f"Engine '{name}' not available. Options: {', '.join(available)}"
    return None


def detect_model_format(path: str) -> str | None:
    """Detect the model format from a file or directory.

    Returns:
        Format string ("gguf", "safetensors", "pytorch") or None if unknown.
    """
    p = Path(path)

    # Single GGUF file
    if p.is_file() and p.suffix.lower() == ".gguf":
        return "gguf"

    if p.is_dir():
        children = list(p.iterdir())
        has_safetensors = any(
            f.suffix == ".safetensors" for f in children if f.is_file()
        )
        has_pytorch = any(
            f.name in ("pytorch_model.bin", "model.bin") or f.suffix in (".pt", ".pth")
            for f in children
            if f.is_file()
        )
        has_gguf = any(f.suffix == ".gguf" for f in children if f.is_file())

        if has_safetensors:
            return "safetensors"
        if has_pytorch:
            return "pytorch"
        if has_gguf:
            return "gguf"

    return None


def validate_model_format(model_path: str, engine_formats: list[str]) -> str | None:
    """Check whether a model's format is compatible with the engine.

    Args:
        model_path: Path to the model file or directory.
        engine_formats: Formats the engine supports (e.g. ["safetensors", "pytorch"]).

    Returns:
        Error message if incompatible, None if OK or format is unknown.
    """
    detected = detect_model_format(model_path)
    if detected is None:
        # Unknown format — let the engine try
        return None

    if detected not in engine_formats:
        return (
            f"Model format '{detected}' is not supported by this engine. "
            f"Supported formats: {', '.join(engine_formats)}"
        )
    return None
