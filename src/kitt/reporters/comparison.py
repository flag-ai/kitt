"""Compare benchmark results across runs."""

from typing import Any


def compare_metrics(
    results: list[dict[str, Any]],
    metric_keys: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Compare metrics across multiple result sets.

    Args:
        results: List of result dicts (from JSON reporter).
        metric_keys: Specific metrics to compare (None = all numeric metrics).

    Returns:
        Dict mapping metric name to comparison stats.
    """
    if not results:
        return {}

    # Collect all metrics from all results
    all_metrics: dict[str, list[float]] = {}

    for result in results:
        for bench_result in result.get("results", []):
            metrics = bench_result.get("metrics", {})
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and (
                    metric_keys is None or key in metric_keys
                ):
                    if key not in all_metrics:
                        all_metrics[key] = []
                    all_metrics[key].append(float(value))

    # Calculate comparison stats
    comparison = {}
    for key, values in all_metrics.items():
        comparison[key] = {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "range": max(values) - min(values),
            "count": len(values),
        }
        if len(values) > 1:
            avg = comparison[key]["avg"]
            variance = sum((v - avg) ** 2 for v in values) / len(values)
            comparison[key]["std_dev"] = variance**0.5
            comparison[key]["cv_percent"] = (
                (comparison[key]["std_dev"] / avg * 100) if avg != 0 else 0
            )

    return comparison
