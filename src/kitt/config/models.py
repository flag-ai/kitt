"""Pydantic models for KITT configuration."""

from typing import Any

from pydantic import BaseModel, Field


class WarmupConfig(BaseModel):
    """Warmup phase configuration."""

    enabled: bool = True
    iterations: int = Field(default=5, ge=0)
    log_warmup_times: bool = True


class SamplingParams(BaseModel):
    """Universal sampling parameters for generation."""

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int = Field(default=50, ge=0)
    max_tokens: int = Field(default=2048, ge=1)


class DatasetConfig(BaseModel):
    """Dataset source configuration."""

    source: str | None = None  # HuggingFace dataset ID or None
    local_path: str | None = None  # Local directory path
    split: str = "test"
    sample_size: int | None = None  # None = use all samples


class PromptConfig(BaseModel):
    """Prompt template configuration."""

    template: str = ""
    few_shot: int = 0
    few_shot_source: str = "dev"


class EvaluationConfig(BaseModel):
    """Evaluation metrics configuration."""

    metrics: list[str] = Field(default_factory=list)
    answer_extraction: dict[str, str] = Field(default_factory=dict)


class PerformanceCollectionConfig(BaseModel):
    """Performance data collection configuration."""

    frequency: str = "start_end"  # 'continuous', 'start_end', or interval


class TestConfig(BaseModel):
    """Configuration for a single test/benchmark."""

    name: str
    version: str = "1.0.0"
    category: str  # 'performance', 'quality_standard', 'quality_custom'
    description: str = ""
    warmup: WarmupConfig = Field(default_factory=WarmupConfig)
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    prompts: PromptConfig = Field(default_factory=PromptConfig)
    sampling: SamplingParams = Field(default_factory=SamplingParams)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    runs: int = Field(default=3, ge=1)
    performance_collection: PerformanceCollectionConfig = Field(
        default_factory=PerformanceCollectionConfig
    )
    test_config: dict[str, Any] = Field(default_factory=dict)


class EngineConfig(BaseModel):
    """Configuration for an inference engine."""

    name: str
    model_path: str = ""
    mode: str = ""  # "docker" or "native"; empty = engine default
    profile_id: str = ""  # Optional engine profile ID
    parameters: dict[str, Any] = Field(default_factory=dict)


class SuiteOverrides(BaseModel):
    """Per-test overrides within a suite."""

    warmup: WarmupConfig | None = None
    sampling: SamplingParams | None = None
    runs: int | None = None


class SuiteConfig(BaseModel):
    """Configuration for a test suite."""

    suite_name: str
    version: str = "1.0.0"
    description: str = ""
    tests: list[str] = Field(default_factory=list)
    global_config: dict[str, Any] = Field(default_factory=dict)
    sampling_overrides: SamplingParams | None = None
    test_overrides: dict[str, SuiteOverrides] = Field(default_factory=dict)
