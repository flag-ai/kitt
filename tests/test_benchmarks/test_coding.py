"""Tests for coding benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.coding import (
    CodingBenchmark,
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
    return CodingBenchmark()


@pytest.fixture
def engine():
    mock = MagicMock()
    mock.generate.return_value = MockResult()
    return mock


class TestCodingBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "coding"
        assert bench.category == "quality_standard"
        assert bench.version == "1.0.0"

    def test_build_prompt(self, bench):
        prompt = bench._build_prompt("Write a function foo()")
        assert "Write a function foo()" in prompt
        assert "```python" in prompt
        assert "Respond with only the Python code" in prompt

    # --- _extract_code ---

    def test_extract_code_from_fenced_block(self, bench):
        output = "Here is the code:\n```python\ndef foo():\n    return 42\n```\nDone."
        code = bench._extract_code(output)
        assert code == "def foo():\n    return 42"

    def test_extract_code_from_bare_fenced_block(self, bench):
        output = "```\ndef bar():\n    pass\n```"
        code = bench._extract_code(output)
        assert code == "def bar():\n    pass"

    def test_extract_code_from_function_def(self, bench):
        output = "Sure, here is:\ndef baz(x):\n    return x + 1"
        code = bench._extract_code(output)
        assert code.startswith("def baz(x):")
        assert "return x + 1" in code

    def test_extract_code_plain_text(self, bench):
        output = "return 42"
        code = bench._extract_code(output)
        assert code == "return 42"

    # --- _test_code ---

    def test_test_code_valid(self, bench):
        code = "def is_palindrome(s):\n    return s == s[::-1]"
        test_code = (
            "assert is_palindrome('aba') == True\nassert is_palindrome('ab') == False"
        )
        passed, syntax_err = bench._test_code(code, test_code, "is_palindrome")
        assert passed is True
        assert syntax_err is False

    def test_test_code_syntax_error(self, bench):
        code = "def foo(\n"
        test_code = "assert foo() == 1"
        passed, syntax_err = bench._test_code(code, test_code, "foo")
        assert passed is False
        assert syntax_err is True

    def test_test_code_assertion_failure(self, bench):
        code = "def add(a, b):\n    return a - b"  # wrong implementation
        test_code = "assert add(2, 3) == 5"
        passed, syntax_err = bench._test_code(code, test_code, "add")
        assert passed is False
        # AssertionError typo in source means it is caught by generic Exception
        assert syntax_err is False

    def test_test_code_runtime_error(self, bench):
        code = "def crash():\n    return 1 / 0"
        test_code = "crash()"
        passed, syntax_err = bench._test_code(code, test_code, "crash")
        assert passed is False
        assert syntax_err is False

    # --- _execute ---

    def test_basic_execution(self, bench, engine):
        engine.generate.return_value = MockResult(
            output="```python\ndef is_palindrome(s):\n    return s == s[::-1]\n```"
        )
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert result.test_name == "coding"
        assert "pass_at_1" in result.metrics
        assert "accuracy" in result.metrics
        assert "syntax_error_rate" in result.metrics
        assert result.metrics["total"] == 1

    def test_engine_error_captured(self, bench, engine):
        engine.generate.side_effect = RuntimeError("OOM")
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.errors) > 0
        assert not result.passed

    def test_sample_size_limits_problems(self, bench, engine):
        engine.generate.return_value = MockResult(output="def foo(): pass")
        config = {"sample_size": 2}
        result = bench._execute(engine, config)
        assert result.metrics["total"] == 2
        assert len(result.outputs) == 2

    def test_outputs_structure(self, bench, engine):
        engine.generate.return_value = MockResult(
            output="```python\ndef is_palindrome(s):\n    return s == s[::-1]\n```"
        )
        config = {"sample_size": 1}
        result = bench._execute(engine, config)
        assert len(result.outputs) == 1
        out = result.outputs[0]
        assert "index" in out
        assert "entry_point" in out
        assert "pass_results" in out
        assert "pass_at_1" in out
        assert "code_sample" in out
