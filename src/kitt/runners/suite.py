"""Test suite runner - execute multiple benchmarks."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kitt.benchmarks.base import BenchmarkResult, LLMBenchmark
from kitt.engines.base import InferenceEngine

from .single_test import SingleTestRunner

logger = logging.getLogger(__name__)


@dataclass
class SuiteResult:
    """Result from running an entire test suite."""

    suite_name: str
    results: list[BenchmarkResult] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    total_time_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        """Suite passes if all benchmarks pass."""
        return all(r.passed for r in self.results)

    @property
    def total_benchmarks(self) -> int:
        return len(self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)


class SuiteRunner:
    """Run a suite of benchmarks against an engine."""

    def __init__(self, engine: InferenceEngine) -> None:
        self.engine = engine

    def run(
        self,
        suite_name: str,
        benchmarks: list[LLMBenchmark],
        global_config: dict[str, Any],
        test_overrides: dict[str, dict[str, Any]] = None,
    ) -> SuiteResult:
        """Execute all benchmarks in the suite.

        Args:
            suite_name: Name of the test suite.
            benchmarks: List of benchmark instances to run.
            global_config: Configuration applied to all benchmarks.
            test_overrides: Per-benchmark config overrides.

        Returns:
            SuiteResult with all benchmark results.
        """
        import time

        test_overrides = test_overrides or {}
        suite_result = SuiteResult(suite_name=suite_name)
        start_time = time.perf_counter()

        for benchmark in benchmarks:
            # Merge global config with per-test overrides
            config = global_config.copy()
            if benchmark.name in test_overrides:
                config.update(test_overrides[benchmark.name])

            # Handle multiple runs
            runs = config.pop("runs", 1)

            for run_num in range(1, runs + 1):
                logger.info(f"[{benchmark.name}] Run {run_num}/{runs}")

                runner = SingleTestRunner(self.engine, benchmark)
                result = runner.run(config)
                result.run_number = run_num

                suite_result.results.append(result)

        suite_result.total_time_seconds = time.perf_counter() - start_time

        logger.info(
            f"Suite '{suite_name}' complete: "
            f"{suite_result.passed_count}/{suite_result.total_benchmarks} passed "
            f"in {suite_result.total_time_seconds:.1f}s"
        )

        return suite_result
