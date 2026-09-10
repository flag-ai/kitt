"""JSON file-based result store — wraps existing file scanning."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from .base import ResultStore

logger = logging.getLogger(__name__)


class JsonStore(ResultStore):
    """Result store backed by JSON files on disk.

    Wraps the existing kitt-results/ and karr-* scanning pattern
    behind the ResultStore interface.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or Path.cwd()
        self._cache: list[dict[str, Any]] | None = None

    def _invalidate_cache(self) -> None:
        self._cache = None

    def _scan_results(self) -> list[dict[str, Any]]:
        """Scan for result files in kitt-results/ and karr-* directories."""
        if self._cache is not None:
            return self._cache

        results: list[dict[str, Any]] = []

        # kitt-results/
        for metrics_file in sorted(self.base_dir.glob("kitt-results/**/metrics.json")):
            data = self._load_json(metrics_file)
            if data:
                data["_source_path"] = str(metrics_file)
                data["_id"] = self._make_id(metrics_file)
                results.append(data)

        # karr-*/
        for karr_dir in sorted(self.base_dir.glob("karr-*")):
            if karr_dir.is_dir():
                for metrics_file in sorted(karr_dir.glob("**/metrics.json")):
                    data = self._load_json(metrics_file)
                    if data:
                        data["_source_path"] = str(metrics_file)
                        data["_id"] = self._make_id(metrics_file)
                        results.append(data)

        self._cache = results
        return results

    def save_result(self, result_data: dict[str, Any]) -> str:
        """Save result data as a JSON file in kitt-results/."""
        import uuid

        model = result_data.get("model", "unknown").replace("/", "_")
        engine = result_data.get("engine", "unknown")
        timestamp = result_data.get("timestamp", "unknown")[:19].replace(":", "-")
        uid = uuid.uuid4().hex[:8]

        output_dir = (
            self.base_dir / "kitt-results" / model / engine / f"{timestamp}_{uid}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "metrics.json"
        with open(output_path, "w") as f:
            json.dump(result_data, f, indent=2, default=str)

        self._invalidate_cache()
        return self._make_id(output_path)

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        results = self._scan_results()
        for r in results:
            if r.get("_id") == result_id:
                return {k: v for k, v in r.items() if not k.startswith("_")}
        return None

    def query(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        results = self._scan_results()

        if filters:
            results = [
                r for r in results if all(r.get(k) == v for k, v in filters.items())
            ]

        if order_by:
            desc = order_by.startswith("-")
            key = order_by.lstrip("-")
            results = sorted(
                results,
                key=lambda r: r.get(key, ""),
                reverse=desc,
            )

        results = results[offset:]
        if limit is not None:
            results = results[:limit]

        # Strip internal fields
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]

    def list_results(self) -> list[dict[str, Any]]:
        results = self._scan_results()
        return [
            {
                "id": r.get("_id", ""),
                "model": r.get("model", ""),
                "engine": r.get("engine", ""),
                "suite_name": r.get("suite_name", ""),
                "timestamp": r.get("timestamp", ""),
                "passed": r.get("passed", False),
            }
            for r in results
        ]

    def aggregate(
        self,
        group_by: str,
        metrics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        results = self._scan_results()
        groups: dict[str, dict[str, Any]] = {}

        for r in results:
            key = str(r.get(group_by, "unknown"))
            if key not in groups:
                groups[key] = {group_by: key, "count": 0}
                if metrics:
                    for m in metrics:
                        groups[key][f"{m}_values"] = []

            groups[key]["count"] += 1

            if metrics:
                for bench in r.get("results", []):
                    bench_metrics = bench.get("metrics", {})
                    for m in metrics:
                        val = bench_metrics.get(m)
                        if isinstance(val, (int, float)):
                            groups[key][f"{m}_values"].append(val)

        # Compute averages
        output = []
        for group in groups.values():
            row = {k: v for k, v in group.items() if not k.endswith("_values")}
            if metrics:
                for m in metrics:
                    values = group.get(f"{m}_values", [])
                    if values:
                        row[f"{m}_avg"] = sum(values) / len(values)
                    else:
                        row[f"{m}_avg"] = None
            output.append(row)

        return output

    def delete_result(self, result_id: str) -> bool:
        results = self._scan_results()
        for r in results:
            if r.get("_id") == result_id:
                path = Path(r["_source_path"])
                if path.exists():
                    path.unlink()
                    self._invalidate_cache()
                    return True
        return False

    def count(self, filters: dict[str, Any] | None = None) -> int:
        results = self._scan_results()
        if filters:
            results = [
                r for r in results if all(r.get(k) == v for k, v in filters.items())
            ]
        return len(results)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def _make_id(path: Path) -> str:
        """Generate a stable ID from a file path."""
        return hashlib.sha256(str(path).encode()).hexdigest()[:16]
