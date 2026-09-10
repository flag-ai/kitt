"""Tests for dynamic campaign builder."""

from unittest.mock import MagicMock

import pytest

from kitt.campaign.dynamic_campaign import DynamicCampaignBuilder
from kitt.campaign.models import CampaignConfig


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def builder(mock_store):
    return DynamicCampaignBuilder(mock_store)


class TestDynamicCampaignBuilder:
    def test_build_from_query_empty_results(self, builder, mock_store):
        mock_store.query.return_value = []
        config = builder.build_from_query(filters={"engine": "vllm"})
        assert isinstance(config, CampaignConfig)
        assert config.models == []
        assert config.engines == []

    def test_build_from_query_extracts_models_and_engines(self, builder, mock_store):
        mock_store.query.return_value = [
            {"model": "Llama-8B", "engine": "vllm"},
            {"model": "Qwen-7B", "engine": "llama_cpp"},
        ]
        config = builder.build_from_query(filters={"passed": True})
        assert len(config.models) == 2
        assert len(config.engines) == 2
        model_names = {m.name for m in config.models}
        assert model_names == {"Llama-8B", "Qwen-7B"}
        engine_names = {e.name for e in config.engines}
        assert engine_names == {"vllm", "llama_cpp"}

    def test_build_from_query_deduplicates(self, builder, mock_store):
        mock_store.query.return_value = [
            {"model": "Llama-8B", "engine": "vllm"},
            {"model": "Llama-8B", "engine": "vllm"},
        ]
        config = builder.build_from_query(filters={})
        assert len(config.models) == 1
        assert len(config.engines) == 1

    def test_build_from_query_custom_name(self, builder, mock_store):
        mock_store.query.return_value = [
            {"model": "TestModel", "engine": "tgi"},
        ]
        config = builder.build_from_query(filters={}, campaign_name="my-campaign")
        assert config.campaign_name == "my-campaign"

    def test_build_from_query_auto_name(self, builder, mock_store):
        mock_store.query.return_value = [
            {"model": "M1", "engine": "e1"},
            {"model": "M2", "engine": "e2"},
        ]
        config = builder.build_from_query(filters={})
        assert config.campaign_name == "dynamic-2m-2e"

    def test_build_from_query_suite_propagated(self, builder, mock_store):
        mock_store.query.return_value = [
            {"model": "M1", "engine": "vllm"},
        ]
        config = builder.build_from_query(filters={}, suite="performance")
        assert config.engines[0].suite == "performance"

    def test_build_from_matching_rules(self, builder, mock_store):
        mock_store.query.side_effect = [
            [{"model": "Llama-8B", "engine": "vllm"}],
            [{"model": "Qwen-7B", "engine": "tgi"}],
        ]
        config = builder.build_from_matching_rules(
            rules=["engine=vllm", "engine=tgi"],
            campaign_name="rules-test",
        )
        assert isinstance(config, CampaignConfig)
        assert config.campaign_name == "rules-test"
        assert len(config.models) == 2
        assert len(config.engines) == 2

    def test_build_from_matching_rules_deduplicates_across_rules(
        self, builder, mock_store
    ):
        mock_store.query.side_effect = [
            [{"model": "Llama-8B", "engine": "vllm"}],
            [{"model": "Llama-8B", "engine": "vllm"}],
        ]
        config = builder.build_from_matching_rules(
            rules=["engine=vllm", "model=Llama-8B"],
        )
        assert len(config.models) == 1
        assert len(config.engines) == 1

    def test_build_from_matching_rules_auto_name(self, builder, mock_store):
        mock_store.query.side_effect = [
            [],
            [],
            [],
        ]
        config = builder.build_from_matching_rules(
            rules=["engine=vllm", "engine=tgi", "engine=ollama"],
        )
        assert config.campaign_name == "rules-3"

    def test_build_from_matching_rules_empty_rules(self, builder, mock_store):
        config = builder.build_from_matching_rules(rules=[])
        assert isinstance(config, CampaignConfig)
        assert config.models == []
        assert config.engines == []
