"""Hardware constraints for model recommendations."""

from pydantic import BaseModel, Field


class HardwareConstraints(BaseModel):
    """Hardware constraints for filtering model recommendations."""

    max_vram_gb: float | None = Field(None, description="Maximum GPU VRAM in GB")
    max_ram_gb: float | None = Field(None, description="Maximum system RAM in GB")
    min_throughput_tps: float | None = Field(
        None, description="Minimum throughput (tokens/sec)"
    )
    min_accuracy: float | None = Field(None, description="Minimum accuracy (0-1)")
    max_latency_ms: float | None = Field(
        None, description="Maximum latency in milliseconds"
    )
    engine: str | None = Field(None, description="Restrict to specific engine")

    def matches(self, result: dict) -> bool:
        """Check if a result satisfies these constraints.

        Args:
            result: Result dict with metrics.

        Returns:
            True if all constraints are satisfied.
        """
        metrics = result.get("metrics", {})

        if self.max_vram_gb is not None:
            vram = metrics.get("peak_vram_gb", 0)
            if vram > self.max_vram_gb:
                return False

        if self.min_throughput_tps is not None:
            tps = metrics.get("avg_tps", 0)
            if tps < self.min_throughput_tps:
                return False

        if self.min_accuracy is not None:
            accuracy = metrics.get("accuracy", 0)
            if accuracy < self.min_accuracy:
                return False

        if self.max_latency_ms is not None:
            latency = metrics.get("avg_latency_ms", float("inf"))
            if latency > self.max_latency_ms:
                return False

        return not (self.engine is not None and result.get("engine") != self.engine)
