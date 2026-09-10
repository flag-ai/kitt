"""Tests for model recommendation engine."""

from unittest.mock import MagicMock

from kitt.recommend.constraints import HardwareConstraints
from kitt.recommend.engine import ModelRecommender


def _make_result(model, engine, accuracy=0.8, avg_tps=50.0, peak_vram_gb=8.0):
    """Helper to create a mock result dict."""
    return {
        "model": model,
        "engine": engine,
        "passed": True,
        "timestamp": "2025-01-15T12:00:00Z",
        "metrics": {
            "accuracy": accuracy,
            "avg_tps": avg_tps,
            "peak_vram_gb": peak_vram_gb,
        },
    }


class TestRecommend:
    def test_returns_ranked_results(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result("model-a", "vllm", accuracy=0.9, avg_tps=80),
            _make_result("model-b", "vllm", accuracy=0.7, avg_tps=40),
        ]
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend()

        assert len(results) == 2
        # Higher score should come first
        assert results[0]["model"] == "model-a"

    def test_with_empty_store(self):
        store = MagicMock()
        store.query.return_value = []
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend()
        assert results == []

    def test_filters_by_constraints(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result(
                "small-model", "vllm", accuracy=0.7, avg_tps=60, peak_vram_gb=4.0
            ),
            _make_result(
                "large-model", "vllm", accuracy=0.9, avg_tps=30, peak_vram_gb=20.0
            ),
        ]
        recommender = ModelRecommender(result_store=store)
        constraints = HardwareConstraints(max_vram_gb=10.0)
        results = recommender.recommend(constraints=constraints)

        assert len(results) == 1
        assert results[0]["model"] == "small-model"

    def test_limits_results(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result(f"model-{i}", "vllm") for i in range(20)
        ]
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend(limit=5)
        assert len(results) == 5

    def test_sort_by_throughput(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result("slow", "vllm", accuracy=0.95, avg_tps=10),
            _make_result("fast", "vllm", accuracy=0.7, avg_tps=100),
        ]
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend(sort_by="throughput")

        assert results[0]["model"] == "fast"

    def test_sort_by_accuracy(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result("low-acc", "vllm", accuracy=0.5, avg_tps=100),
            _make_result("high-acc", "vllm", accuracy=0.95, avg_tps=10),
        ]
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend(sort_by="accuracy")

        assert results[0]["model"] == "high-acc"

    def test_deduplicates_by_model_engine(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result("model-a", "vllm", accuracy=0.9, avg_tps=80),
            _make_result("model-a", "vllm", accuracy=0.85, avg_tps=75),
        ]
        recommender = ModelRecommender(result_store=store)
        results = recommender.recommend()

        assert len(results) == 1
        # First result (latest) should be kept
        assert results[0]["accuracy"] == 0.9


class TestScoreResult:
    def test_computes_correct_score(self):
        store = MagicMock()
        recommender = ModelRecommender(result_store=store)

        result = _make_result("model-a", "vllm", accuracy=0.8, avg_tps=50)
        scored = recommender._score_result(result)

        # norm_acc = min(0.8, 1.0) = 0.8
        # norm_tps = min(50 / 100, 1.0) = 0.5
        # score = 0.8 * 0.6 + 0.5 * 0.4 = 0.48 + 0.20 = 0.68
        assert scored["score"] == 0.68
        assert scored["accuracy"] == 0.8
        assert scored["throughput"] == 50.0

    def test_score_clamps_high_values(self):
        store = MagicMock()
        recommender = ModelRecommender(result_store=store)

        result = _make_result("model", "vllm", accuracy=1.5, avg_tps=200)
        scored = recommender._score_result(result)

        # norm_acc = min(1.5, 1.0) = 1.0
        # norm_tps = min(200 / 100, 1.0) = 1.0
        # score = 1.0 * 0.6 + 1.0 * 0.4 = 1.0
        assert scored["score"] == 1.0


class TestParetoFrontier:
    def test_returns_non_dominated_results(self):
        store = MagicMock()
        store.query.return_value = [
            _make_result("pareto-1", "vllm", accuracy=0.9, avg_tps=30),
            _make_result("pareto-2", "vllm", accuracy=0.7, avg_tps=90),
            _make_result("dominated", "vllm", accuracy=0.6, avg_tps=20),
        ]
        recommender = ModelRecommender(result_store=store)
        frontier = recommender.pareto_frontier()

        names = [r["model"] for r in frontier]
        assert "pareto-1" in names
        assert "pareto-2" in names
        assert "dominated" not in names

    def test_empty_store_returns_empty(self):
        store = MagicMock()
        store.query.return_value = []
        recommender = ModelRecommender(result_store=store)
        frontier = recommender.pareto_frontier()
        assert frontier == []
