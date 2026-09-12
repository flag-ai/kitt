"""Tests for KITT configuration loader."""

from pathlib import Path

import pytest

from kitt.config.loader import (
    ConfigError,
    load_engine_config,
    load_suite_config,
    load_test_config,
    load_yaml,
)


@pytest.fixture
def tmp_yaml(tmp_path):
    """Create a temporary YAML file."""

    def _create(content: str, filename: str = "test.yaml") -> Path:
        path = tmp_path / filename
        path.write_text(content)
        return path

    return _create


class TestLoadYaml:
    def test_valid_yaml(self, tmp_yaml):
        path = tmp_yaml("name: test\nversion: '1.0.0'")
        data = load_yaml(path)
        assert data["name"] == "test"

    def test_empty_yaml(self, tmp_yaml):
        path = tmp_yaml("")
        data = load_yaml(path)
        assert data == {}

    def test_file_not_found(self):
        with pytest.raises(ConfigError, match="not found"):
            load_yaml(Path("/nonexistent/file.yaml"))

    def test_invalid_yaml(self, tmp_yaml):
        path = tmp_yaml("invalid: [yaml: {broken")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_yaml(path)


class TestLoadTestConfig:
    def test_valid_test_config(self, tmp_yaml):
        content = """
name: throughput
category: performance
description: "Throughput benchmark"
warmup:
  enabled: true
  iterations: 5
sampling:
  temperature: 0.0
  max_tokens: 2048
runs: 3
"""
        path = tmp_yaml(content)
        config = load_test_config(path)
        assert config.name == "throughput"
        assert config.category == "performance"
        assert config.warmup.iterations == 5

    def test_missing_required_fields(self, tmp_yaml):
        content = "description: 'missing name and category'"
        path = tmp_yaml(content)
        with pytest.raises(ConfigError, match="validation failed"):
            load_test_config(path)


class TestLoadSuiteConfig:
    def test_valid_suite(self, tmp_yaml):
        content = """
suite_name: quick
version: "1.0.0"
tests:
  - throughput
  - latency
"""
        path = tmp_yaml(content)
        config = load_suite_config(path)
        assert config.suite_name == "quick"
        assert len(config.tests) == 2


class TestLoadEngineConfig:
    def test_valid_engine(self, tmp_yaml):
        content = """
name: vllm
model_path: /models/llama-7b
parameters:
  tensor_parallel_size: 1
  gpu_memory_utilization: 0.9
"""
        path = tmp_yaml(content)
        config = load_engine_config(path)
        assert config.name == "vllm"
        assert config.parameters["tensor_parallel_size"] == 1
