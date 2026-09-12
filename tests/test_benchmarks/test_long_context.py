"""Tests for long-context benchmark."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.performance.long_context import LongContextBenchmark
from kitt.engines.base import GenerationMetrics, GenerationResult


@pytest.fixture
def benchmark():
    return LongContextBenchmark()


def make_gen_result(text: str, prompt_tokens: int = 100) -> GenerationResult:
    return GenerationResult(
        output=text,
        metrics=GenerationMetrics(
            ttft_ms=0,
            tps=10,
            total_latency_ms=500,
            gpu_memory_peak_gb=0,
            gpu_memory_avg_gb=0,
            timestamp=datetime.now(),
        ),
        prompt_tokens=prompt_tokens,
        completion_tokens=20,
    )


class TestLongContextBenchmark:
    def test_metadata(self, benchmark):
        assert benchmark.name == "long_context"
        assert benchmark.category == "performance"

    def test_needle_found(self, benchmark):
        engine = MagicMock()
        engine.generate.return_value = make_gen_result(
            "The secret code is KITT-42-BENCHMARK."
        )

        result = benchmark._execute(
            engine,
            {
                "context_lengths": [4096],
                "needle_positions": [0.5],
            },
        )

        assert result.passed
        assert len(result.outputs) == 1
        assert result.outputs[0]["found_needle"] is True

    def test_needle_not_found(self, benchmark):
        engine = MagicMock()
        engine.generate.return_value = make_gen_result("I don't know the answer.")

        result = benchmark._execute(
            engine,
            {
                "context_lengths": [4096],
                "needle_positions": [0.5],
            },
        )

        assert result.passed  # Still passes — just reports accuracy
        assert result.outputs[0]["found_needle"] is False

    def test_multiple_lengths(self, benchmark):
        engine = MagicMock()
        engine.generate.return_value = make_gen_result("KITT-42")

        result = benchmark._execute(
            engine,
            {
                "context_lengths": [4096, 8192, 16384],
                "needle_positions": [0.5],
            },
        )

        assert len(result.outputs) == 3
        assert result.metrics["total_tests"] == 3
        assert result.metrics["overall_accuracy"] == 1.0

    def test_accuracy_by_length(self, benchmark):
        call_count = 0

        def mock_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            # Only find needle at shorter lengths
            if call_count <= 2:
                return make_gen_result("KITT-42")
            return make_gen_result("I don't know")

        engine = MagicMock()
        engine.generate.side_effect = mock_generate

        result = benchmark._execute(
            engine,
            {
                "context_lengths": [4096, 8192, 16384, 32768],
                "needle_positions": [0.5],
            },
        )

        assert result.metrics["overall_accuracy"] == 0.5
        assert "4096" in result.metrics["accuracy_by_context_length"]

    def test_build_prompt(self, benchmark):
        prompt = benchmark._build_prompt(
            "SECRET_NEEDLE",
            "What is the needle?",
            target_chars=1000,
            position=0.5,
        )
        assert "SECRET_NEEDLE" in prompt
        assert "What is the needle?" in prompt
