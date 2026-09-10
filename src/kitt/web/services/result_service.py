"""Result service wrapping the existing storage layer for web use."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ResultService:
    """Web-facing service for querying and managing results.

    Wraps the existing SQLiteStore (or any ResultStore) with
    web-specific convenience methods.
    """

    def __init__(self, store: Any) -> None:
        self._store = store

    def list_results(
        self,
        model: str = "",
        engine: str = "",
        suite_name: str = "",
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        """List results with optional filters and pagination."""
        filters: dict[str, Any] = {}
        if model:
            filters["model"] = model
        if engine:
            filters["engine"] = engine
        if suite_name:
            filters["suite_name"] = suite_name

        total = self._store.count(filters=filters or None)
        offset = (page - 1) * per_page
        items = self._store.query(
            filters=filters or None,
            order_by="-timestamp",
            limit=per_page,
            offset=offset,
        )

        pages = (total + per_page - 1) // per_page if per_page else 0
        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        """Get a single result by ID."""
        return self._store.get_result(result_id)

    def delete_result(self, result_id: str) -> bool:
        """Delete a result by ID."""
        return self._store.delete_result(result_id)

    def aggregate(
        self, group_by: str, metrics: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Aggregate results by a field."""
        return self._store.aggregate(group_by=group_by, metrics=metrics)

    def get_summary(self) -> dict[str, Any]:
        """Get overall results summary for the dashboard."""
        total = self._store.count()
        passed = self._store.count(filters={"passed": True})
        pass_rate = round(passed / total * 100) if total > 0 else 0

        by_engine = self._store.aggregate(group_by="engine")
        by_model = self._store.aggregate(group_by="model")

        return {
            "total_results": total,
            "total_passed": passed,
            "pass_rate": pass_rate,
            "engine_count": len(by_engine),
            "model_count": len(by_model),
            "engines": by_engine,
            "models": by_model,
        }

    def get_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent results."""
        return self._store.query(order_by="-timestamp", limit=limit)

    def compare_results(self, result_ids: list[str]) -> list[dict[str, Any]]:
        """Get multiple results for comparison."""
        results = []
        for rid in result_ids:
            r = self._store.get_result(rid)
            if r:
                results.append(r)
        return results

    def save_result(self, result_data: dict[str, Any]) -> None:
        """Persist a result received from an agent."""
        self._store.save_result(result_data)

    def import_directory(self, directory: Path) -> int:
        """Import results from a directory tree."""
        if hasattr(self._store, "import_directory"):
            return self._store.import_directory(directory)
        return 0
