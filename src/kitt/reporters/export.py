"""Export results to CSV and Parquet formats."""

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def flatten_result(result_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a KITT result JSON into rows suitable for tabular export.

    Each benchmark run becomes one row. Nested metrics are flattened
    with dot notation (e.g., "ttft_ms.avg").

    Args:
        result_data: Parsed metrics.json content.

    Returns:
        List of flat dicts, one per benchmark run.
    """
    rows = []
    base = {
        "model": result_data.get("model", ""),
        "engine": result_data.get("engine", ""),
        "suite_name": result_data.get("suite_name", ""),
        "timestamp": result_data.get("timestamp", ""),
        "kitt_version": result_data.get("kitt_version", ""),
    }

    for bench in result_data.get("results", []):
        row = {**base}
        row["test_name"] = bench.get("test_name", "")
        row["test_version"] = bench.get("test_version", "")
        row["run_number"] = bench.get("run_number", 1)
        row["passed"] = bench.get("passed", False)

        # Flatten metrics
        for key, value in bench.get("metrics", {}).items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, (int, float)):
                        row[f"{key}.{sub_key}"] = sub_value
            elif isinstance(value, (int, float, str, bool)):
                row[key] = value

        rows.append(row)

    return rows


def export_to_csv(
    result_data: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    """Export results to CSV.

    Args:
        result_data: List of result dicts (from metrics.json files).
        output_path: Path for the output CSV file.

    Returns:
        Path to the created CSV file.
    """
    all_rows = []
    for data in result_data:
        all_rows.extend(flatten_result(data))

    if not all_rows:
        raise ValueError("No data to export")

    # Collect all column names
    columns = list(dict.fromkeys(col for row in all_rows for col in row))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(all_rows)

    logger.info(f"Exported {len(all_rows)} rows to {output_path}")
    return output_path


def export_to_parquet(
    result_data: list[dict[str, Any]],
    output_path: Path,
) -> Path:
    """Export results to Parquet format.

    Requires pyarrow.

    Args:
        result_data: List of result dicts.
        output_path: Path for the output Parquet file.

    Returns:
        Path to the created Parquet file.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError(
            "pyarrow is required for Parquet export. Install with: pip install pyarrow"
        ) from None

    all_rows = []
    for data in result_data:
        all_rows.extend(flatten_result(data))

    if not all_rows:
        raise ValueError("No data to export")

    # Convert to columnar format
    columns = list(dict.fromkeys(col for row in all_rows for col in row))

    arrays = {}
    for col in columns:
        values = [row.get(col) for row in all_rows]
        arrays[col] = values

    table = pa.table(arrays)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, str(output_path))

    logger.info(f"Exported {len(all_rows)} rows to {output_path}")
    return output_path
