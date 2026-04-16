#!/usr/bin/env python3
"""Smoke test for every reference benchmark.

Starts the stdlib mock_engine in a thread, then exec's every
entrypoint in-process against it. Asserts each container writes a
/results/out.json with the required protocol keys.

Deliberately lightweight — the goal is "does the entrypoint run and
produce valid JSON?", not "does it give accurate results". The
mock-engine returns canned answers tuned to the inline datasets (see
mock_engine.py).

Usage:
    python3 benchmarks-reference/tools/smoke_test.py
    python3 benchmarks-reference/tools/smoke_test.py --only throughput latency

Exit code 0 on success, non-zero on failure. Used by
`make smoke-benchmarks` and the CI matrix job.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Allow running the script from any CWD — resolve paths relative to
# the benchmarks-reference root.
SCRIPT_DIR = Path(__file__).resolve().parent
BENCHMARKS_ROOT = SCRIPT_DIR.parent
REPO_ROOT = BENCHMARKS_ROOT.parent

# Make our mock_engine module importable.
sys.path.insert(0, str(SCRIPT_DIR))
from mock_engine import MockEngineServer  # noqa: E402

REQUIRED_KEYS = {"benchmark", "score", "metrics", "duration_ms"}

# Every reference benchmark + its entrypoint script, keyed by name.
BENCHMARKS: dict[str, Path] = {
    "throughput": BENCHMARKS_ROOT / "containers" / "throughput" / "entrypoint.py",
    "latency": BENCHMARKS_ROOT / "containers" / "latency" / "entrypoint.py",
    "memory": BENCHMARKS_ROOT / "containers" / "memory" / "entrypoint.py",
    "warmup-analysis": BENCHMARKS_ROOT / "containers" / "warmup-analysis" / "entrypoint.py",
    "streaming-latency": BENCHMARKS_ROOT / "containers" / "streaming-latency" / "entrypoint.py",
    "long-context": BENCHMARKS_ROOT / "containers" / "long-context" / "entrypoint.py",
    "tensor-parallel": BENCHMARKS_ROOT / "containers" / "tensor-parallel" / "entrypoint.py",
    "speculative-decoding": BENCHMARKS_ROOT / "containers" / "speculative-decoding" / "entrypoint.py",
    "humaneval": BENCHMARKS_ROOT / "containers" / "humaneval" / "entrypoint.py",
    "vlm": BENCHMARKS_ROOT / "containers" / "vlm" / "entrypoint.py",
    "rag-pipeline": BENCHMARKS_ROOT / "containers" / "rag-pipeline" / "entrypoint.py",
    "function-calling": BENCHMARKS_ROOT / "containers" / "function-calling" / "entrypoint.py",
    "multiturn": BENCHMARKS_ROOT / "containers" / "multiturn" / "entrypoint.py",
}

# Per-benchmark minimal config so smoke runs finish in seconds.
CONFIGS: dict[str, dict] = {
    "throughput": {"requests": 2, "concurrency": 2, "max_tokens": 4},
    "latency": {"runs": 2, "max_tokens": 4, "stream": False},
    "memory": {"requests": 2, "max_tokens": 4},
    "warmup-analysis": {"runs": 3, "skip_warmup": 1, "max_tokens": 4},
    "streaming-latency": {"runs": 2, "max_tokens": 4, "stall_threshold_ms": 10000},
    "long-context": {"context_lengths": [128], "depths": [0.5], "trials_per_cell": 1, "max_tokens": 4},
    "tensor-parallel": {"requests": 2, "concurrency": 1, "max_tokens": 4, "gpus": 1},
    "speculative-decoding": {"requests": 2, "max_tokens": 4},
    "humaneval": {"timeout_s": 4.0},
    "vlm": {"max_tokens": 4},
    "rag-pipeline": {"top_k": 2, "max_tokens": 8},
    "function-calling": {},
    "multiturn": {"max_tokens": 4},
}


def run_entrypoint(script: Path, engine_url: str, results_path: Path, config_path: Path) -> None:
    argv = [
        str(script),
        "--engine-url", engine_url,
        "--model-name", "mock-model",
        "--config", str(config_path),
        "--results", str(results_path),
    ]
    old_argv = sys.argv
    try:
        sys.argv = argv
        # Isolate entrypoint globals — we don't want them bleeding
        # into the smoke harness.
        spec = importlib.util.spec_from_file_location(f"bench_{script.parent.name.replace('-', '_')}", script)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load spec for {script}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rc = module.main()
        if rc != 0:
            raise RuntimeError(f"entrypoint returned {rc}")
    finally:
        sys.argv = old_argv


def validate_output(name: str, path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{name}: results file not written"]
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{name}: results not valid JSON: {exc}"]
    missing = REQUIRED_KEYS - set(data)
    if missing:
        errors.append(f"{name}: missing required keys {sorted(missing)}")
    if data.get("benchmark") and data["benchmark"] != name:
        # Not fatal — the image name is canonical and may differ from
        # the filesystem dir name — just log.
        pass
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="Run only these benchmark names")
    args = ap.parse_args()

    selected = args.only or list(BENCHMARKS)
    unknown = [name for name in selected if name not in BENCHMARKS]
    if unknown:
        print(f"unknown benchmarks: {unknown}", file=sys.stderr)
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="kitt-bench-smoke-"))
    try:
        with MockEngineServer() as srv:
            engine_url = f"http://127.0.0.1:{srv.port}"
            print(f"mock-engine at {engine_url}")
            all_errors: list[str] = []
            for name in selected:
                script = BENCHMARKS[name]
                results_path = workdir / f"{name}-out.json"
                config_path = workdir / f"{name}-config.json"
                config_path.write_text(json.dumps(CONFIGS.get(name, {})))
                print(f"  → {name}")
                try:
                    run_entrypoint(script, engine_url, results_path, config_path)
                except Exception as exc:  # noqa: BLE001 — smoke loop collects everything
                    all_errors.append(f"{name}: entrypoint crashed: {exc}")
                    continue
                all_errors.extend(validate_output(name, results_path))
        if all_errors:
            print("FAIL:", file=sys.stderr)
            for e in all_errors:
                print(f"  {e}", file=sys.stderr)
            return 1
        print(f"OK: {len(selected)} benchmarks smoke-tested")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
