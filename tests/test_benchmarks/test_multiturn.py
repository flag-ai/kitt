"""Tests for multi-turn benchmark."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.multiturn import MultiTurnBenchmark
from kitt.engines.base import GenerationMetrics, GenerationResult


@pytest.fixture
def benchmark():
    return MultiTurnBenchmark()


def make_gen_result(text: str, tokens: int = 10) -> GenerationResult:
    return GenerationResult(
        output=text,
        metrics=GenerationMetrics(
            ttft_ms=0,
            tps=10,
            total_latency_ms=100,
            gpu_memory_peak_gb=0,
            gpu_memory_avg_gb=0,
            timestamp=datetime.now(),
        ),
        prompt_tokens=5,
        completion_tokens=tokens,
    )


class TestMultiTurnBenchmark:
    def test_metadata(self, benchmark):
        assert benchmark.name == "multiturn"
        assert benchmark.category == "quality_standard"

    def test_successful_conversation(self, benchmark):
        engine = MagicMock()
        engine.generate.side_effect = [
            make_gen_result("345"),
            make_gen_result("690"),
            make_gen_result("15 and 23"),
        ]

        result = benchmark._execute(
            engine,
            {
                "conversations": [
                    {
                        "name": "test",
                        "turns": ["What is 15*23?", "Double it", "Original numbers?"],
                    }
                ]
            },
        )

        assert result.passed
        assert len(result.outputs) == 1
        assert result.outputs[0]["turns_completed"] == 3
        assert result.outputs[0]["completion_rate"] == 1.0

    def test_engine_error_mid_conversation(self, benchmark):
        engine = MagicMock()
        engine.generate.side_effect = [
            make_gen_result("First response"),
            RuntimeError("OOM"),
        ]

        result = benchmark._execute(
            engine,
            {
                "conversations": [
                    {"name": "test", "turns": ["Turn 1", "Turn 2", "Turn 3"]}
                ]
            },
        )

        assert not result.passed
        assert result.outputs[0]["turns_completed"] == 1

    def test_aggregate_metrics(self, benchmark):
        outputs = [
            {"completion_rate": 1.0, "turns_completed": 3},
            {"completion_rate": 0.5, "turns_completed": 1},
        ]
        metrics = benchmark._aggregate_metrics(outputs)
        assert metrics["total_conversations"] == 2
        assert metrics["avg_completion_rate"] == 0.75
