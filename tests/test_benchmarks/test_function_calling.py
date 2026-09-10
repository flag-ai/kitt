"""Tests for function calling benchmark."""

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from kitt.benchmarks.quality.standard.function_calling import FunctionCallingBenchmark


@dataclass
class MockMetrics:
    tps: float = 45.0
    total_latency_ms: float = 250.0


@dataclass
class MockResult:
    output: str = '{"name": "get_weather", "arguments": {"location": "Tokyo"}}'
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
    return FunctionCallingBenchmark()


class TestFunctionCallingBenchmark:
    def test_name_and_category(self, bench):
        assert bench.name == "function_calling"
        assert bench.category == "quality_standard"

    def test_basic_execution(self, bench, engine):
        config = {"sample_size": 2}
        result = bench._execute(engine, config)
        assert result.test_name == "function_calling"
        assert "correct_function_selection_rate" in result.metrics
        assert "json_parse_success_rate" in result.metrics

    def test_correct_function_detection(self, bench, engine):
        engine.generate.return_value = MockResult(
            output='{"name": "get_weather", "arguments": {"location": "Tokyo"}}'
        )
        config = {
            "test_cases": [
                ("What's the weather in Tokyo?", "get_weather", {"location": "Tokyo"})
            ],
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct_function_selection_rate"] == 1.0

    def test_wrong_function(self, bench, engine):
        engine.generate.return_value = MockResult(
            output='{"name": "search_web", "arguments": {"query": "Tokyo weather"}}'
        )
        config = {
            "test_cases": [
                ("What's the weather in Tokyo?", "get_weather", {"location": "Tokyo"})
            ],
        }
        result = bench._execute(engine, config)
        assert result.metrics["correct_function_selection_rate"] == 0.0

    def test_json_parse_failure(self, bench, engine):
        engine.generate.return_value = MockResult(
            output="I'll check the weather for you"
        )
        config = {
            "test_cases": [("Weather?", "get_weather", {})],
        }
        result = bench._execute(engine, config)
        assert result.metrics["json_parse_success_rate"] == 0.0

    def test_hallucinated_function(self, bench, engine):
        engine.generate.return_value = MockResult(
            output='{"name": "nonexistent_function", "arguments": {}}'
        )
        config = {
            "test_cases": [("Do something", "get_weather", {})],
        }
        result = bench._execute(engine, config)
        assert result.metrics["hallucinated_function_rate"] > 0

    def test_parse_function_call_valid_json(self, bench):
        output = '{"name": "calculate", "arguments": {"expression": "2+2"}}'
        parsed = bench._parse_function_call(output)
        assert parsed is not None
        assert parsed["name"] == "calculate"

    def test_parse_function_call_json_in_text(self, bench):
        output = 'Here is the result: {"name": "search_web", "arguments": {"query": "AI"}} done'
        parsed = bench._parse_function_call(output)
        assert parsed is not None
        assert parsed["name"] == "search_web"

    def test_parse_function_call_invalid(self, bench):
        output = "I cannot parse this"
        parsed = bench._parse_function_call(output)
        assert parsed is None

    def test_handles_engine_error(self, bench, engine):
        engine.generate.side_effect = RuntimeError("fail")
        config = {
            "test_cases": [("Test", "get_weather", {})],
        }
        result = bench._execute(engine, config)
        assert len(result.errors) > 0

    def test_sample_size(self, bench, engine):
        config = {"sample_size": 3}
        result = bench._execute(engine, config)
        assert result.metrics["total"] == 3

    def test_format_tools(self, bench):
        tools = [
            {
                "name": "test",
                "description": "Test tool",
                "parameters": {
                    "arg1": {"type": "string", "required": True},
                },
            }
        ]
        formatted = bench._format_tools(tools)
        assert "test" in formatted
        assert "arg1" in formatted

    def test_outputs_structure(self, bench, engine):
        config = {
            "test_cases": [("Test", "get_weather", {})],
        }
        result = bench._execute(engine, config)
        assert len(result.outputs) == 1
        out = result.outputs[0]
        assert "query" in out
        assert "expected_function" in out
        assert "predicted_function" in out

    def test_argument_accuracy(self, bench, engine):
        engine.generate.return_value = MockResult(
            output='{"name": "get_weather", "arguments": {"location": "Tokyo", "unit": "celsius"}}'
        )
        config = {
            "test_cases": [("Weather in Tokyo?", "get_weather", {"location": "Tokyo"})],
        }
        result = bench._execute(engine, config)
        assert result.metrics["argument_accuracy"] == 1.0
