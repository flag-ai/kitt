"""Tests for campaign Pydantic models."""

import yaml

from kitt.campaign.models import (
    CampaignConfig,
    CampaignEngineSpec,
    CampaignModelSpec,
    CampaignRunSpec,
    DiskConfig,
    NotificationConfig,
    QuantFilterConfig,
    ResourceLimitsConfig,
)


class TestCampaignModelSpec:
    def test_minimal(self):
        spec = CampaignModelSpec(name="test-model")
        assert spec.name == "test-model"
        assert spec.safetensors_repo is None
        assert spec.gguf_repo is None
        assert spec.ollama_tag is None
        assert spec.estimated_size_gb == 0.0

    def test_full(self):
        spec = CampaignModelSpec(
            name="Llama-3.1-8B",
            params="8B",
            safetensors_repo="meta-llama/Llama-3.1-8B",
            gguf_repo="bartowski/Llama-3.1-8B-GGUF",
            ollama_tag="llama3.1:8b",
            estimated_size_gb=16.0,
        )
        assert spec.params == "8B"
        assert spec.estimated_size_gb == 16.0


class TestCampaignEngineSpec:
    def test_defaults(self):
        spec = CampaignEngineSpec(name="llama_cpp")
        assert spec.suite == "standard"
        assert spec.config == {}
        assert spec.formats == []

    def test_with_config(self):
        spec = CampaignEngineSpec(
            name="vllm",
            config={"tensor_parallel_size": 2},
            suite="performance",
            formats=["safetensors"],
        )
        assert spec.config["tensor_parallel_size"] == 2


class TestDiskConfig:
    def test_defaults(self):
        cfg = DiskConfig()
        assert cfg.reserve_gb == 100.0
        assert cfg.cleanup_after_run is True

    def test_custom(self):
        cfg = DiskConfig(reserve_gb=50.0, storage_path="/data/models")
        assert cfg.reserve_gb == 50.0
        assert cfg.storage_path == "/data/models"


class TestNotificationConfig:
    def test_defaults(self):
        cfg = NotificationConfig()
        assert cfg.webhook_url is None
        assert cfg.desktop is False
        assert cfg.on_complete is True

    def test_webhook(self):
        cfg = NotificationConfig(webhook_url="https://hooks.example.com/notify")
        assert cfg.webhook_url == "https://hooks.example.com/notify"


class TestResourceLimitsConfig:
    def test_defaults(self):
        cfg = ResourceLimitsConfig()
        assert cfg.max_model_size_gb == 0.0

    def test_custom(self):
        cfg = ResourceLimitsConfig(max_model_size_gb=100.0)
        assert cfg.max_model_size_gb == 100.0

    def test_zero_means_no_limit(self):
        cfg = ResourceLimitsConfig(max_model_size_gb=0.0)
        assert cfg.max_model_size_gb == 0.0


class TestCampaignRunSpec:
    def test_key(self):
        run = CampaignRunSpec(
            model_name="Llama-8B",
            engine_name="llama_cpp",
            quant="Q4_K_M",
        )
        assert run.key == "Llama-8B|llama_cpp|Q4_K_M"

    def test_defaults(self):
        run = CampaignRunSpec(model_name="test", engine_name="vllm", quant="bf16")
        assert run.suite == "standard"
        assert run.engine_config == {}


class TestCampaignConfig:
    def test_minimal(self):
        cfg = CampaignConfig(campaign_name="test")
        assert cfg.campaign_name == "test"
        assert cfg.models == []
        assert cfg.engines == []
        assert cfg.parallel is False

    def test_full_config(self):
        cfg = CampaignConfig(
            campaign_name="dgx-spark-full",
            description="Full DGX Spark campaign",
            models=[
                CampaignModelSpec(name="Llama-8B", params="8B"),
            ],
            engines=[
                CampaignEngineSpec(name="llama_cpp"),
            ],
            disk=DiskConfig(reserve_gb=200.0),
            notifications=NotificationConfig(desktop=True),
            quant_filter=QuantFilterConfig(skip_patterns=["IQ1_*"]),
        )
        assert len(cfg.models) == 1
        assert cfg.disk.reserve_gb == 200.0

    def test_yaml_roundtrip(self, tmp_path):
        """Config can be serialized to YAML and loaded back."""
        cfg = CampaignConfig(
            campaign_name="roundtrip-test",
            description="Test YAML roundtrip",
            models=[
                CampaignModelSpec(
                    name="TestModel",
                    params="7B",
                    gguf_repo="test/repo",
                ),
            ],
            engines=[
                CampaignEngineSpec(name="ollama", suite="quick"),
            ],
        )

        yaml_path = tmp_path / "campaign.yaml"
        yaml_path.write_text(yaml.dump(cfg.model_dump(), default_flow_style=False))

        loaded_data = yaml.safe_load(yaml_path.read_text())
        loaded_cfg = CampaignConfig(**loaded_data)

        assert loaded_cfg.campaign_name == "roundtrip-test"
        assert loaded_cfg.models[0].name == "TestModel"
        assert loaded_cfg.engines[0].suite == "quick"

    def test_config_with_resource_limits(self):
        cfg = CampaignConfig(
            campaign_name="test-limits",
            resource_limits=ResourceLimitsConfig(max_model_size_gb=100.0),
        )
        assert cfg.resource_limits.max_model_size_gb == 100.0

    def test_config_default_resource_limits(self):
        cfg = CampaignConfig(campaign_name="test")
        assert cfg.resource_limits.max_model_size_gb == 0.0
