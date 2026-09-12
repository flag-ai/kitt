"""Tests for VLM benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.vlm_benchmark import (
    VLMBenchmark,
)


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0
    ttft_ms: float = 50.0
    gpu_memory_peak_gb: float = 10.0
    gpu_memory_avg_gb: float = 8.0


@dataclass
class MockResult:
    output: str = "test output"
    metrics: MockMetrics = None
    prompt_tokens: int = 10
    completion_tokens: int = 50

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = MockMetrics()


@pytest.fixture
def bench():
    return VLMBenchmark()


@pytest.fixture
def engine():
    """Engine without generate_chat (text-only)."""
    mock = MagicMock(spec=["generate"])
    mock.generate.return_value = MockResult()
    return mock


@pytest.fixture
def chat_engine():
    """Engine with generate_chat (multimodal capable)."""
    mock = MagicMock(spec=["generate", "generate_chat"])
    mock.generate.return_value = MockResult()
    mock.generate_chat.return_value = MockResult()
    return mock


class TestVLMBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "vlm_benchmark"
        assert bench.category == "quality_standard"
        assert bench.version == "1.0.0"

    def test_basic_text_only_execution(self, bench, engine):
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert result.test_name == "vlm_benchmark"
        assert result.passed
        engine.generate.assert_called_once()

    def test_engine_without_chat_uses_generate(self, bench, engine):
        config = {
            "tasks": [
                {
                    "prompt": "Describe something",
                    "image_url": "http://example.com/img.png",
                    "expected_keywords": [],
                },
            ],
        }
        result = bench._execute(engine, config)
        # No generate_chat attribute, so falls back to generate
        engine.generate.assert_called_once()
        assert result.passed

    def test_engine_with_chat_and_image_uses_generate_chat(self, bench, chat_engine):
        config = {
            "tasks": [
                {
                    "prompt": "What is in this image?",
                    "image_url": "http://example.com/img.png",
                    "expected_keywords": [],
                },
            ],
        }
        result = bench._execute(chat_engine, config)
        chat_engine.generate_chat.assert_called_once()
        assert result.passed

    def test_engine_with_chat_no_image_uses_generate(self, bench, chat_engine):
        config = {
            "tasks": [
                {
                    "prompt": "Describe something",
                    "image_url": None,
                    "expected_keywords": [],
                },
            ],
        }
        result = bench._execute(chat_engine, config)
        chat_engine.generate.assert_called_once()
        assert result.passed

    def test_multimodal_supported_metric(self, bench, engine, chat_engine):
        result_no_chat = bench._execute(engine, {"sample_size": 1})
        assert result_no_chat.metrics["multimodal_supported"] is False

        result_chat = bench._execute(chat_engine, {"sample_size": 1})
        assert result_chat.metrics["multimodal_supported"] is True

    def test_keyword_matching_correct(self, bench, engine):
        engine.generate.return_value = MockResult(output="A cute dog playing")
        config = {
            "tasks": [
                {
                    "prompt": "Describe",
                    "image_url": None,
                    "expected_keywords": ["dog"],
                },
            ],
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct"] == 1
        assert result.metrics["accuracy"] == 1.0

    def test_keyword_matching_incorrect(self, bench, engine):
        engine.generate.return_value = MockResult(output="A beautiful sunset")
        config = {
            "tasks": [
                {
                    "prompt": "Describe",
                    "image_url": None,
                    "expected_keywords": ["dog", "cat"],
                },
            ],
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct"] == 0
        assert result.metrics["accuracy"] == 0.0

    def test_no_keywords_counts_as_correct(self, bench, engine):
        engine.generate.return_value = MockResult(output="Anything at all")
        config = {
            "tasks": [
                {
                    "prompt": "Describe",
                    "image_url": None,
                    "expected_keywords": [],
                },
            ],
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct"] == 1

    def test_engine_error_captured(self, bench, engine):
        engine.generate.side_effect = RuntimeError("OOM")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.errors) > 0
        assert not result.passed

    def test_outputs_structure(self, bench, engine):
        engine.generate.return_value = MockResult(output="A scene")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.outputs) == 1
        out = result.outputs[0]
        assert "index" in out
        assert "prompt" in out
        assert "has_image" in out
        assert "correct" in out
        assert "answer" in out
        assert "latency_ms" in out

    def test_avg_latency_metric(self, bench, engine):
        engine.generate.return_value = MockResult(output="response")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert "avg_latency_ms" in result.metrics
        assert result.metrics["avg_latency_ms"] == 250.0
