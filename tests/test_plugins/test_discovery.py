"""Tests for plugin discovery."""

from unittest.mock import MagicMock, patch

from kitt.plugins.discovery import (
    _load_entry_points,
    discover_external_benchmarks,
    discover_external_engines,
    discover_external_reporters,
    discover_plugins,
)


class TestLoadEntryPoints:
    def test_returns_empty_list_when_no_plugins(self):
        result = _load_entry_points("kitt.engines")
        # In a test env there are no kitt plugins installed
        assert isinstance(result, list)

    def test_returns_empty_on_exception(self):
        with patch("importlib.metadata.entry_points", side_effect=Exception("fail")):
            result = _load_entry_points("kitt.engines")
            assert result == []


class TestDiscoverExternalEngines:
    def test_returns_empty_when_none_installed(self):
        result = discover_external_engines()
        assert isinstance(result, list)

    def test_loads_engine_from_entry_point(self):
        mock_ep = MagicMock()
        mock_ep.name = "test_engine"
        mock_cls = type("TestEngine", (), {"name": staticmethod(lambda: "test")})
        mock_ep.load.return_value = mock_cls

        with patch("kitt.plugins.discovery._load_entry_points", return_value=[mock_ep]):
            result = discover_external_engines()
            assert len(result) == 1
            assert result[0] is mock_cls

    def test_handles_load_failure_gracefully(self):
        mock_ep = MagicMock()
        mock_ep.name = "bad_engine"
        mock_ep.load.side_effect = ImportError("missing")

        with patch("kitt.plugins.discovery._load_entry_points", return_value=[mock_ep]):
            result = discover_external_engines()
            assert result == []


class TestDiscoverExternalBenchmarks:
    def test_returns_empty_when_none_installed(self):
        result = discover_external_benchmarks()
        assert isinstance(result, list)

    def test_loads_benchmark_from_entry_point(self):
        mock_ep = MagicMock()
        mock_ep.name = "test_bench"
        mock_cls = type("TestBench", (), {"name": "test"})
        mock_ep.load.return_value = mock_cls

        with patch("kitt.plugins.discovery._load_entry_points", return_value=[mock_ep]):
            result = discover_external_benchmarks()
            assert len(result) == 1

    def test_handles_failure(self):
        mock_ep = MagicMock()
        mock_ep.name = "bad_bench"
        mock_ep.load.side_effect = Exception("boom")

        with patch("kitt.plugins.discovery._load_entry_points", return_value=[mock_ep]):
            result = discover_external_benchmarks()
            assert result == []


class TestDiscoverExternalReporters:
    def test_returns_empty_when_none_installed(self):
        result = discover_external_reporters()
        assert isinstance(result, list)


class TestDiscoverPlugins:
    def test_returns_dict_with_all_groups(self):
        result = discover_plugins()
        assert "engines" in result
        assert "benchmarks" in result
        assert "reporters" in result

    def test_aggregates_all_groups(self):
        mock_engine = type("E", (), {})
        mock_bench = type("B", (), {})

        with (
            patch(
                "kitt.plugins.discovery.discover_external_engines",
                return_value=[mock_engine],
            ),
            patch(
                "kitt.plugins.discovery.discover_external_benchmarks",
                return_value=[mock_bench],
            ),
            patch(
                "kitt.plugins.discovery.discover_external_reporters",
                return_value=[],
            ),
        ):
            result = discover_plugins()
            assert len(result["engines"]) == 1
            assert len(result["benchmarks"]) == 1
            assert len(result["reporters"]) == 0
