"""Tests for ResultSync — mock SSHConnection, use tmp_path for local dirs."""

import json
from unittest.mock import MagicMock, patch

from kitt.remote.host_config import HostConfig
from kitt.remote.result_sync import ResultSync


def _make_host_config(**kwargs):
    """Create a HostConfig with sensible defaults."""
    defaults = dict(
        name="dgx01",
        hostname="gpu-server",
        user="kitt",
        port=22,
        storage_path="~/kitt-results",
    )
    defaults.update(kwargs)
    return HostConfig(**defaults)


class TestListRemoteResults:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_paths(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="~/kitt-results/llama/vllm/20240101\n~/kitt-results/llama/tgi/20240102\n",
            stderr="",
        )
        config = _make_host_config()
        sync = ResultSync(config)
        results = sync.list_remote_results()
        assert len(results) == 2
        assert "~/kitt-results/llama/vllm/20240101" in results
        assert "~/kitt-results/llama/tgi/20240102" in results

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_empty_on_error(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="No such file"
        )
        config = _make_host_config()
        sync = ResultSync(config)
        results = sync.list_remote_results()
        assert results == []

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_returns_empty_on_no_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        config = _make_host_config()
        sync = ResultSync(config)
        results = sync.list_remote_results()
        assert results == []


class TestListLocalResults:
    def test_with_existing_results(self, tmp_path):
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)
        # Create local result structure
        result_dir = tmp_path / "llama" / "vllm" / "20240101"
        result_dir.mkdir(parents=True)
        (result_dir / "metrics.json").write_text("{}")
        results = sync.list_local_results()
        assert len(results) == 1
        assert "llama/vllm/20240101" in results[0]

    def test_empty_dir(self, tmp_path):
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)
        results = sync.list_local_results()
        assert results == []

    def test_nonexistent_dir(self, tmp_path):
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path / "nonexistent")
        results = sync.list_local_results()
        assert results == []


class TestSync:
    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_downloads_new_results(self, mock_run, tmp_path):
        # First call: find remote results (run_command via ssh)
        # Second call: download_directory via scp
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout="~/kitt-results/llama/vllm/20240101\n",
                stderr="",
            ),
            MagicMock(returncode=0, stdout="", stderr=""),  # scp download
        ]
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)
        count = sync.sync(incremental=True)
        assert count == 1

    @patch("kitt.remote.ssh_connection.subprocess.run")
    def test_skips_existing_in_incremental_mode(self, mock_run, tmp_path):
        # Create a local result that matches the remote path
        result_dir = tmp_path / "llama" / "vllm" / "20240101"
        result_dir.mkdir(parents=True)
        (result_dir / "metrics.json").write_text("{}")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="~/kitt-results/llama/vllm/20240101\n",
            stderr="",
        )
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)
        count = sync.sync(incremental=True)
        assert count == 0


class TestImportToStore:
    def test_imports_all_metrics_files(self, tmp_path):
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)

        # Create two result dirs with metrics.json
        for name in ["run1", "run2"]:
            d = tmp_path / name
            d.mkdir()
            (d / "metrics.json").write_text(
                json.dumps({"model": "llama", "engine": "vllm", "run": name})
            )

        mock_store = MagicMock()
        count = sync.import_to_store(mock_store)
        assert count == 2
        assert mock_store.save_result.call_count == 2

    def test_handles_errors_gracefully(self, tmp_path):
        config = _make_host_config()
        sync = ResultSync(config, local_results_dir=tmp_path)

        # Create a corrupt metrics file
        d = tmp_path / "bad_run"
        d.mkdir()
        (d / "metrics.json").write_text("not valid json")

        mock_store = MagicMock()
        count = sync.import_to_store(mock_store)
        assert count == 0
        mock_store.save_result.assert_not_called()
