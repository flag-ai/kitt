"""Tests for RAG pipeline benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.rag_pipeline import (
    BUILT_IN_CORPUS,
    RAGPipelineBenchmark,
    SimpleRetriever,
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
    return RAGPipelineBenchmark()


@pytest.fixture
def engine():
    mock = MagicMock()
    mock.generate.return_value = MockResult()
    return mock


# --- SimpleRetriever ---


class TestSimpleRetriever:
    def test_retrieve_returns_list(self):
        docs = ["The cat sat on the mat", "Dogs are great pets"]
        retriever = SimpleRetriever(docs)
        results = retriever.retrieve("cat", top_k=1)
        assert isinstance(results, list)
        assert len(results) == 1

    def test_retrieve_ranks_by_overlap(self):
        docs = [
            "Python is a programming language",
            "Java is also a programming language",
            "Cooking recipes are delicious",
        ]
        retriever = SimpleRetriever(docs)
        results = retriever.retrieve("Python programming", top_k=2)
        assert len(results) == 2
        # The Python doc should rank highest due to word overlap
        assert "Python" in results[0]

    def test_retrieve_top_k_clamps(self):
        docs = ["doc one", "doc two"]
        retriever = SimpleRetriever(docs)
        results = retriever.retrieve("doc", top_k=10)
        assert len(results) == 2

    def test_retrieve_empty_query(self):
        docs = ["some document"]
        retriever = SimpleRetriever(docs)
        results = retriever.retrieve("", top_k=1)
        assert isinstance(results, list)

    def test_retrieve_no_documents(self):
        retriever = SimpleRetriever([])
        results = retriever.retrieve("anything", top_k=3)
        assert results == []


# --- RAGPipelineBenchmark ---


class TestRAGPipelineBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "rag_pipeline"
        assert bench.category == "quality_standard"
        assert bench.version == "1.0.0"

    def test_basic_execution(self, bench, engine):
        engine.generate.return_value = MockResult(output="299792458")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert result.test_name == "rag_pipeline"
        assert result.passed
        assert result.metrics["total"] == 1

    def test_metrics_include_latencies(self, bench, engine):
        engine.generate.return_value = MockResult(output="299792458")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert "e2e_latency_ms" in result.metrics
        assert "retrieval_latency_ms" in result.metrics
        assert "generation_latency_ms" in result.metrics
        assert "answer_accuracy" in result.metrics

    def test_correct_answer_counted(self, bench, engine):
        engine.generate.return_value = MockResult(output="The answer is 299792458 m/s")
        config = {
            "corpus": [BUILT_IN_CORPUS[0]],  # speed of light question
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct"] == 1
        assert result.metrics["answer_accuracy"] == 1.0

    def test_incorrect_answer(self, bench, engine):
        engine.generate.return_value = MockResult(output="I have no idea")
        config = {
            "corpus": [BUILT_IN_CORPUS[0]],  # expects "299792458"
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct"] == 0
        assert result.metrics["answer_accuracy"] == 0.0

    def test_engine_error_captured(self, bench, engine):
        engine.generate.side_effect = RuntimeError("timeout")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.errors) > 0
        assert not result.passed

    def test_sample_size_limits_corpus(self, bench, engine):
        engine.generate.return_value = MockResult(output="some answer")
        config = {"sample_size": 2}
        result = bench._execute(engine, config)
        assert result.metrics["total"] == 2
        assert len(result.outputs) == 2

    def test_outputs_structure(self, bench, engine):
        engine.generate.return_value = MockResult(output="1969")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.outputs) >= 1
        out = result.outputs[0]
        assert "question" in out
        assert "expected" in out
        assert "answer" in out
        assert "correct" in out
        assert "retrieved_docs" in out
        assert "retrieval_ms" in out
        assert "generation_ms" in out
        assert "e2e_ms" in out

    def test_build_prompt(self, bench):
        prompt = bench._build_prompt("What is Python?", "Python is a language.")
        assert "What is Python?" in prompt
        assert "Python is a language." in prompt
        assert "Context:" in prompt
        assert "Answer:" in prompt
