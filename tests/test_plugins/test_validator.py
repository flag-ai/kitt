"""Tests for plugin validator."""

from unittest.mock import MagicMock, patch

from kitt.plugins.validator import PluginValidator


class TestValidateManifest:
    def setup_method(self):
        self.validator = PluginValidator()

    def test_valid_manifest_returns_true(self):
        manifest = {
            "name": "kitt-test-plugin",
            "version": "1.0.0",
            "plugin_type": "engine",
            "entry_point": "my_plugin.engine:MyEngine",
        }
        valid, errors = self.validator.validate_manifest(manifest)
        assert valid is True
        assert errors == []

    def test_missing_fields_returns_errors(self):
        manifest = {"name": "test"}
        valid, errors = self.validator.validate_manifest(manifest)
        assert valid is False
        assert len(errors) == 3
        assert any("version" in e for e in errors)
        assert any("plugin_type" in e for e in errors)
        assert any("entry_point" in e for e in errors)

    def test_invalid_type_returns_error(self):
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "plugin_type": "invalid_type",
            "entry_point": "mod:cls",
        }
        valid, errors = self.validator.validate_manifest(manifest)
        assert valid is False
        assert any("Invalid plugin_type" in e for e in errors)

    def test_empty_manifest_returns_all_errors(self):
        valid, errors = self.validator.validate_manifest({})
        assert valid is False
        assert len(errors) == 4

    def test_valid_benchmark_type(self):
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "plugin_type": "benchmark",
            "entry_point": "mod:cls",
        }
        valid, errors = self.validator.validate_manifest(manifest)
        assert valid is True
        assert errors == []

    def test_valid_reporter_type(self):
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "plugin_type": "reporter",
            "entry_point": "mod:cls",
        }
        valid, errors = self.validator.validate_manifest(manifest)
        assert valid is True
        assert errors == []


class TestCheckDependencies:
    def setup_method(self):
        self.validator = PluginValidator()

    def test_returns_true_when_all_satisfied(self):
        mock_dist = MagicMock()
        mock_dist.requires = ["click>=7.0", "pydantic>=2.0"]

        with patch("importlib.metadata.distribution") as mock_distribution:
            # First call is for the package itself, subsequent calls for deps
            mock_distribution.return_value = mock_dist
            satisfied, missing = self.validator.check_dependencies("my-plugin")

        assert satisfied is True
        assert missing == []

    def test_returns_true_when_package_not_found(self):
        with patch(
            "importlib.metadata.distribution",
            side_effect=Exception("not found"),
        ):
            satisfied, missing = self.validator.check_dependencies("nonexistent")

        assert satisfied is True
        assert missing == []

    def test_returns_missing_deps(self):
        mock_dist = MagicMock()
        mock_dist.requires = ["nonexistent-pkg>=1.0"]

        def side_effect(name):
            if name == "my-plugin":
                return mock_dist
            raise Exception("not found")

        with patch("importlib.metadata.distribution", side_effect=side_effect):
            satisfied, missing = self.validator.check_dependencies("my-plugin")

        assert satisfied is False
        assert "nonexistent-pkg" in missing


class TestValidateEntryPoint:
    def setup_method(self):
        self.validator = PluginValidator()

    def test_valid_entry_point_returns_true(self):
        with patch("importlib.import_module") as mock_import:
            mock_mod = MagicMock()
            mock_mod.MyClass = type("MyClass", (), {})
            mock_import.return_value = mock_mod

            result = self.validator.validate_entry_point("my_plugin.engine:MyClass")

        assert result is True

    def test_invalid_entry_point_no_colon_returns_false(self):
        result = self.validator.validate_entry_point("my_plugin.engine")
        assert result is False

    def test_missing_attr_returns_false(self):
        with patch("importlib.import_module") as mock_import:
            mock_mod = MagicMock(spec=[])
            mock_import.return_value = mock_mod

            result = self.validator.validate_entry_point("my_plugin:NonExistent")

        assert result is False

    def test_import_error_returns_false(self):
        with patch("importlib.import_module", side_effect=ImportError("no module")):
            result = self.validator.validate_entry_point("nonexistent:Class")

        assert result is False
