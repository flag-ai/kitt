"""Base class for all LLM benchmarks."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WarmupConfig:
    """Warmup phase configuration."""

    enabled: bool = True
    iterations: int = 5
    log_warmup_times: bool = True


@dataclass
class BenchmarkResult:
    """Result from a benchmark run."""

    test_name: str
    test_version: str
    passed: bool
    metrics: dict[str, Any]
    outputs: list[Any]
    errors: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    run_number: int = 1
    warmup_times: list[float] = field(default_factory=list)


class LLMBenchmark(ABC):
    """Base class for all LLM benchmarks."""

    # Override in subclasses
    name: str = ""
    version: str = "1.0.0"
    category: str = ""  # 'performance', 'quality_standard', 'quality_custom'
    description: str = ""

    def run(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Execute the benchmark with optional warmup phase.

        Args:
            engine: Initialized InferenceEngine instance.
            config: Benchmark configuration including warmup settings.

        Returns:
            BenchmarkResult containing metrics and outputs.
        """
        warmup_config = self._parse_warmup_config(config)
        warmup_times: list[float] = []

        # Warmup phase
        if warmup_config.enabled:
            warmup_times = self._warmup_phase(engine, config, warmup_config)

        # Actual benchmark execution
        result = self._execute(engine, config)
        result.warmup_times = warmup_times

        return result

    def _parse_warmup_config(self, config: dict[str, Any]) -> WarmupConfig:
        """Parse warmup configuration from benchmark config."""
        warmup = config.get("warmup", {})
        return WarmupConfig(
            enabled=warmup.get("enabled", True),
            iterations=warmup.get("iterations", 5),
            log_warmup_times=warmup.get("log_warmup_times", True),
        )

    def _warmup_phase(
        self,
        engine,
        config: dict[str, Any],
        warmup_config: WarmupConfig,
    ) -> list[float]:
        """Run warmup iterations to initialize CUDA kernels and memory.

        Returns:
            List of warmup iteration times in seconds.
        """
        logger.info(f"Running {warmup_config.iterations} warmup iterations...")

        warmup_times = []
        for i in range(warmup_config.iterations):
            start = time.perf_counter()
            try:
                engine.generate(
                    prompt="This is a warmup prompt to initialize GPU kernels.",
                    max_tokens=10,
                    temperature=0.0,
                )
            except Exception as e:
                logger.warning(f"Warmup iteration {i + 1} failed: {e}")
                continue

            elapsed = time.perf_counter() - start
            warmup_times.append(elapsed)
            logger.debug(f"Warmup iteration {i + 1}: {elapsed:.3f}s")

        if warmup_config.log_warmup_times and warmup_times:
            avg_time = sum(warmup_times) / len(warmup_times)
            logger.info(f"Warmup complete. Average time: {avg_time:.3f}s")

        return warmup_times

    @abstractmethod
    def _execute(self, engine, config: dict[str, Any]) -> BenchmarkResult:
        """Execute the actual benchmark (override in subclasses).

        This method should implement the core benchmark logic without warmup.
        """

    def required_config(self) -> list[str]:
        """List of required configuration keys.

        Override if benchmark needs specific config.
        """
        return []

    def validate_config(self, config: dict[str, Any]) -> bool:
        """Validate that required config is present."""
        required = self.required_config()
        return all(key in config for key in required)
