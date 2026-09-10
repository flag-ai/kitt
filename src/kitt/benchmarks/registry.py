"""Benchmark discovery and registration."""

import logging

from .base import LLMBenchmark

logger = logging.getLogger(__name__)


class BenchmarkRegistry:
    """Registry for discovering and managing benchmarks."""

    _benchmarks: dict[str, type[LLMBenchmark]] = {}

    @classmethod
    def register(cls, benchmark_class: type[LLMBenchmark]) -> None:
        """Register a benchmark class."""
        cls._benchmarks[benchmark_class.name] = benchmark_class

    @classmethod
    def get_benchmark(cls, name: str) -> type[LLMBenchmark]:
        """Get benchmark class by name.

        Raises:
            ValueError: If benchmark is not registered.
        """
        if name not in cls._benchmarks:
            available = ", ".join(cls._benchmarks.keys()) or "none"
            raise ValueError(f"Benchmark '{name}' not found. Available: {available}")
        return cls._benchmarks[name]

    @classmethod
    def list_all(cls) -> list[str]:
        """List all registered benchmark names."""
        return list(cls._benchmarks.keys())

    @classmethod
    def list_by_category(cls, category: str) -> list[str]:
        """List benchmarks filtered by category."""
        return [
            name
            for name, bench_cls in cls._benchmarks.items()
            if bench_cls.category == category
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered benchmarks (for testing)."""
        cls._benchmarks.clear()

    @classmethod
    def auto_discover(cls) -> None:
        """Import built-in benchmark modules to trigger registration."""
        from .performance import (
            batch_inference,  # noqa: F401
            latency,  # noqa: F401
            long_context,  # noqa: F401
            memory,  # noqa: F401
            speculative,  # noqa: F401
            streaming_latency,  # noqa: F401
            tensor_parallel,  # noqa: F401
            throughput,  # noqa: F401
            warmup_analysis,  # noqa: F401
        )
        from .quality.standard import (
            coding,  # noqa: F401
            function_calling,  # noqa: F401
            gsm8k,  # noqa: F401
            hellaswag,  # noqa: F401
            mmlu,  # noqa: F401
            multiturn,  # noqa: F401
            prompt_robustness,  # noqa: F401
            rag_pipeline,  # noqa: F401
            truthfulqa,  # noqa: F401
            vlm_benchmark,  # noqa: F401
        )

        # External plugins via entry points
        try:
            from kitt.plugins.discovery import discover_external_benchmarks

            for bench_cls in discover_external_benchmarks():
                cls.register(bench_cls)
        except Exception:
            pass


def register_benchmark(benchmark_class: type[LLMBenchmark]) -> type[LLMBenchmark]:
    """Decorator to auto-register benchmark classes."""
    BenchmarkRegistry.register(benchmark_class)
    return benchmark_class
