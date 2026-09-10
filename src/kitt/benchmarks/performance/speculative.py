"""Speculative decoding benchmark — compare with/without draft models."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)


@register_benchmark
class SpeculativeDecodingBenchmark(LLMBenchmark):
    """Benchmark speculative decoding vs. standard inference."""

    name = "speculative_decoding"
    version = "1.0.0"
    category = "performance"
    description = "Compare inference with and without speculative decoding"

    def required_config(self) -> list[str]:
        return ["model_path"]

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)
        iterations = config.get("iterations", 5)
        speculative_model = config.get("speculative_model")
        num_speculative_tokens = config.get("num_speculative_tokens", 5)
        prompt = config.get(
            "prompt",
            "Write a detailed explanation of how neural networks learn from data.",
        )

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []

        # Run baseline (no speculative decoding)
        logger.info("Running baseline (no speculative decoding)...")
        baseline_results = self._run_iterations(
            engine, prompt, max_tokens, temperature, iterations
        )
        if baseline_results["errors"]:
            errors.extend(baseline_results["errors"])

        outputs.append(
            {
                "mode": "baseline",
                **baseline_results["stats"],
            }
        )

        # Run with speculative decoding (if configured)
        spec_results = None
        if speculative_model:
            logger.info(
                f"Running with speculative decoding "
                f"(draft={speculative_model}, tokens={num_speculative_tokens})..."
            )
            try:
                engine.cleanup()
                spec_config = {
                    **config,
                    "speculative_model": speculative_model,
                    "num_speculative_tokens": num_speculative_tokens,
                }
                engine.initialize(config["model_path"], spec_config)

                spec_results = self._run_iterations(
                    engine, prompt, max_tokens, temperature, iterations
                )
                if spec_results["errors"]:
                    errors.extend(spec_results["errors"])

                outputs.append(
                    {
                        "mode": "speculative",
                        "draft_model": speculative_model,
                        "num_speculative_tokens": num_speculative_tokens,
                        **spec_results["stats"],
                    }
                )
            except Exception as e:
                errors.append(f"Speculative decoding failed: {e}")
        else:
            logger.warning(
                "No speculative_model configured — "
                "only baseline results will be reported"
            )

        metrics = self._compute_metrics(baseline_results, spec_results)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _run_iterations(
        self,
        engine,
        prompt: str,
        max_tokens: int,
        temperature: float,
        iterations: int,
    ) -> dict[str, Any]:
        """Run multiple iterations and collect stats."""
        tps_values: list[float] = []
        latencies: list[float] = []
        gen_outputs: list[str] = []
        errors: list[str] = []

        for i in range(iterations):
            try:
                result = engine.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                tps_values.append(result.metrics.tps)
                latencies.append(result.metrics.total_latency_ms)
                gen_outputs.append(result.output[:200])
            except Exception as e:
                errors.append(f"Iteration {i}: {e}")

        stats = {}
        if tps_values:
            stats = {
                "avg_tps": round(sum(tps_values) / len(tps_values), 2),
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
                "min_tps": round(min(tps_values), 2),
                "max_tps": round(max(tps_values), 2),
                "iterations": len(tps_values),
            }

        return {"stats": stats, "errors": errors, "outputs": gen_outputs}

    def _compute_metrics(
        self,
        baseline: dict[str, Any],
        speculative: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Compute comparison metrics."""
        metrics: dict[str, Any] = {}

        baseline_stats = baseline.get("stats", {})
        metrics["baseline_avg_tps"] = baseline_stats.get("avg_tps", 0)
        metrics["baseline_avg_latency_ms"] = baseline_stats.get("avg_latency_ms", 0)

        if speculative:
            spec_stats = speculative.get("stats", {})
            metrics["speculative_avg_tps"] = spec_stats.get("avg_tps", 0)
            metrics["speculative_avg_latency_ms"] = spec_stats.get("avg_latency_ms", 0)

            base_tps = baseline_stats.get("avg_tps", 0)
            spec_tps = spec_stats.get("avg_tps", 0)
            if base_tps > 0:
                metrics["speedup_ratio"] = round(spec_tps / base_tps, 3)
            else:
                metrics["speedup_ratio"] = 0

            # Compare outputs for quality
            base_outputs = baseline.get("outputs", [])
            spec_outputs = speculative.get("outputs", [])
            if base_outputs and spec_outputs:
                matches = sum(
                    1
                    for a, b in zip(base_outputs, spec_outputs, strict=False)
                    if a == b
                )
                metrics["output_match_rate"] = round(
                    matches / min(len(base_outputs), len(spec_outputs)), 3
                )

        return metrics
