"""Single benchmark test runner."""

import logging
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.engines.base import InferenceEngine

logger = logging.getLogger(__name__)


class SingleTestRunner:
    """Run a single benchmark against an engine."""

    def __init__(self, engine: InferenceEngine, benchmark: LLMBenchmark) -> None:
        self.engine = engine
        self.benchmark = benchmark

    def run(self, config: dict[str, Any]) -> BenchmarkResult:
        """Execute the benchmark.

        Args:
            config: Benchmark configuration.

        Returns:
            BenchmarkResult with metrics and outputs.
        """
        # Validate config
        if not self.benchmark.validate_config(config):
            missing = [k for k in self.benchmark.required_config() if k not in config]
            logger.error(f"Missing required config keys: {missing}")
            return BenchmarkResult(
                test_name=self.benchmark.name,
                test_version=self.benchmark.version,
                passed=False,
                metrics={},
                outputs=[],
                errors=[f"Missing required config: {missing}"],
            )

        logger.info(
            f"Running benchmark '{self.benchmark.name}' "
            f"v{self.benchmark.version} with engine"
        )

        result = self.benchmark.run(self.engine, config)

        if result.passed:
            logger.info(f"Benchmark '{self.benchmark.name}' completed successfully")
        else:
            logger.warning(
                f"Benchmark '{self.benchmark.name}' completed with "
                f"{len(result.errors)} error(s)"
            )

        return result
