"""Tests for YAML benchmark loader."""

from pathlib import Path

import pytest

from kitt.benchmarks.loader import BenchmarkLoader, YAMLBenchmark


@pytest.fixture
def tmp_yaml(tmp_path):
    def _create(content: str, filename: str = "test_bench.yaml") -> Path:
        path = tmp_path / filename
        path.write_text(content)
        return path

    return _create


class TestYAMLBenchmark:
    def test_load_from_yaml(self, tmp_yaml):
        path = tmp_yaml("""
name: test_bench
category: performance
version: "1.0.0"
description: "A test benchmark"
""")
        benchmark = YAMLBenchmark(path)
        assert benchmark.name == "test_bench"
        assert benchmark.category == "performance"
        assert benchmark.version == "1.0.0"

    def test_missing_name_raises(self, tmp_yaml):
        path = tmp_yaml("category: performance")
        with pytest.raises(KeyError):
            YAMLBenchmark(path)


class TestBenchmarkLoader:
    def test_discover_yaml_benchmarks(self, tmp_path):
        (tmp_path / "bench1.yaml").write_text("name: bench1\ncategory: performance")
        (tmp_path / "bench2.yaml").write_text(
            "name: bench2\ncategory: quality_standard"
        )
        (tmp_path / "not_yaml.txt").write_text("ignore me")

        benchmarks = BenchmarkLoader.discover_benchmarks(tmp_path)
        assert len(benchmarks) == 2
        names = {b.name for b in benchmarks}
        assert "bench1" in names
        assert "bench2" in names

    def test_discover_skips_invalid(self, tmp_path):
        (tmp_path / "valid.yaml").write_text("name: valid\ncategory: performance")
        (tmp_path / "invalid.yaml").write_text("not: valid: yaml: [broken")

        benchmarks = BenchmarkLoader.discover_benchmarks(tmp_path)
        assert len(benchmarks) == 1
        assert benchmarks[0].name == "valid"
