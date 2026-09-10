"""Campaign run scheduling with disk-awareness and size-based skip rules."""

import logging
import re
import shutil
from pathlib import Path

from .models import CampaignConfig, CampaignRunSpec, DiskConfig, ResourceLimitsConfig
from .state_manager import CampaignState

logger = logging.getLogger(__name__)

# Approximate bytes-per-parameter for common quantization formats.
# Values include ~10% overhead for metadata, embeddings, etc.
_QUANT_BPP: dict[str, float] = {
    "f32": 4.4,
    "fp16": 2.2,
    "bf16": 2.2,
    "q8_0": 1.1,
    "q6_k": 0.85,
    "q5_k_m": 0.72,
    "q5_k_s": 0.72,
    "q5_k_l": 0.72,
    "q5_0": 0.72,
    "q5_1": 0.72,
    "q4_k_m": 0.63,
    "q4_k_s": 0.59,
    "q4_k_l": 0.63,
    "q4_0": 0.59,
    "q4_0_4_4": 0.59,
    "q4_0_4_8": 0.59,
    "q4_0_8_8": 0.59,
    "q4_1": 0.63,
    "q3_k_m": 0.50,
    "q3_k_s": 0.46,
    "q3_k_l": 0.53,
    "q2_k": 0.42,
    "iq4_xs": 0.57,
    "iq4_nl": 0.59,
    "iq3_m": 0.45,
    "iq3_s": 0.43,
    "iq3_xs": 0.42,
    "iq3_xxs": 0.40,
    "iq2_m": 0.34,
    "iq2_s": 0.33,
    "iq2_xs": 0.32,
    "iq2_xxs": 0.31,
    "iq1_m": 0.26,
    "iq1_s": 0.24,
}

_PARAMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[Bb]")


