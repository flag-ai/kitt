"""Tests for streaming latency benchmark."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.benchmarks.performance.streaming_latency import StreamingLatencyBenchmark
from kitt.engines.openai_compat import StreamChunk


@pytest.fixture
def benchmark():
    return StreamingLatencyBenchmark()


class TestStreamingLatencyBenchmark:
    def test_metadata(self, benchmark):
        assert benchmark.name == "streaming_latency"
        assert benchmark.category == "performance"

    def test_no_base_url(self, benchmark):
        engine = MagicMock()
        del engine._base_url  # No base_url attribute
        result = benchmark._execute(engine, {})
        assert not result.passed
        assert "base_url" in result.errors[0].lower()

    @patch("kitt.engines.openai_compat.openai_generate_stream")
    def test_successful_streaming(self, mock_stream, benchmark):
        mock_stream.return_value = iter(
            [
                StreamChunk(token="Hello", timestamp_ms=50.0),
                StreamChunk(token=" world", timestamp_ms=80.0),
                StreamChunk(token="!", timestamp_ms=100.0),
            ]
        )

        engine = MagicMock()
        engine._base_url = "http://localhost:8000"
        engine._model_name = "test-model"

        result = benchmark._execute(engine, {"iterations": 1})
        assert result.passed
        assert len(result.outputs) == 1
        assert result.outputs[0]["metrics"]["ttft_ms"] == 50.0

    @patch("kitt.engines.openai_compat.openai_generate_stream")
    def test_empty_stream(self, mock_stream, benchmark):
        mock_stream.return_value = iter([])

        engine = MagicMock()
        engine._base_url = "http://localhost:8000"
        engine._model_name = "test-model"

        result = benchmark._execute(engine, {"iterations": 1})
        assert not result.passed


class TestStreamChunk:
    def test_fields(self):
        chunk = StreamChunk(token="hello", timestamp_ms=42.5)
        assert chunk.token == "hello"
        assert chunk.timestamp_ms == 42.5
