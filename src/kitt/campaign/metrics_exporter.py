"""Metrics exporter for campaign monitoring.

Provides a Prometheus-compatible metrics endpoint and writes results
to InfluxDB in line protocol format for historical tracking.
"""

import logging
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

logger = logging.getLogger(__name__)


class CampaignMetricsExporter:
    """Export campaign metrics to Prometheus and InfluxDB.

    Exposes a /metrics HTTP endpoint for Prometheus scraping
    and writes results to InfluxDB via the line protocol API.
    """

    def __init__(
        self,
        prometheus_port: int = 9100,
        influxdb_url: str | None = None,
        influxdb_token: str | None = None,
        influxdb_org: str = "kitt",
        influxdb_bucket: str = "benchmarks",
    ) -> None:
        self.prometheus_port = prometheus_port
        self.influxdb_url = influxdb_url or "http://localhost:8086"
        self.influxdb_token = influxdb_token or "kitt-influx-token"
        self.influxdb_org = influxdb_org
        self.influxdb_bucket = influxdb_bucket

        # Current state for Prometheus
        self._metrics: dict[str, float] = {
            "kitt_campaign_runs_total": 0,
            "kitt_campaign_runs_succeeded_total": 0,
            "kitt_campaign_runs_failed_total": 0,
            "kitt_campaign_runs_skipped_total": 0,
            "kitt_campaign_progress_pct": 0,
            "kitt_campaign_duration_seconds": 0,
        }
        self._labeled_metrics: list = []

        self._server: HTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start the Prometheus metrics HTTP server."""
        exporter = self

        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    body = exporter._render_prometheus()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(body.encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress default logging

        self._server = HTTPServer(("0.0.0.0", self.prometheus_port), MetricsHandler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Prometheus metrics server started on port {self.prometheus_port}")

    def stop(self) -> None:
        """Stop the Prometheus metrics HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None
            self._thread = None
            logger.info("Prometheus metrics server stopped")

    def update_campaign_progress(
        self,
        total_runs: int,
        completed: int,
        succeeded: int,
        failed: int,
        skipped: int,
        duration_s: float,
    ) -> None:
        """Update campaign-level metrics."""
        self._metrics["kitt_campaign_runs_total"] = total_runs
        self._metrics["kitt_campaign_runs_succeeded_total"] = succeeded
        self._metrics["kitt_campaign_runs_failed_total"] = failed
        self._metrics["kitt_campaign_runs_skipped_total"] = skipped
        self._metrics["kitt_campaign_duration_seconds"] = round(duration_s, 1)
        self._metrics["kitt_campaign_progress_pct"] = (
            round(completed / total_runs * 100, 1) if total_runs > 0 else 0
        )

    def record_benchmark_result(
        self,
        model: str,
        engine: str,
        benchmark: str,
        metrics: dict[str, float],
    ) -> None:
        """Record a benchmark result for both Prometheus and InfluxDB."""
        # Update labeled metrics for Prometheus
        for key, value in metrics.items():
            self._labeled_metrics.append(
                {
                    "name": f"kitt_benchmark_{key}",
                    "labels": {
                        "model": model,
                        "engine": engine,
                        "benchmark": benchmark,
                    },
                    "value": value,
                }
            )

        # Write to InfluxDB
        self._write_influxdb(model, engine, benchmark, metrics)

    def _render_prometheus(self) -> str:
        """Render metrics in Prometheus text format."""
        lines = []

        # Simple gauges
        for name, value in self._metrics.items():
            lines.append(f"{name} {value}")

        # Labeled metrics
        for m in self._labeled_metrics:
            label_str = ",".join(f'{k}="{v}"' for k, v in m["labels"].items())
            lines.append(f"{m['name']}{{{label_str}}} {m['value']}")

        lines.append("")
        return "\n".join(lines)

    def _write_influxdb(
        self,
        model: str,
        engine: str,
        benchmark: str,
        metrics: dict[str, float],
    ) -> None:
        """Write a result point to InfluxDB using line protocol."""
        if not metrics:
            return

        # Build line protocol
        tags = f"model={_escape_tag(model)},engine={_escape_tag(engine)},benchmark={_escape_tag(benchmark)}"
        fields = ",".join(
            f"{_escape_field_key(k)}={v}"
            for k, v in metrics.items()
            if isinstance(v, (int, float))
        )

        if not fields:
            return

        timestamp_ns = int(time.time() * 1e9)
        line = f"benchmark_result,{tags} {fields} {timestamp_ns}"

        url = (
            f"{self.influxdb_url}/api/v2/write"
            f"?org={self.influxdb_org}&bucket={self.influxdb_bucket}&precision=ns"
        )

        try:
            req = urllib.request.Request(
                url,
                data=line.encode(),
                method="POST",
                headers={
                    "Authorization": f"Token {self.influxdb_token}",
                    "Content-Type": "text/plain",
                },
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.debug(f"InfluxDB write failed (non-fatal): {e}")


def _escape_tag(value: str) -> str:
    """Escape special characters in InfluxDB tag values."""
    return value.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def _escape_field_key(key: str) -> str:
    """Escape special characters in InfluxDB field keys."""
    return key.replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")
