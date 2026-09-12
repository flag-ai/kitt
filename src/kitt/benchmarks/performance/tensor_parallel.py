"""Tensor parallel benchmark — measure scaling across multiple GPUs."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.benchmarks.registry import register_benchmark

logger = logging.getLogger(__name__)

DEFAULT_TP_SIZES = [1, 2, 4]


@register_benchmark
class TensorParallelBenchmark(LLMBenchmark):
    """Benchmark tensor parallel scaling across GPU counts."""

    name = "tensor_parallel"
    version = "1.0.0"
    category = "performance"
    description = "Measure inference scaling with tensor parallelism"

    def required_config(self) -> list[str]:
        return ["model_path"]

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        tp_sizes = config.get("tp_sizes", DEFAULT_TP_SIZES)
        max_tokens = config.get("max_tokens", 256)
        temperature = config.get("temperature", 0.0)
        iterations = config.get("iterations", 5)
        prompt = config.get(
            "prompt",
            "Explain the theory of relativity in simple terms.",
        )

        # Detect available GPUs
        available_gpus = self._detect_gpu_count()

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        tp_results: dict[int, dict[str, float]] = {}

        for tp_size in tp_sizes:
            if tp_size > available_gpus:
                logger.warning(
                    f"Skipping TP={tp_size}: only {available_gpus} GPUs available"
                )
                outputs.append(
                    {
                        "tp_size": tp_size,
                        "skipped": True,
                        "reason": f"Requires {tp_size} GPUs, {available_gpus} available",
                    }
                )
                continue

            logger.info(f"Testing tensor_parallel_size={tp_size}")

            try:
                # Re-initialize engine with new TP size
                engine.cleanup()
                tp_config = {**config, "tensor_parallel_size": tp_size}
                engine.initialize(config["model_path"], tp_config)

                tps_values = []
                latencies = []

                for _i in range(iterations):
                    result = engine.generate(
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    tps_values.append(result.metrics.tps)
                    latencies.append(result.metrics.total_latency_ms)

                avg_tps = sum(tps_values) / len(tps_values)
                avg_latency = sum(latencies) / len(latencies)

                tp_data = {
                    "tp_size": tp_size,
                    "avg_tps": round(avg_tps, 2),
                    "avg_latency_ms": round(avg_latency, 2),
                    "min_tps": round(min(tps_values), 2),
                    "max_tps": round(max(tps_values), 2),
                    "iterations": iterations,
                    "skipped": False,
                }
                tp_results[tp_size] = tp_data
                outputs.append(tp_data)

            except Exception as e:
                error_msg = f"TP={tp_size} failed: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
                outputs.append(
                    {
                        "tp_size": tp_size,
                        "skipped": False,
                        "error": str(e),
                    }
                )

        metrics = self._compute_scaling(tp_results)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0 and len(tp_results) > 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _compute_scaling(
        self, tp_results: dict[int, dict[str, float]]
    ) -> dict[str, Any]:
        """Compute scaling efficiency metrics."""
        if not tp_results:
            return {}

        base_tps = tp_results.get(1, {}).get("avg_tps", 0)
        metrics: dict[str, Any] = {}

        for tp_size, data in tp_results.items():
            metrics[f"tps_tp{tp_size}"] = data["avg_tps"]
            metrics[f"latency_tp{tp_size}"] = data["avg_latency_ms"]

            if base_tps > 0 and tp_size > 1:
                speedup = data["avg_tps"] / base_tps
                ideal_speedup = tp_size
                efficiency = (speedup / ideal_speedup) * 100
                metrics[f"scaling_efficiency_tp{tp_size}"] = round(efficiency, 1)
                metrics[f"speedup_tp{tp_size}"] = round(speedup, 2)

        if base_tps > 0:
            best_tp = max(tp_results, key=lambda k: tp_results[k]["avg_tps"])
            metrics["best_tp_size"] = best_tp
            metrics["best_tps"] = tp_results[best_tp]["avg_tps"]
            overhead = (
                (
                    1
                    - (
                        tp_results.get(2, {}).get("avg_tps", base_tps * 2)
                        / (base_tps * 2)
                    )
                )
                * 100
                if 2 in tp_results
                else 0
            )
            metrics["communication_overhead_pct"] = round(max(0, overhead), 1)

        return metrics

    def _detect_gpu_count(self) -> int:
        """Detect number of available GPUs."""
        try:
            from kitt.hardware.detector import detect_gpu

            gpu_info = detect_gpu()
            if gpu_info:
                return gpu_info.count
        except Exception:
            pass
        return 1
