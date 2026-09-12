"""Tests for campaign query builder."""

import pytest

from kitt.campaign.query_builder import QueryBuilder


@pytest.fixture
def qb():
    return QueryBuilder()


class TestQueryBuilder:
    def test_empty_expression(self, qb):
        assert qb.parse("") == {}

    def test_whitespace_only(self, qb):
        assert qb.parse("   ") == {}

    def test_single_equality(self, qb):
        result = qb.parse("engine=vllm")
        assert result == {"engine": "vllm"}

    def test_single_equality_with_quotes(self, qb):
        result = qb.parse("engine='vllm'")
        assert result == {"engine": "vllm"}

    def test_multiple_and_conditions(self, qb):
        result = qb.parse("engine=vllm AND model=Llama-8B")
        assert result == {"engine": "vllm", "model": "Llama-8B"}

    def test_and_case_insensitive(self, qb):
        result = qb.parse("engine=vllm and model=Qwen")
        assert result == {"engine": "vllm", "model": "Qwen"}

    def test_like_operator(self, qb):
        result = qb.parse("model LIKE 'Qwen%'")
        # LIKE strips the % wildcard for simplified dict filters
        assert result == {"model": "Qwen"}

    def test_like_lowercase(self, qb):
        result = qb.parse("model like 'Llama%'")
        assert result == {"model": "Llama"}

    def test_boolean_coercion_true(self, qb):
        result = qb.parse("passed=true")
        assert result["passed"] is True

    def test_boolean_coercion_false(self, qb):
        result = qb.parse("passed=false")
        assert result["passed"] is False

    def test_integer_coercion(self, qb):
        result = qb.parse("run_count=5")
        assert result["run_count"] == 5
        assert isinstance(result["run_count"], int)

    def test_inequality_ignored(self, qb):
        result = qb.parse("engine!=tgi")
        # Inequality is not supported in simple filters; should be skipped
        assert result == {}

    def test_complex_expression(self, qb):
        result = qb.parse("engine=vllm AND model LIKE 'Qwen%' AND passed=true")
        assert result == {"engine": "vllm", "model": "Qwen", "passed": True}

    def test_unparseable_condition_skipped(self, qb):
        result = qb.parse("engine=vllm AND ??? AND model=Llama")
        # The unparseable middle part is skipped
        assert result == {"engine": "vllm", "model": "Llama"}
