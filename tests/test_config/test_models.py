"""Tests for KITT configuration models."""

import pytest
from pydantic import ValidationError

from kitt.config.models import (
    DatasetConfig,
    EngineConfig,
    SamplingParams,
    SuiteConfig,
    TestConfig,
    WarmupConfig,
)


class TestWarmupConfig:
    def test_defaults(self):
        config = WarmupConfig()
        assert config.enabled is True
        assert config.iterations == 5
        assert config.log_warmup_times is True

    def test_custom_values(self):
        config = WarmupConfig(enabled=False, iterations=10)
        assert config.enabled is False
        assert config.iterations == 10

    def test_negative_iterations_rejected(self):
        with pytest.raises(ValidationError):
            WarmupConfig(iterations=-1)


class TestSamplingParams:
    def test_defaults(self):
        params = SamplingParams()
        assert params.temperature == 0.0
        assert params.top_p == 1.0
        assert params.top_k == 50
        assert params.max_tokens == 2048

    def test_temperature_bounds(self):
        SamplingParams(temperature=0.0)
        SamplingParams(temperature=2.0)
        with pytest.raises(ValidationError):
            SamplingParams(temperature=-0.1)
        with pytest.raises(ValidationError):
            SamplingParams(temperature=2.1)

    def test_max_tokens_positive(self):
        with pytest.raises(ValidationError):
            SamplingParams(max_tokens=0)


class TestDatasetConfig:
    def test_huggingface_source(self):
        config = DatasetConfig(source="cais/mmlu", split="test")
        assert config.source == "cais/mmlu"
        assert config.local_path is None

    def test_local_path(self):
        config = DatasetConfig(local_path="/data/mmlu")
        assert config.source is None
        assert config.local_path == "/data/mmlu"


class TestTestConfig:
    def test_minimal(self):
        config = TestConfig(name="throughput", category="performance")
        assert config.name == "throughput"
        assert config.version == "1.0.0"
        assert config.warmup.enabled is True
        assert config.runs == 3

    def test_full_config(self):
        config = TestConfig(
            name="mmlu",
            version="1.0.0",
            category="quality_standard",
            description="MMLU benchmark",
            warmup=WarmupConfig(enabled=True, iterations=3),
            sampling=SamplingParams(temperature=0.0, max_tokens=10),
            runs=1,
        )
        assert config.warmup.iterations == 3
        assert config.sampling.max_tokens == 10


class TestEngineConfig:
    def test_basic(self):
        config = EngineConfig(name="vllm", model_path="/models/llama")
        assert config.name == "vllm"
        assert config.parameters == {}

    def test_with_parameters(self):
        config = EngineConfig(
            name="vllm",
            parameters={"tensor_parallel_size": 1, "gpu_memory_utilization": 0.9},
        )
        assert config.parameters["tensor_parallel_size"] == 1


class TestSuiteConfig:
    def test_basic(self):
        config = SuiteConfig(
            suite_name="standard_benchmarks",
            tests=["mmlu", "gsm8k", "throughput"],
        )
        assert len(config.tests) == 3
        assert config.version == "1.0.0"
