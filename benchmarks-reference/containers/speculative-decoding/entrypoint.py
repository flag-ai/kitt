#!/usr/bin/env python3
"""Speculative decoding — acceptance rate of draft tokens.

Acceptance rate is engine-reported: vLLM and llama.cpp expose per-run
speculative-decoding stats either via a dedicated endpoint or as
fields on the usage block of a completions response. The reference
implementation pulls both shapes; if neither is present (mock engine,
engine without spec-decoding), it falls back to a "not supported"
sentinel.

Acceptance rate is the fraction of draft tokens the verifier kept:
high is good (fewer wasted drafts).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def fetch_stats(engine_url: str) -> dict[str, Any] | None:
    """Try known "speculative stats" endpoints; return first non-empty."""
    for path in ("/metrics/speculative", "/v1/speculative_stats", "/stats/speculative"):
        try:
            r = httpx.get(engine_url.rstrip("/") + path, timeout=5.0)
            r.raise_for_status()
            data = r.json()
            if data:
                return data
        except (httpx.HTTPError, ValueError):
            continue
    return None


def run_load(engine_url: str, model: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Drive a small generation load and collect per-response usage blocks."""
    prompt = cfg.get("prompt", "Write a concise explanation of the Pythagorean theorem.\n")
    max_tokens = int(cfg.get("max_tokens", 128))
    requests = int(cfg.get("requests", 8))
    url = engine_url.rstrip("/") + "/v1/completions"
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    usages: list[dict[str, Any]] = []
    with httpx.Client(timeout=120.0) as client:
        for _ in range(requests):
            try:
                r = client.post(url, json=body)
                r.raise_for_status()
                data = r.json()
            except httpx.HTTPError as exc:
                print(f"spec-dec request failed: {exc}", file=sys.stderr)
                continue
            usages.append(data.get("usage") or {})
    return usages


def acceptance_from_usages(usages: list[dict[str, Any]]) -> tuple[float, int, int]:
    """Sum per-request accepted/proposed draft tokens if present."""
    proposed = 0
    accepted = 0
    for u in usages:
        p = u.get("draft_tokens_proposed") or u.get("speculative_proposed") or 0
        a = u.get("draft_tokens_accepted") or u.get("speculative_accepted") or 0
        proposed += int(p)
        accepted += int(a)
    if proposed == 0:
        return 0.0, 0, 0
    return accepted / proposed, accepted, proposed


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

    start = time.monotonic()
    usages = run_load(args.engine_url, args.model_name, cfg)
    rate, accepted, proposed = acceptance_from_usages(usages)
    endpoint_stats = fetch_stats(args.engine_url) if proposed == 0 else None
    if endpoint_stats:
        try:
            rate = float(endpoint_stats.get("acceptance_rate", rate))
            accepted = int(endpoint_stats.get("accepted_tokens", accepted))
            proposed = int(endpoint_stats.get("proposed_tokens", proposed))
        except (TypeError, ValueError):
            pass
    duration_ms = int((time.monotonic() - start) * 1000)

    metrics = {
        "acceptance_rate": rate,
        "draft_tokens_accepted": accepted,
        "draft_tokens_proposed": proposed,
        "requests": len(usages),
        "stats_source": "endpoint" if endpoint_stats else ("usage" if proposed else "unavailable"),
    }
    payload = {
        "benchmark": "speculative-decoding",
        "score": rate,
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"speculative-decoding: acceptance_rate={rate:.3f} ({accepted}/{proposed}) source={metrics['stats_source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
