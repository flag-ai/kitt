"""Tests for Devon integration bridge."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestDevonBridgeImportError:
    def test_raises_when_devon_not_installed(self):
        """Should raise ImportError when Devon is not available."""
        with patch("kitt.campaign.devon_bridge.DEVON_AVAILABLE", False):
            from kitt.campaign.devon_bridge import DevonBridge

            with pytest.raises(ImportError, match="Devon is not installed"):
                DevonBridge()


class TestIsDevonAvailable:
    def test_returns_bool(self):
        from kitt.campaign.devon_bridge import is_devon_available

        assert isinstance(is_devon_available(), bool)


@pytest.fixture
def mock_devon():
    """Mock Devon's storage and source classes."""
    mock_storage = MagicMock()
    mock_storage.root = Path("/mock/models")
    mock_source = MagicMock()

    with (
        patch("kitt.campaign.devon_bridge.DEVON_AVAILABLE", True),
        patch(
            "kitt.campaign.devon_bridge.ModelStorage",
            return_value=mock_storage,
            create=True,
        ),
        patch(
            "kitt.campaign.devon_bridge.HuggingFaceSource",
            return_value=mock_source,
            create=True,
        ),
    ):
        from kitt.campaign.devon_bridge import DevonBridge

        bridge = DevonBridge.__new__(DevonBridge)
        bridge._storage = mock_storage
        bridge._hf_source = mock_source
        yield bridge, mock_storage, mock_source


class TestDevonBridgeDownload:
    def test_download_basic(self, mock_devon):
        bridge, storage, source = mock_devon
        source.download_model.return_value = Path("/mock/models/meta-llama/Llama-8B")

        result = bridge.download("meta-llama/Llama-8B")
        assert result == Path("/mock/models/meta-llama/Llama-8B")
        source.download_model.assert_called_once()

    def test_download_with_patterns(self, mock_devon):
        bridge, storage, source = mock_devon
        source.download_model.return_value = Path("/mock/models/test/repo")

        bridge.download("test/repo", allow_patterns=["*.gguf"])
        call_kwargs = source.download_model.call_args
        assert call_kwargs[1].get("allow_patterns") == ["*.gguf"]

    def test_download_failure(self, mock_devon):
        bridge, storage, source = mock_devon
        source.download_model.side_effect = Exception("Network error")

        with pytest.raises(RuntimeError, match="Devon download failed"):
            bridge.download("test/repo")


class TestDevonBridgeRemove:
    def test_remove_success(self, mock_devon):
        bridge, storage, _ = mock_devon
        assert bridge.remove("test/repo") is True
        storage.remove.assert_called_once_with("test/repo")

    def test_remove_failure(self, mock_devon):
        bridge, storage, _ = mock_devon
        storage.remove.side_effect = Exception("Not found")
        assert bridge.remove("test/repo") is False


class TestDevonBridgeFindPath:
    def test_find_existing(self, mock_devon):
        bridge, storage, _ = mock_devon
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        storage.get_path.return_value = mock_path

        assert bridge.find_path("test/repo") == mock_path

    def test_find_missing(self, mock_devon):
        bridge, storage, _ = mock_devon
        storage.get_path.return_value = None

        assert bridge.find_path("test/repo") is None


class TestDevonBridgeListModels:
    def test_list_models(self, mock_devon):
        bridge, storage, _ = mock_devon
        storage.list_models.return_value = ["model/a", "model/b"]

        result = bridge.list_models()
        assert result == ["model/a", "model/b"]

    def test_list_models_failure(self, mock_devon):
        bridge, storage, _ = mock_devon
        storage.list_models.side_effect = Exception("Error")

        assert bridge.list_models() == []


class TestDevonBridgeDiskUsage:
    def test_disk_usage(self, mock_devon, tmp_path):
        bridge, storage, _ = mock_devon

        # Create a real file to measure
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        f = model_dir / "weights.bin"
        f.write_bytes(b"x" * 1024)

        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.rglob.return_value = [f]
        storage.get_path.return_value = mock_path

        usage = bridge.disk_usage_gb("test/repo")
        assert usage > 0

    def test_disk_usage_not_found(self, mock_devon):
        bridge, storage, _ = mock_devon
        storage.get_path.return_value = None

        assert bridge.disk_usage_gb("test/repo") == 0.0
