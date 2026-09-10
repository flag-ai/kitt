"""Tests for plugin registry index."""

import json
from unittest.mock import MagicMock, patch

from kitt.plugins.registry_index import DEFAULT_INDEX_URL, PluginIndex

SAMPLE_INDEX = {
    "plugins": [
        {
            "name": "kitt-vllm-plus",
            "description": "Extended vLLM support",
            "plugin_type": "engine",
            "min_kitt_version": "1.0.0",
        },
        {
            "name": "kitt-mmlu-extended",
            "description": "Extended MMLU benchmark",
            "plugin_type": "benchmark",
            "min_kitt_version": "1.1.0",
        },
    ]
}


def _mock_urlopen(sample_data):
    """Create a mock for urllib.request.urlopen that returns sample_data."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(sample_data).encode()
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


class TestPluginIndex:
    def test_init_default_url(self):
        index = PluginIndex()
        assert index.index_url == DEFAULT_INDEX_URL
        assert index._cache is None

    def test_init_custom_url(self):
        url = "https://example.com/index.json"
        index = PluginIndex(index_url=url)
        assert index.index_url == url

    def test_search_returns_all_with_empty_query(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = index.search()

        assert len(results) == 2
        names = [p["name"] for p in results]
        assert "kitt-vllm-plus" in names
        assert "kitt-mmlu-extended" in names

    def test_search_filters_by_query_string(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = index.search(query="vllm")

        assert len(results) == 1
        assert results[0]["name"] == "kitt-vllm-plus"

    def test_search_filters_by_plugin_type(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = index.search(plugin_type="benchmark")

        assert len(results) == 1
        assert results[0]["name"] == "kitt-mmlu-extended"

    def test_get_info_returns_plugin_dict(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = index.get_info("kitt-vllm-plus")

        assert info is not None
        assert info["name"] == "kitt-vllm-plus"
        assert info["plugin_type"] == "engine"

    def test_get_info_returns_none_for_unknown(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = index.get_info("nonexistent-plugin")

        assert info is None

    def test_check_compatibility_returns_true_for_compatible_version(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = index.check_compatibility("kitt-vllm-plus", kitt_version="2.0.0")

        assert result is True

    def test_check_compatibility_returns_false_for_incompatible_version(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = index.check_compatibility(
                "kitt-mmlu-extended", kitt_version="0.9.0"
            )

        assert result is False

    def test_check_compatibility_returns_false_for_unknown_plugin(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = index.check_compatibility("nonexistent", kitt_version="2.0.0")

        assert result is False

    def test_fetch_index_caches_result(self):
        index = PluginIndex()
        mock_resp = _mock_urlopen(SAMPLE_INDEX)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            index._fetch_index()
            index._fetch_index()

        # urlopen should only be called once due to caching
        assert mock_open.call_count == 1

    def test_fetch_index_returns_empty_on_error(self):
        index = PluginIndex()

        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            result = index._fetch_index()

        assert result == []
