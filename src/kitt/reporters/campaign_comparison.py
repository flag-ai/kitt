"""Cross-campaign comparison."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def compare_campaigns(
    campaign_a: list[dict[str, Any]],
    campaign_b: list[dict[str, Any]],
    metric_keys: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compare results between two campaigns.

    Matches runs by (model, engine) and computes deltas for numeric metrics.

    Args:
        campaign_a: List of result dicts from campaign A (baseline).
        campaign_b: List of result dicts from campaign B (comparison).
        metric_keys: Specific metrics to compare (None = all numeric).

    Returns:
        Dict mapping run key to comparison data with deltas.
    """
    index_a = _index_by_key(campaign_a)
    index_b = _index_by_key(campaign_b)

    all_keys = sorted(set(index_a.keys()) | set(index_b.keys()))
    comparison = {}

    for key in all_keys:
        result_a = index_a.get(key)
        result_b = index_b.get(key)

        entry: dict[str, Any] = {
            "key": key,
            "in_a": result_a is not None,
            "in_b": result_b is not None,
        }

        if result_a and result_b:
            metrics_a = _extract_flat_metrics(result_a, metric_keys)
            metrics_b = _extract_flat_metrics(result_b, metric_keys)

            deltas: dict[str, dict[str, float | None]] = {}
            for metric in sorted(set(metrics_a.keys()) | set(metrics_b.keys())):
                val_a = metrics_a.get(metric)
                val_b = metrics_b.get(metric)

                if val_a is not None and val_b is not None:
                    delta = val_b - val_a
                    pct_change = (delta / val_a * 100) if val_a != 0 else 0
                    deltas[metric] = {
                        "baseline": val_a,
                        "comparison": val_b,
                        "delta": round(delta, 4),
                        "pct_change": round(pct_change, 2),
                    }
                elif val_a is not None:
                    deltas[metric] = {"baseline": val_a, "comparison": None}
                else:
                    deltas[metric] = {"baseline": None, "comparison": val_b}

            entry["deltas"] = deltas
        elif result_a:
            entry["note"] = "Only in baseline"
        else:
            entry["note"] = "Only in comparison"

        comparison[key] = entry

    return comparison


def _index_by_key(
    results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index results by (model, engine) key."""
    index = {}
    for r in results:
        model = r.get("model", "unknown")
        engine = r.get("engine", "unknown")
        key = f"{model}|{engine}"
        index[key] = r
    return index


def _extract_flat_metrics(
    result: dict[str, Any],
    metric_keys: list[str] | None = None,
) -> dict[str, float]:
    """Extract flat numeric metrics from a result."""
    flat = {}
    for bench in result.get("results", []):
        for key, value in bench.get("metrics", {}).items():
            if isinstance(value, (int, float)):
                if metric_keys is None or key in metric_keys:
                    flat[f"{bench.get('test_name', '')}.{key}"] = float(value)
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, (int, float)):
                        full_key = f"{bench.get('test_name', '')}.{key}.{sub_key}"
                        if metric_keys is None or full_key in metric_keys:
                            flat[full_key] = float(sub_value)
    return flat
