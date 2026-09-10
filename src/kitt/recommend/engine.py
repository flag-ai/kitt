"""Model recommendation engine."""

import logging
from typing import Any

from .constraints import HardwareConstraints

logger = logging.getLogger(__name__)


class ModelRecommender:
    """Recommend models based on historical benchmark data.

    Queries a ResultStore, filters by constraints, and ranks
    by a quality/performance tradeoff score.
    """

    def __init__(self, result_store) -> None:
        self.store = result_store

    def recommend(
        self,
        constraints: HardwareConstraints | None = None,
        limit: int = 10,
        sort_by: str = "score",
    ) -> list[dict[str, Any]]:
        """Get ranked model recommendations.

        Args:
            constraints: Hardware constraints to filter by.
            limit: Maximum number of recommendations.
            sort_by: Ranking metric ("score", "throughput", "accuracy").

        Returns:
            Sorted list of recommendation dicts.
        """
        # Get all results
        results = self.store.query(order_by="-timestamp", limit=500)
        if not results:
            return []

        # Aggregate by model+engine (use latest result for each)
        seen = {}
        for r in results:
            key = f"{r.get('model', '')}|{r.get('engine', '')}"
            if key not in seen:
                seen[key] = r

        # Filter by constraints
        candidates = []
        for r in seen.values():
            if constraints and not constraints.matches(r):
                continue
            scored = self._score_result(r)
            candidates.append(scored)

        # Sort
        if sort_by == "throughput":
            candidates.sort(key=lambda x: x.get("throughput", 0), reverse=True)
        elif sort_by == "accuracy":
            candidates.sort(key=lambda x: x.get("accuracy", 0), reverse=True)
        else:
            candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        return candidates[:limit]

    def _score_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Compute a composite score for a result.

        Score = normalized_accuracy * 0.6 + normalized_throughput * 0.4

        Returns:
            Enriched result dict with score fields.
        """
        metrics = result.get("metrics", {})
        accuracy = metrics.get("accuracy", 0)
        throughput = metrics.get("avg_tps", 0)

        # Normalize (assume rough ranges)
        norm_acc = min(accuracy, 1.0)
        norm_tps = min(throughput / 100.0, 1.0)  # Normalize to 100 tps max

        score = norm_acc * 0.6 + norm_tps * 0.4

        return {
            **result,
            "accuracy": accuracy,
            "throughput": throughput,
            "score": round(score, 4),
        }

    def pareto_frontier(
        self,
        constraints: HardwareConstraints | None = None,
    ) -> list[dict[str, Any]]:
        """Find models on the Pareto frontier of quality vs performance.

        A model is Pareto-optimal if no other model is better in both
        accuracy and throughput.

        Returns:
            List of Pareto-optimal results.
        """
        candidates = self.recommend(constraints=constraints, limit=500, sort_by="score")
        if not candidates:
            return []

        # Find Pareto frontier
        frontier = []
        for c in candidates:
            dominated = False
            for other in candidates:
                if other is c:
                    continue
                if (
                    other.get("accuracy", 0) >= c.get("accuracy", 0)
                    and other.get("throughput", 0) >= c.get("throughput", 0)
                    and (
                        other.get("accuracy", 0) > c.get("accuracy", 0)
                        or other.get("throughput", 0) > c.get("throughput", 0)
                    )
                ):
                    dominated = True
                    break
            if not dominated:
                frontier.append(c)

        return frontier
