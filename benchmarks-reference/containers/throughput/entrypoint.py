#!/usr/bin/env python3
"""Throughput benchmark — tokens per second at steady state.

Fires a configurable number of concurrent generation requests against
the engine and computes aggregate output tokens/sec. Optimized for
signal, not peak numbers — the mock-engine smoke test produces
pathological TPS values and that's fine, the point is to validate the
protocol and the shape of the results JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx


async def one_request(client: httpx.AsyncClient, url: str, model: str, prompt: str, max_tokens: int) -> int:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    r = await client.post(url, json=body, timeout=120.0)
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    if completion_tokens is None:
        text = (data.get("choices", [{}])[0]).get("text", "")
        completion_tokens = max(1, len(text.split()))
    return int(completion_tokens)


async def run(engine_url: str, model: str, cfg: dict[str, Any]) -> dict[str, Any]:
    concurrency = int(cfg.get("concurrency", 8))
    total_requests = int(cfg.get("requests", 32))
    max_tokens = int(cfg.get("max_tokens", 64))
    prompt = cfg.get("prompt", "Write a short poem about the sea.\n")
    url = engine_url.rstrip("/") + "/v1/completions"

    sem = asyncio.Semaphore(concurrency)

    async def guarded(client: httpx.AsyncClient) -> int:
        async with sem:
            return await one_request(client, url, model, prompt, max_tokens)

    start = time.monotonic()
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[guarded(client) for _ in range(total_requests)], return_exceptions=True)
    elapsed = time.monotonic() - start

    tokens = 0
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
            continue
        tokens += r
    tps = tokens / elapsed if elapsed > 0 else 0.0
    return {
        "tokens_per_second": tps,
        "total_output_tokens": tokens,
        "total_requests": total_requests,
        "errors": errors,
        "concurrency": concurrency,
        "duration_s": elapsed,
    }


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
    metrics = asyncio.run(run(args.engine_url, args.model_name, cfg))
    duration_ms = int((time.monotonic() - start) * 1000)

    payload = {
        "benchmark": "throughput",
        "score": metrics["tokens_per_second"],
        "metrics": metrics,
        "duration_ms": duration_ms,
        "metadata": {"model": args.model_name},
    }
    out = Path(args.results)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"throughput: {metrics['tokens_per_second']:.2f} tok/s ({metrics['errors']} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
