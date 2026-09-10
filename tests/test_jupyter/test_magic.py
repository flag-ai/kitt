"""Tests for Jupyter magic commands."""

from unittest.mock import MagicMock, patch

from kitt.jupyter.magic import KITTMagics


class TestKITTMagicsInit:
    def test_init_with_no_shell(self):
        magics = KITTMagics()
        assert magics.shell is None
        assert magics._store is None

    def test_init_with_shell(self):
        mock_shell = MagicMock()
        magics = KITTMagics(shell=mock_shell)
        assert magics.shell is mock_shell


class TestKittLineMagic:
    def test_help_returns_help_text(self):
        magics = KITTMagics()
        result = magics.kitt("help")
        assert "KITT Jupyter Magic Commands" in result
        assert "%kitt results" in result
        assert "%kitt status" in result
        assert "%kitt compare" in result
        assert "%kitt fingerprint" in result
        assert "%kitt help" in result

    def test_fingerprint_returns_fingerprint_string(self):
        magics = KITTMagics()

        with patch("kitt.hardware.fingerprint.HardwareFingerprint") as mock_fp:
            mock_fp.generate.return_value = "rtx4090-24gb_i9-13900k"
            result = magics.kitt("fingerprint")

        assert result == "rtx4090-24gb_i9-13900k"

    def test_unknown_command_returns_error(self):
        magics = KITTMagics()
        result = magics.kitt("nonexistent")
        assert "Unknown command: nonexistent" in result

    def test_empty_line_returns_help(self):
        magics = KITTMagics()
        result = magics.kitt("")
        assert "KITT Jupyter Magic Commands" in result

    def test_results_with_no_store_returns_message(self):
        magics = KITTMagics()
        magics._store = None

        with patch.object(magics, "_get_store", return_value=None):
            result = magics.kitt("results")

        assert "No storage backend available" in result

    def test_results_with_store_returns_formatted_results(self):
        magics = KITTMagics()
        mock_store = MagicMock()
        mock_store.query.return_value = [
            {
                "model": "Llama-3.1-8B",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2025-01-15T12:00:00Z",
            }
        ]
        magics._store = mock_store

        result = magics.kitt("results")
        assert "Found 1 result(s)" in result
        assert "Llama-3.1-8B" in result
        assert "vllm" in result
        assert "PASS" in result

    def test_results_with_empty_results(self):
        magics = KITTMagics()
        mock_store = MagicMock()
        mock_store.query.return_value = []
        magics._store = mock_store

        result = magics.kitt("results")
        assert "No results found" in result


class TestKittCellMagic:
    def test_run_with_yaml_parses_config(self):
        magics = KITTMagics()
        yaml_text = "campaign_name: test-campaign\nmodels:\n  - Llama-3.1\n"
        result = magics.kitt_cell("run", yaml_text)
        assert "Campaign config parsed" in result
        assert "test-campaign" in result

    def test_non_run_returns_usage_message(self):
        magics = KITTMagics()
        result = magics.kitt_cell("something", "body text")
        assert "Usage:" in result

    def test_run_with_invalid_yaml(self):
        magics = KITTMagics()
        result = magics.kitt_cell("run", "{{ invalid: yaml: :")
        assert "Error parsing YAML" in result


class TestHelp:
    def test_help_includes_all_commands(self):
        magics = KITTMagics()
        result = magics._help()
        assert "results" in result
        assert "status" in result
        assert "compare" in result
        assert "fingerprint" in result
        assert "help" in result
        assert "run" in result
