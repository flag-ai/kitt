#!/usr/bin/env python3
"""Memory benchmark — peak GPU memory observed during a load.

Drives the engine with a short generation workload while polling the
engine's exposed metrics endpoint (or a sidecar nvidia-smi source, if
configured) for GPU memory usage. If no metrics source is reachable
(mock engine, CPU-only test hosts), we emit zeroed metrics so the
output JSON remains protocol-compatible and campaigns don't fail.

The real memory harness plugs BONNIE's GPU info endpoint in via the
``metrics_source`` config knob; the default keeps the reference image
generic.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def poll_metrics(source: str) -> dict[str, float] | None:
    """Pull a single sample from an optional metrics source.

    Expected schema (flexible):
        {"memory_used_mb": 12345.6, "memory_total_mb": 24000.0}
    """
    try:
        r = httpx.get(source, timeout=5.0)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if isinstance(data, dict):
        return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
    return None


def drive_engine(engine_url: str, model: str, cfg: dict[str, Any]) -> int:
    """Fire a small generation workload and return request count."""
    prompt = cfg.get("prompt", "Hello.\n")
    max_tokens = int(cfg.get("max_tokens", 64))
    requests = int(cfg.get("requests", 8))
    url = engine_url.rstrip("/") + "/v1/completions"
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    with httpx.Client(timeout=60.0) as client:
        for _ in range(requests):
            try:
                client.post(url, json=body).raise_for_status()
            except httpx.HTTPError:
                continue
    return requests


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-url", required=True)
    ap.add_argument("--model-name", required=True)
    ap.add_argument("--config", default="/config.json")
    ap.add_argument("--results", default="/results/out.json")
    args = ap.parse_args()

    cfg: dict[str, Any] = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError:
            cfg = {}

    metrics_source = cfg.get("metrics_source", "")

    # Single "before" sample, drive load, single "after+peak" sample.
    # This is intentionally naive — the real version will subscribe to
    # an SSE stream of GPU samples via BONNIE.
    before = poll_metrics(metrics_source) if metrics_source else None
    start = time.monotonic()
    reqs = drive_engine(args.engine_url, args.model_name, cfg)
    after = poll_metrics(metrics_source) if metrics_source else None
    duration_ms = int((time.monotonic() - start) * 1000)

    before = before or {}
    after = after or {}
    peak_mb = max(
        float(before.get("memory_used_mb", 0.0)),
        float(after.get("memory_used_mb", 0.0)),
    )
    total_mb = float(after.get("memory_total_mb") or before.get("memory_total_mb") or 0.0)

    metrics = {
        "peak_memory_mb": peak_mb,
        "total_memory_mb": total_mb,
        "requests_sent": reqs,
        "metrics_source_reachable": bool(after or before),
    }
    payload = {
        "benchmark": "memory",
        # "Score" for memory is inverse: smaller peak → higher score.
        # Ranges 0..1 for the fraction of available memory free.
        "score": (1.0 - (peak_mb / total_mb)) if total_mb > 0 else 0.0,
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name, "metrics_source": metrics_source or "none"},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"memory: peak={peak_mb:.1f} MB (source reachable: {metrics['metrics_source_reachable']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
