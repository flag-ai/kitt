"""Generate realistic fake benchmark results for test agents.

Produces result dicts matching the SQLiteStore.save_result() schema
with random but logically consistent metrics.
"""

from __future__ import annotations

import contextlib
import random
from datetime import datetime
from typing import Any

import kitt


def generate_fake_result(
    model_path: str,
    engine_name: str,
    benchmark_name: str,
    suite_name: str,
    agent: dict[str, Any],
) -> dict[str, Any]:
    """Generate a complete fake result dict for a simulated test.

    Args:
        model_path: Model identifier (e.g., "llama-3.1-8b").
        engine_name: Engine name (e.g., "vllm").
        benchmark_name: Benchmark to simulate (e.g., "throughput").
        suite_name: Suite name (e.g., "quick").
        agent: Agent dict from the database (for system_info).

    Returns:
        A result dict ready for ResultService.save_result().
    """
    now = datetime.now().isoformat()
    metrics = _generate_metrics(benchmark_name)

    # Extract model short name from path
    model_name = model_path.rsplit("/", 1)[-1] if "/" in model_path else model_path

    return {
        "model": model_name,
        "engine": engine_name,
        "suite_name": suite_name,
        "timestamp": now,
        "passed": True,
        "total_benchmarks": 1,
        "passed_count": 1,
        "failed_count": 0,
        "total_time_seconds": round(random.uniform(5.0, 15.0), 2),
        "kitt_version": kitt.__version__,
        "results": [
            {
                "test_name": benchmark_name,
                "test_version": "1.0.0",
                "run_number": 1,
                "passed": True,
                "timestamp": now,
                "metrics": metrics,
                "errors": [],
            }
        ],
        "system_info": _build_system_info(agent),
    }


def _build_system_info(agent: dict[str, Any]) -> dict[str, Any]:
    """Build system_info from stored agent hardware details."""
    gpu_info = agent.get("gpu_info", "NVIDIA RTX 4090 24GB")

    # Extract VRAM from gpu_info string (e.g., "NVIDIA RTX 4090 24GB" -> 24)
    vram_gb = 24
    parts = gpu_info.split()
    for i, part in enumerate(parts):
        if part.upper() == "GB" and i > 0:
            with contextlib.suppress(ValueError):
                vram_gb = int(parts[i - 1])
        elif part.upper().endswith("GB"):
            with contextlib.suppress(ValueError):
                vram_gb = int(part[:-2])

    return {
        "gpu": {
            "model": gpu_info,
            "vram_gb": vram_gb,
            "count": agent.get("gpu_count", 1) or 1,
        },
        "cpu": {
            "model": agent.get("cpu_info", "Intel Core i9-13900K"),
            "cores": 24,
        },
        "ram_gb": agent.get("ram_gb", 64) or 64,
        "environment_type": agent.get("environment_type", "native_linux"),
        "fingerprint": f"test-agent-{agent.get('id', 'unknown')}",
    }


def _generate_metrics(benchmark_name: str) -> dict[str, Any]:
    """Generate realistic metrics for a given benchmark type."""
    generators = {
        "throughput": _gen_throughput,
        "latency": _gen_latency,
        "memory_usage": _gen_memory_usage,
        "mmlu": _gen_accuracy,
        "gsm8k": _gen_accuracy,
        "truthfulqa": _gen_accuracy,
        "hellaswag": _gen_accuracy,
    }
    gen = generators.get(benchmark_name, _gen_throughput)
    return gen()


def _gen_throughput() -> dict[str, Any]:
    """Generate throughput benchmark metrics."""
    avg_tps = round(random.uniform(80.0, 180.0), 1)
    iterations = random.randint(3, 10)
    tokens_per_iter = random.randint(200, 500)
    avg_latency = round(1000.0 / avg_tps, 1)

    return {
        "avg_tps": avg_tps,
        "total_iterations": iterations,
        "total_tokens_generated": iterations * tokens_per_iter,
        "avg_latency_ms": avg_latency,
    }


def _gen_latency() -> dict[str, Any]:
    """Generate latency benchmark metrics with consistent percentiles."""
    # TTFT (time to first token)
    ttft_avg = round(random.uniform(20.0, 80.0), 1)
    ttft_min = round(ttft_avg * random.uniform(0.4, 0.7), 1)
    ttft_max = round(ttft_avg * random.uniform(1.5, 3.0), 1)
    ttft_p50 = round(random.uniform(ttft_min, ttft_avg), 1)
    ttft_p95 = round(random.uniform(ttft_avg, ttft_max * 0.9), 1)
    ttft_p99 = round(random.uniform(ttft_p95, ttft_max), 1)
    ttft_std = round(random.uniform(5.0, 20.0), 1)

    # Total latency
    total_avg = round(random.uniform(150.0, 500.0), 1)
    total_min = round(total_avg * random.uniform(0.4, 0.7), 1)
    total_max = round(total_avg * random.uniform(1.5, 3.0), 1)
    total_p50 = round(random.uniform(total_min, total_avg), 1)
    total_p95 = round(random.uniform(total_avg, total_max * 0.9), 1)
    total_p99 = round(random.uniform(total_p95, total_max), 1)
    total_std = round(random.uniform(20.0, 80.0), 1)

    return {
        "ttft_ms": {
            "avg": ttft_avg,
            "min": ttft_min,
            "max": ttft_max,
            "p50": ttft_p50,
            "p95": ttft_p95,
            "p99": ttft_p99,
            "std_dev": ttft_std,
        },
        "total_latency_ms": {
            "avg": total_avg,
            "min": total_min,
            "max": total_max,
            "p50": total_p50,
            "p95": total_p95,
            "p99": total_p99,
            "std_dev": total_std,
        },
    }


def _gen_memory_usage() -> dict[str, Any]:
    """Generate memory usage benchmark metrics."""
    peak_gb = round(random.uniform(8.0, 22.0), 2)
    avg_gb = round(peak_gb * random.uniform(0.6, 0.85), 2)

    return {
        "overall_peak_gpu_memory_gb": peak_gb,
        "overall_avg_gpu_memory_gb": avg_gb,
    }


def _gen_accuracy() -> dict[str, Any]:
    """Generate accuracy-style metrics (mmlu, gsm8k, truthfulqa, hellaswag)."""
    total = random.choice([100, 200, 500, 1000])
    accuracy = round(random.uniform(55.0, 95.0), 1)
    correct = int(total * accuracy / 100.0)

    return {
        "accuracy_pct": accuracy,
        "correct_count": correct,
        "total_count": total,
    }
