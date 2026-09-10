"""Abstract base class for result storage backends."""

from abc import ABC, abstractmethod
from typing import Any


class ResultStore(ABC):
    """Abstract interface for storing and querying benchmark results."""

    @abstractmethod
    def save_result(self, result_data: dict[str, Any]) -> str:
        """Save a benchmark result.

        Args:
            result_data: Parsed metrics.json content.

        Returns:
            Unique identifier for the saved result.
        """

    @abstractmethod
    def get_result(self, result_id: str) -> dict[str, Any] | None:
        """Retrieve a single result by ID.

        Args:
            result_id: Unique identifier from save_result().

        Returns:
            Result data dict or None if not found.
        """

    @abstractmethod
    def query(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query results with optional filtering, ordering, and pagination.

        Args:
            filters: Key-value pairs for exact match filtering.
                     Supported keys: model, engine, suite_name, passed.
            order_by: Field name to sort by. Prefix with '-' for descending.
            limit: Maximum number of results to return.
            offset: Number of results to skip (for pagination).

        Returns:
            List of matching result dicts.
        """

    @abstractmethod
    def list_results(self) -> list[dict[str, Any]]:
        """List all stored results (summary view).

        Returns:
            List of result summaries (id, model, engine, suite, timestamp, passed).
        """

    @abstractmethod
    def aggregate(
        self,
        group_by: str,
        metrics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Aggregate results grouped by a field.

        Args:
            group_by: Field to group by (e.g., 'model', 'engine').
            metrics: Metric names to aggregate (avg). If None, counts only.

        Returns:
            List of dicts with group key, count, and optional metric averages.
        """

    @abstractmethod
    def delete_result(self, result_id: str) -> bool:
        """Delete a result by ID.

        Returns:
            True if deleted, False if not found.
        """

    @abstractmethod
    def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count results matching optional filters."""

    def close(self) -> None:  # noqa: B027
        """Release any held resources. Override if needed."""
