"""YAML-defined benchmark loader with error recovery."""

import logging
from pathlib import Path
from typing import Any

import yaml

from kitt.runners.checkpoint import CheckpointManager

from .base import BenchmarkResult, LLMBenchmark
from .dataset_manager import DatasetManager

logger = logging.getLogger(__name__)


class YAMLBenchmark(LLMBenchmark):
    """Benchmark defined by YAML configuration with error recovery."""

    def __init__(self, config_path: Path) -> None:
        """Load benchmark from YAML file."""
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.name = self.config["name"]
        self.version = self.config.get("version", "1.0.0")
        self.category = self.config["category"]
        self.description = self.config.get("description", "")
        self._config_path = config_path

    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Execute YAML-defined benchmark with error recovery and checkpointing."""
        prompts = self._load_prompts()

        outputs: list[dict[str, Any]] = []
        errors: list[str] = []
        checkpoint_manager = CheckpointManager(self.name, config)

        # Resume from checkpoint if exists
        start_index = checkpoint_manager.get_last_completed_index()
        if start_index > 0:
            logger.info(f"Resuming from checkpoint at index {start_index}")
            outputs = checkpoint_manager.load_partial_outputs()

        # Process each prompt with error handling
        for i, prompt in enumerate(prompts[start_index:], start=start_index):
            try:
                result = engine.generate(
                    prompt=prompt,
                    **config.get("sampling", {}),
                )

                output_data = {
                    "prompt": prompt,
                    "output": result.output,
                    "metrics": {
                        "ttft_ms": result.metrics.ttft_ms,
                        "tps": result.metrics.tps,
                        "total_latency_ms": result.metrics.total_latency_ms,
                        "gpu_memory_peak_gb": result.metrics.gpu_memory_peak_gb,
                    },
                }
                outputs.append(output_data)

                # Checkpoint every 100 items
                if (i + 1) % 100 == 0:
                    checkpoint_manager.save_checkpoint(i, outputs)
                    logger.info(f"Checkpoint saved at {i + 1}/{len(prompts)}")

            except Exception as e:
                error_msg = f"Error on item {i}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                checkpoint_manager.save_checkpoint(i, outputs, error=error_msg)
                continue

        # Clear checkpoint on successful completion
        if not errors:
            checkpoint_manager.clear_checkpoint()

        metrics = self._calculate_metrics(outputs)

        return BenchmarkResult(
            test_name=self.name,
            test_version=self.version,
            passed=len(errors) == 0,
            metrics=metrics,
            outputs=outputs,
            errors=errors,
        )

    def _load_prompts(self) -> list[str]:
        """Load prompts from dataset configuration."""
        dataset_config = self.config.get("dataset", {})
        source = dataset_config.get("source")
        local_path = dataset_config.get("local_path")
        split = dataset_config.get("split", "test")
        sample_size = dataset_config.get("sample_size")

        if source:
            return DatasetManager.load_from_huggingface(
                source, split=split, sample_size=sample_size
            )
        elif local_path:
            return DatasetManager.load_from_directory(
                Path(local_path), sample_size=sample_size
            )

        # If no dataset, check for inline prompts
        prompts_config = self.config.get("prompts", {})
        if "items" in prompts_config:
            return prompts_config["items"]

        test_config = self.config.get("test_config", {})
        if "prompts" in test_config:
            return test_config["prompts"]

        return []

    def _calculate_metrics(self, outputs: list[dict]) -> dict[str, Any]:
        """Calculate benchmark metrics from outputs."""
        if not outputs:
            return {}

        latencies = [
            o["metrics"]["total_latency_ms"] for o in outputs if "metrics" in o
        ]
        tps_values = [o["metrics"]["tps"] for o in outputs if "metrics" in o]

        metrics: dict[str, Any] = {
            "total_samples": len(outputs),
        }

        if latencies:
            metrics["avg_latency_ms"] = sum(latencies) / len(latencies)
            metrics["min_latency_ms"] = min(latencies)
            metrics["max_latency_ms"] = max(latencies)

        if tps_values:
            metrics["avg_tps"] = sum(tps_values) / len(tps_values)

        return metrics


class BenchmarkLoader:
    """Load benchmarks from filesystem."""

    @staticmethod
    def discover_benchmarks(test_dir: Path) -> list[LLMBenchmark]:
        """Discover all benchmarks in directory.

        Args:
            test_dir: Directory to search for benchmark definitions.

        Returns:
            List of loaded benchmark instances.
        """
        benchmarks: list[LLMBenchmark] = []

        for yaml_file in test_dir.rglob("*.yaml"):
            try:
                benchmark = YAMLBenchmark(yaml_file)
                benchmarks.append(benchmark)
            except Exception as e:
                logger.error(f"Failed to load benchmark {yaml_file}: {e}")

        return benchmarks
