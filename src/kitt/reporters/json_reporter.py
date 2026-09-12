"""JSON result output."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from kitt import __version__
from kitt.hardware.fingerprint import SystemInfo
from kitt.runners.suite import SuiteResult


def _default_serializer(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def suite_result_to_dict(
    suite_result: SuiteResult,
    system_info: SystemInfo | None = None,
    engine_name: str = "unknown",
    model_name: str = "unknown",
) -> dict[str, Any]:
    """Convert suite result to a JSON-serializable dict.

    Args:
        suite_result: Results from running a test suite.
        system_info: Optional system hardware information.
        engine_name: Name of the inference engine used.
        model_name: Name/path of the model tested.

    Returns:
        Dictionary suitable for JSON serialization.
    """
    data: dict[str, Any] = {
        "kitt_version": __version__,
        "suite_name": suite_result.suite_name,
        "timestamp": suite_result.timestamp.isoformat(),
        "engine": engine_name,
        "model": model_name,
        "passed": suite_result.passed,
        "total_benchmarks": suite_result.total_benchmarks,
        "passed_count": suite_result.passed_count,
        "failed_count": suite_result.failed_count,
        "total_time_seconds": suite_result.total_time_seconds,
        "results": [],
    }

    if system_info:
        data["system_info"] = asdict(system_info)

    for result in suite_result.results:
        result_dict = {
            "test_name": result.test_name,
            "test_version": result.test_version,
            "run_number": result.run_number,
            "passed": result.passed,
            "metrics": result.metrics,
            "errors": result.errors,
            "warmup_times": result.warmup_times,
            "timestamp": result.timestamp.isoformat(),
        }
        data["results"].append(result_dict)

    return data


def save_json_report(
    suite_result: SuiteResult,
    output_path: Path,
    system_info: SystemInfo | None = None,
    engine_name: str = "unknown",
    model_name: str = "unknown",
    result_store: Any | None = None,
) -> Path:
    """Save suite results as JSON.

    Args:
        suite_result: Results from running a test suite.
        output_path: Path to write JSON file.
        system_info: Optional system hardware information.
        engine_name: Name of the inference engine used.
        model_name: Name/path of the model tested.
        result_store: Optional ResultStore to also persist to database.

    Returns:
        Path to the created JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = suite_result_to_dict(suite_result, system_info, engine_name, model_name)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=_default_serializer)

    # Persist to database if a store is configured
    if result_store is not None:
        try:
            result_store.save_result(data)
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to save result to storage backend"
            )

    return output_path
