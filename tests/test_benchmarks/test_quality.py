"""Tests for quality benchmark implementations."""

from datetime import datetime
from unittest.mock import MagicMock

from kitt.benchmarks.quality.standard.gsm8k import GSM8KBenchmark
from kitt.benchmarks.quality.standard.hellaswag import HellaSwagBenchmark
from kitt.benchmarks.quality.standard.mmlu import MMLUBenchmark
from kitt.benchmarks.quality.standard.truthfulqa import TruthfulQABenchmark
from kitt.engines.base import GenerationMetrics, GenerationResult


def _mock_engine(output_text="A"):
    """Create a mock engine that returns the given text."""
    engine = MagicMock()
    engine.generate.return_value = GenerationResult(
        output=output_text,
        metrics=GenerationMetrics(
            ttft_ms=10.0,
            tps=50.0,
            total_latency_ms=100.0,
            gpu_memory_peak_gb=4.0,
            gpu_memory_avg_gb=3.5,
            timestamp=datetime.now(),
        ),
        prompt_tokens=20,
        completion_tokens=5,
    )
    return engine


class TestMMLUBenchmark:
    def test_registration(self):
        assert MMLUBenchmark.name == "mmlu"
        assert MMLUBenchmark.category == "quality_standard"

    def test_no_dataset(self):
        bench = MMLUBenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {})
        assert result.test_name == "mmlu"
        assert result.metrics["total_samples"] == 0

    def test_with_questions(self):
        bench = MMLUBenchmark()
        engine = _mock_engine("A")

        config = {
            "dataset": {},
            "sampling": {"temperature": 0.0, "max_tokens": 10},
        }

        # Patch _load_questions to return test data
        questions = [
            {
                "question": "What is 2+2?",
                "subject": "math",
                "choices": ["4", "5", "6", "7"],
                "answer": "A",
            },
            {
                "question": "Capital of France?",
                "subject": "geography",
                "choices": ["London", "Paris", "Berlin", "Madrid"],
                "answer": "A",
            },
        ]
        bench._load_questions = lambda c: questions

        result = bench._execute(engine, config)
        assert result.metrics["total"] == 2
        assert result.metrics["correct"] == 2
        assert result.metrics["accuracy"] == 1.0

    def test_extract_answer(self):
        assert MMLUBenchmark._extract_answer("A") == "A"
        assert MMLUBenchmark._extract_answer("The answer is B.") == "B"
        assert MMLUBenchmark._extract_answer("C. Paris") == "C"
        assert MMLUBenchmark._extract_answer("") == ""


class TestGSM8KBenchmark:
    def test_registration(self):
        assert GSM8KBenchmark.name == "gsm8k"
        assert GSM8KBenchmark.category == "quality_standard"

    def test_no_dataset(self):
        bench = GSM8KBenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {})
        assert result.metrics["total_samples"] == 0

    def test_extract_number(self):
        assert GSM8KBenchmark._extract_number("#### 42") == "42"
        assert GSM8KBenchmark._extract_number("The answer is #### 3.14") == "3.14"
        assert GSM8KBenchmark._extract_number("So the total is 100") == "100"
        assert GSM8KBenchmark._extract_number("#### 1,234") == "1234"

    def test_numbers_match(self):
        assert GSM8KBenchmark._numbers_match("42", "42") is True
        assert GSM8KBenchmark._numbers_match("42.0", "42") is True
        assert GSM8KBenchmark._numbers_match("42", "43") is False

    def test_with_questions(self):
        bench = GSM8KBenchmark()
        engine = _mock_engine("Let me solve this step by step.\n\n#### 42")

        questions = [
            {
                "question": "If John has 20 apples and gets 22 more, how many?",
                "answer": "#### 42",
            },
        ]
        bench._load_questions = lambda c: questions

        result = bench._execute(engine, {"sampling": {"max_tokens": 512}})
        assert result.metrics["correct"] == 1
        assert result.metrics["accuracy"] == 1.0


class TestTruthfulQABenchmark:
    def test_registration(self):
        assert TruthfulQABenchmark.name == "truthfulqa"
        assert TruthfulQABenchmark.category == "quality_standard"

    def test_no_dataset(self):
        bench = TruthfulQABenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {})
        assert result.metrics["total_samples"] == 0

    def test_evaluate_mc1(self):
        mc1_targets = {
            "choices": ["Paris", "London", "Berlin"],
            "labels": [1, 0, 0],
        }
        assert (
            TruthfulQABenchmark._evaluate_mc1("Paris is the capital", mc1_targets)
            is True
        )
        assert (
            TruthfulQABenchmark._evaluate_mc1("London is great", mc1_targets) is False
        )

    def test_evaluate_open(self):
        assert (
            TruthfulQABenchmark._evaluate_open("Yes, Paris is the capital", "Paris")
            is True
        )
        assert TruthfulQABenchmark._evaluate_open("Berlin is nice", "Paris") is False


class TestHellaSwagBenchmark:
    def test_registration(self):
        assert HellaSwagBenchmark.name == "hellaswag"
        assert HellaSwagBenchmark.category == "quality_standard"

    def test_no_dataset(self):
        bench = HellaSwagBenchmark()
        engine = _mock_engine()
        result = bench._execute(engine, {})
        assert result.metrics["total_samples"] == 0

    def test_extract_answer(self):
        assert HellaSwagBenchmark._extract_answer("A") == "A"
        assert HellaSwagBenchmark._extract_answer("B. The cat") == "B"
        assert HellaSwagBenchmark._extract_answer("") == ""

    def test_with_questions(self):
        bench = HellaSwagBenchmark()
        engine = _mock_engine("A")

        questions = [
            {
                "ctx": "The cat sat on",
                "endings": ["the mat", "the dog", "a cloud", "nothing"],
                "label": 0,
            },
        ]
        bench._load_questions = lambda c: questions

        result = bench._execute(engine, {"sampling": {"max_tokens": 10}})
        assert result.metrics["correct"] == 1
        assert result.metrics["accuracy"] == 1.0
