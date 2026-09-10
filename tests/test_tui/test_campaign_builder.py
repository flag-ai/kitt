"""Tests for TUI campaign builder."""

from unittest.mock import patch

import yaml

from kitt.tui.campaign_builder import CampaignBuilderApp


class TestCampaignBuilderInit:
    def test_init_creates_default_config(self):
        app = CampaignBuilderApp()
        assert "campaign_name" in app.config
        assert "description" in app.config
        assert "models" in app.config
        assert "engines" in app.config
        assert "disk" in app.config

    def test_default_config_has_empty_models(self):
        app = CampaignBuilderApp()
        assert app.config["models"] == []

    def test_default_config_has_empty_engines(self):
        app = CampaignBuilderApp()
        assert app.config["engines"] == []

    def test_default_disk_reserve(self):
        app = CampaignBuilderApp()
        assert app.config["disk"]["reserve_gb"] == 50.0
        assert app.config["disk"]["cleanup_after_run"] is True


class TestRunSimple:
    def test_sets_campaign_name_from_prompt(self):
        app = CampaignBuilderApp()

        with patch("click.prompt") as mock_prompt, patch("click.echo"):
            mock_prompt.side_effect = [
                "test-campaign",  # campaign_name
                "A test campaign",  # description
                "",  # end models
                "",  # end engines
                50.0,  # disk reserve
            ]
            result = app.run_simple()

        assert result["campaign_name"] == "test-campaign"
        assert result["description"] == "A test campaign"

    def test_adds_model_entries(self):
        app = CampaignBuilderApp()

        with patch("click.prompt") as mock_prompt, patch("click.echo"):
            mock_prompt.side_effect = [
                "my-campaign",  # campaign_name
                "",  # description
                "Qwen/Qwen2.5-7B-Instruct",  # model 1 name
                "7B",  # model 1 params
                "",  # end models
                "",  # end engines
                50.0,  # disk reserve
            ]
            result = app.run_simple()

        assert len(result["models"]) == 1
        assert result["models"][0]["name"] == "Qwen/Qwen2.5-7B-Instruct"
        assert result["models"][0]["params"] == "7B"

    def test_adds_engine_entries(self):
        app = CampaignBuilderApp()

        with patch("click.prompt") as mock_prompt, patch("click.echo"):
            mock_prompt.side_effect = [
                "my-campaign",  # campaign_name
                "",  # description
                "",  # end models
                "vllm",  # engine name
                "standard",  # suite
                "",  # end engines
                50.0,  # disk reserve
            ]
            result = app.run_simple()

        assert len(result["engines"]) == 1
        assert result["engines"][0]["name"] == "vllm"
        assert result["engines"][0]["suite"] == "standard"

    def test_sets_disk_reserve(self):
        app = CampaignBuilderApp()

        with patch("click.prompt") as mock_prompt, patch("click.echo"):
            mock_prompt.side_effect = [
                "my-campaign",  # campaign_name
                "",  # description
                "",  # end models
                "",  # end engines
                100.0,  # disk reserve
            ]
            result = app.run_simple()

        assert result["disk"]["reserve_gb"] == 100.0

    def test_config_structure_after_run(self):
        app = CampaignBuilderApp()

        with patch("click.prompt") as mock_prompt, patch("click.echo"):
            mock_prompt.side_effect = [
                "full-campaign",
                "Full test",
                "model-a",
                "13B",
                "",
                "vllm",
                "performance",
                "",
                75.0,
            ]
            result = app.run_simple()

        assert result["campaign_name"] == "full-campaign"
        assert result["description"] == "Full test"
        assert len(result["models"]) == 1
        assert len(result["engines"]) == 1
        assert result["disk"]["reserve_gb"] == 75.0


class TestToYaml:
    def test_returns_valid_yaml(self):
        app = CampaignBuilderApp()
        app.config["campaign_name"] = "test"
        result = app.to_yaml()
        parsed = yaml.safe_load(result)
        assert parsed["campaign_name"] == "test"

    def test_includes_all_config_keys(self):
        app = CampaignBuilderApp()
        result = app.to_yaml()
        parsed = yaml.safe_load(result)
        assert "campaign_name" in parsed
        assert "description" in parsed
        assert "models" in parsed
        assert "engines" in parsed
        assert "disk" in parsed


class TestSave:
    def test_writes_file(self, tmp_path):
        app = CampaignBuilderApp()
        app.config["campaign_name"] = "saved-campaign"
        path = tmp_path / "campaign.yaml"
        app.save(str(path))

        assert path.exists()
        content = yaml.safe_load(path.read_text())
        assert content["campaign_name"] == "saved-campaign"

    def test_creates_file_at_specified_path(self, tmp_path):
        app = CampaignBuilderApp()
        path = tmp_path / "subdir" / "campaign.yaml"
        path.parent.mkdir(parents=True)
        app.save(str(path))
        assert path.exists()


class TestRunTui:
    def test_falls_back_when_textual_not_available(self):
        app = CampaignBuilderApp()

        with (
            patch.dict("sys.modules", {"textual": None, "textual.app": None}),
            patch.object(app, "run_simple", return_value=app.config) as mock_simple,
        ):
            result = app.run_tui()

        mock_simple.assert_called_once()
        assert result == app.config
