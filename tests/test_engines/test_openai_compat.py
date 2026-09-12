"""Tests for openai_compat HTTP client."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.openai_compat import openai_generate, parse_openai_result


class TestOpenaiGenerate:
    @patch("kitt.engines.openai_compat.urllib.request.urlopen")
    def test_basic_request(self, mock_urlopen):
        response_data = {
            "choices": [{"text": "Hello world"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = openai_generate("http://localhost:8000", "test prompt", model="llama")

        assert result["choices"][0]["text"] == "Hello world"
        assert result["usage"]["prompt_tokens"] == 5

        # Verify the request was made to the right URL
        req = mock_urlopen.call_args[0][0]
        assert req.full_url == "http://localhost:8000/v1/completions"

        # Verify payload
        payload = json.loads(req.data)
        assert payload["prompt"] == "test prompt"
        assert payload["model"] == "llama"

    @patch("kitt.engines.openai_compat.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        error = urllib.error.HTTPError(
            "http://localhost:8000/v1/completions",
            500,
            "Internal Server Error",
            {},
            MagicMock(read=lambda: b"engine error"),
        )
        mock_urlopen.side_effect = error

        with pytest.raises(RuntimeError, match="API request failed"):
            openai_generate("http://localhost:8000", "test")

    @patch("kitt.engines.openai_compat.urllib.request.urlopen")
    def test_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with pytest.raises(RuntimeError, match="Cannot connect"):
            openai_generate("http://localhost:8000", "test")


class TestParseOpenaiResult:
    def test_parse_success(self):
        response = {
            "choices": [{"text": "Generated text here"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        tracker = MagicMock()
        tracker.get_peak_memory_mb.return_value = 4096.0
        tracker.get_average_memory_mb.return_value = 3072.0

        result = parse_openai_result(response, 500.0, tracker)

        assert result.output == "Generated text here"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5
        assert result.metrics.total_latency_ms == 500.0
        assert result.metrics.tps == 5 / 0.5  # 10 tps
        assert result.metrics.gpu_memory_peak_gb == 4.0
        assert result.metrics.gpu_memory_avg_gb == 3.0

    def test_parse_empty_choices(self):
        response = {"choices": [], "usage": {}}
        tracker = MagicMock()
        tracker.get_peak_memory_mb.return_value = 0.0
        tracker.get_average_memory_mb.return_value = 0.0

        result = parse_openai_result(response, 100.0, tracker)
        assert result.output == ""
        assert result.metrics.tps == 0

    def test_parse_missing_usage(self):
        response = {"choices": [{"text": "hi"}]}
        tracker = MagicMock()
        tracker.get_peak_memory_mb.return_value = 0.0
        tracker.get_average_memory_mb.return_value = 0.0

        result = parse_openai_result(response, 100.0, tracker)
        assert result.prompt_tokens == 0
        assert result.completion_tokens == 0
