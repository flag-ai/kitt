"""Tests for prompt robustness benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.prompt_robustness import PromptRobustnessBenchmark


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0


@dataclass
class MockResult:
    output: str = "The capital of France is Paris."
    metrics: MockMetrics = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = MockMetrics()


@pytest.fixture
def engine():
    mock = MagicMock()
    mock.generate.return_value = MockResult()
    return mock


@pytest.fixture
def bench():
    return PromptRobustnessBenchmark()


class TestPromptRobustnessBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "prompt_robustness"
        assert bench.category == "quality_standard"

    def test_basic_execution(self, bench, engine):
        config = {
            "prompt_groups": [
                {
                    "canonical": "What is 2+2?",
                    "variants": ["Tell me 2+2", "Compute 2+2"],
                }
            ]
        }
        result = bench._execute(engine, config)
        assert result.test_name == "prompt_robustness"
        assert "consistency_score" in result.metrics

    def test_high_consistency_same_output(self, bench, engine):
        engine.generate.return_value = MockResult(output="The answer is Paris.")
        config = {
            "prompt_groups": [
                {
                    "canonical": "Capital of France?",
                    "variants": ["France's capital?"],
                }
            ]
        }
        result = bench._execute(engine, config)
        assert result.metrics["consistency_score"] == 1.0

    def test_low_consistency_different_outputs(self, bench, engine):
        outputs = iter(["Paris is the capital.", "London is big.", "Tokyo is nice."])

        def side_effect(**kwargs):
            return MockResult(output=next(outputs))

        engine.generate.side_effect = side_effect

        config = {
            "prompt_groups": [
                {
                    "canonical": "Capital of France?",
                    "variants": ["France capital?", "What's France's capital?"],
                }
            ]
        }
        result = bench._execute(engine, config)
        assert result.metrics["consistency_score"] < 1.0

    def test_compute_consistency_identical(self, bench):
        score = bench._compute_consistency(["hello world", "hello world"])
        assert score == 1.0

    def test_compute_consistency_empty(self, bench):
        score = bench._compute_consistency([])
        assert score == 1.0

    def test_compute_consistency_single(self, bench):
        score = bench._compute_consistency(["hello"])
        assert score == 1.0

    def test_compute_consistency_disjoint(self, bench):
        score = bench._compute_consistency(["hello world", "foo bar"])
        assert score == 0.0

    def test_compute_consistency_partial_overlap(self, bench):
        score = bench._compute_consistency(
            ["the capital is paris", "paris is the capital city"]
        )
        assert 0 < score < 1

    def test_metrics_include_all_fields(self, bench, engine):
        result = bench._execute(engine, {})
        m = result.metrics
        assert "consistency_score" in m
        assert "semantic_stability" in m
        assert "worst_case_divergence" in m
        assert "num_groups" in m
        assert "total_prompts" in m

    def test_handles_engine_error(self, bench, engine):
        engine.generate.side_effect = RuntimeError("fail")
        config = {
            "prompt_groups": [
                {"canonical": "test", "variants": ["test2"]},
            ]
        }
        result = bench._execute(engine, config)
        assert len(result.errors) > 0

    def test_outputs_per_group(self, bench, engine):
        config = {
            "prompt_groups": [
                {"canonical": "Q1", "variants": ["Q1a"]},
                {"canonical": "Q2", "variants": ["Q2a"]},
            ]
        }
        result = bench._execute(engine, config)
        assert len(result.outputs) == 2
        assert result.outputs[0]["group_index"] == 0
        assert result.outputs[1]["group_index"] == 1