class CampaignScheduler:
    """Schedule campaign runs with disk space and resource awareness.

    Orders runs by estimated size and skips runs that would exceed
    the configured disk reserve or model size limit.
    """

    def __init__(
        self,
        disk_config: DiskConfig,
        resource_limits: ResourceLimitsConfig | None = None,
    ) -> None:
        self.disk_config = disk_config
        self.resource_limits = resource_limits or ResourceLimitsConfig()

    def plan_runs(self, config: CampaignConfig) -> list[CampaignRunSpec]:
        """Generate ordered list of runs from campaign config.

        Produces one CampaignRunSpec per (model, engine, quant) combination.
        For safetensors models, quant is "bf16". For GGUF/Ollama, quants
        are discovered dynamically at runtime — here we produce placeholders
        that the runner will expand.
        """
        runs: list[CampaignRunSpec] = []

        for model in config.models:
            for engine in config.engines:
                if engine.name == "vllm" and model.safetensors_repo:
                    runs.append(
                        CampaignRunSpec(
                            model_name=model.name,
                            engine_name=engine.name,
                            quant="bf16",
                            repo_id=model.safetensors_repo,
                            estimated_size_gb=model.estimated_size_gb,
                            suite=engine.suite,
                            engine_config=engine.config,
                        )
                    )
                elif engine.name in ("llama_cpp", "exllamav2") and model.gguf_repo:
                    # Placeholder — actual quants discovered at runtime
                    runs.append(
                        CampaignRunSpec(
                            model_name=model.name,
                            engine_name=engine.name,
                            quant="__discover_gguf__",
                            repo_id=model.gguf_repo,
                            estimated_size_gb=model.estimated_size_gb,
                            suite=engine.suite,
                            engine_config=engine.config,
                        )
                    )
                elif engine.name == "ollama" and model.ollama_tag:
                    # Placeholder — actual tags discovered at runtime
                    runs.append(
                        CampaignRunSpec(
                            model_name=model.name,
                            engine_name=engine.name,
                            quant="__discover_ollama__",
                            repo_id=model.ollama_tag,
                            estimated_size_gb=model.estimated_size_gb,
                            suite=engine.suite,
                            engine_config=engine.config,
                        )
                    )

        return runs

    def order_by_size(self, runs: list[CampaignRunSpec]) -> list[CampaignRunSpec]:
        """Order runs by estimated size (smallest first) to maximize throughput."""
        return sorted(runs, key=lambda r: r.estimated_size_gb)

    def filter_completed(
        self, runs: list[CampaignRunSpec], state: CampaignState
    ) -> list[CampaignRunSpec]:
        """Remove runs that are already completed (for resume)."""
        return [r for r in runs if r.key not in state.completed_keys]

    def check_disk_space(
        self, run: CampaignRunSpec, storage_path: str | None = None
    ) -> bool:
        """Check if there's enough disk space for a run."""
        path = storage_path or str(Path.home())
        try:
            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024**3)
        except OSError:
            logger.warning(f"Could not check disk space at {path}")
            return True

        required = self.disk_config.reserve_gb + run.estimated_size_gb
        if free_gb < required:
            logger.warning(
                f"Insufficient disk space for {run.key}: "
                f"{free_gb:.1f}GB free, need {required:.1f}GB "
                f"(reserve={self.disk_config.reserve_gb}GB + "
                f"model={run.estimated_size_gb}GB)"
            )
            return False
        return True

    def should_skip(self, run: CampaignRunSpec) -> bool:
        """Check if a run should be skipped based on disk or size constraints."""
        if not self.check_disk_space(run, self.disk_config.storage_path):
            return True
        return bool(self.should_skip_for_size(run))

    def should_skip_for_size(self, run: CampaignRunSpec) -> bool:
        """Check if a run exceeds the configured model size limit.

        Uses the run's estimated_size_gb if set, otherwise returns False.
        """
        if self.resource_limits.max_model_size_gb <= 0:
            return False

        if run.estimated_size_gb <= 0:
            return False

        if run.estimated_size_gb > self.resource_limits.max_model_size_gb:
            logger.warning(
                f"Skipping {run.key}: estimated size {run.estimated_size_gb:.1f}GB "
                f"exceeds limit of {self.resource_limits.max_model_size_gb:.1f}GB"
            )
            return True

        return False


def parse_params(params_str: str) -> float:
    """Parse parameter count string to billions.

    Examples:
        "8B" -> 8.0
        "70B" -> 70.0
        "1.5B" -> 1.5
        "14B" -> 14.0
        "" -> 0.0
    """
    if not params_str:
        return 0.0
    match = _PARAMS_RE.search(params_str)
    if match:
        return float(match.group(1))
    return 0.0


def estimate_quant_size_gb(params_b: float, quant: str) -> float:
    """Estimate loaded model size in GB from parameter count and quantization.

    Args:
        params_b: Parameter count in billions (e.g. 70.0 for 70B).
        quant: Quantization name (e.g. "Q4_K_M", "fp16", "bf16").

    Returns:
        Estimated size in GB. Returns 0.0 if estimation is not possible.
    """
    if params_b <= 0:
        return 0.0

    quant_lower = quant.lower().strip()

    # Direct lookup
    bpp = _QUANT_BPP.get(quant_lower)
    if bpp is not None:
        return round(params_b * bpp, 1)

    # Try prefix matching for variants (e.g. "q4_k_m" matches "q4_k_m")
    # Also handle Ollama tag suffixes like "70b-instruct-fp16"
    for suffix in ("fp16", "bf16", "f32", "f16"):
        if quant_lower.endswith(suffix):
            bpp = _QUANT_BPP.get(suffix)
            if bpp is not None:
                return round(params_b * bpp, 1)

    # Try extracting quant name from longer strings (e.g. Ollama tags)
    for known_quant, known_bpp in sorted(
        _QUANT_BPP.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if known_quant in quant_lower:
            return round(params_b * known_bpp, 1)

    return 0.0
