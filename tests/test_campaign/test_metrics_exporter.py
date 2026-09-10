"""Tests for campaign metrics exporter."""

import sys
import urllib.request
from unittest.mock import patch

import pytest

from kitt.campaign.metrics_exporter import (
    CampaignMetricsExporter,
    _escape_field_key,
    _escape_tag,
)


class TestCampaignMetricsExporter:
    def test_update_progress(self):
        exporter = CampaignMetricsExporter()
        exporter.update_campaign_progress(
            total_runs=10,
            completed=5,
            succeeded=4,
            failed=1,
            skipped=0,
            duration_s=3600.0,
        )
        assert exporter._metrics["kitt_campaign_runs_total"] == 10
        assert exporter._metrics["kitt_campaign_runs_succeeded_total"] == 4
        assert exporter._metrics["kitt_campaign_runs_failed_total"] == 1
        assert exporter._metrics["kitt_campaign_progress_pct"] == 50.0
        assert exporter._metrics["kitt_campaign_duration_seconds"] == 3600.0

    def test_progress_zero_total(self):
        exporter = CampaignMetricsExporter()
        exporter.update_campaign_progress(
            total_runs=0,
            completed=0,
            succeeded=0,
            failed=0,
            skipped=0,
            duration_s=0,
        )
        assert exporter._metrics["kitt_campaign_progress_pct"] == 0

    def test_render_prometheus_simple(self):
        exporter = CampaignMetricsExporter()
        exporter.update_campaign_progress(
            total_runs=5,
            completed=3,
            succeeded=2,
            failed=1,
            skipped=0,
            duration_s=120.0,
        )
        output = exporter._render_prometheus()
        assert "kitt_campaign_runs_total 5" in output
        assert "kitt_campaign_runs_succeeded_total 2" in output
        assert "kitt_campaign_runs_failed_total 1" in output
        assert "kitt_campaign_progress_pct 60.0" in output

    def test_render_prometheus_labeled(self):
        exporter = CampaignMetricsExporter()
        exporter.record_benchmark_result(
            model="Qwen-7B",
            engine="vllm",
            benchmark="throughput",
            metrics={"avg_tps": 150.0},
        )
        output = exporter._render_prometheus()
        assert (
            'kitt_benchmark_avg_tps{model="Qwen-7B",engine="vllm",benchmark="throughput"} 150.0'
            in output
        )

    @patch("kitt.campaign.metrics_exporter.urllib.request.urlopen")
    def test_write_influxdb(self, mock_urlopen):
        exporter = CampaignMetricsExporter(
            influxdb_url="http://localhost:8086",
            influxdb_token="test-token",
        )
        exporter.record_benchmark_result(
            model="Qwen-7B",
            engine="vllm",
            benchmark="throughput",
            metrics={"avg_tps": 150.0, "total_iterations": 5},
        )
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert b"benchmark_result" in req.data
        assert b"avg_tps=150.0" in req.data
        assert req.get_header("Authorization") == "Token test-token"

    @patch("kitt.campaign.metrics_exporter.urllib.request.urlopen")
    def test_influxdb_failure_non_fatal(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("connection refused")
        exporter = CampaignMetricsExporter()
        # Should not raise
        exporter.record_benchmark_result(
            model="m",
            engine="e",
            benchmark="b",
            metrics={"avg_tps": 100.0},
        )

    def test_empty_metrics_no_influxdb_write(self):
        exporter = CampaignMetricsExporter()
        with patch("kitt.campaign.metrics_exporter.urllib.request.urlopen") as mock_url:
            exporter.record_benchmark_result(
                model="m",
                engine="e",
                benchmark="b",
                metrics={},
            )
            mock_url.assert_not_called()

    @pytest.mark.skipif(
        sys.platform == "darwin", reason="HTTPServer.shutdown() unreliable on macOS"
    )
    def test_start_stop_server(self):
        exporter = CampaignMetricsExporter(prometheus_port=19100)
        exporter.start()
        assert exporter._server is not None
        assert exporter._thread is not None
        assert exporter._thread.is_alive()
        exporter.stop()
        assert exporter._server is None

    def test_record_multiple_results(self):
        exporter = CampaignMetricsExporter()
        with patch("kitt.campaign.metrics_exporter.urllib.request.urlopen"):
            exporter.record_benchmark_result(
                model="m1",
                engine="e1",
                benchmark="b1",
                metrics={"avg_tps": 100.0},
            )
            exporter.record_benchmark_result(
                model="m2",
                engine="e2",
                benchmark="b2",
                metrics={"avg_tps": 200.0},
            )
        assert len(exporter._labeled_metrics) == 2


class TestEscapeFunctions:
    def test_escape_tag_spaces(self):
        assert _escape_tag("model name") == "model\\ name"

    def test_escape_tag_commas(self):
        assert _escape_tag("a,b") == "a\\,b"

    def test_escape_tag_equals(self):
        assert _escape_tag("a=b") == "a\\=b"

    def test_escape_field_key(self):
        assert _escape_field_key("avg tps") == "avg\\ tps"
