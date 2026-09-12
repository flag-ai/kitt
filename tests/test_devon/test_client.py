"""Tests for Remote Devon HTTP client."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kitt.devon.config import DevonConnectionConfig

httpx = pytest.importorskip("httpx", reason="httpx not installed (optional dep)")


class TestRemoteDevonClientInit:
    def test_requires_url(self):
        from kitt.devon.client import RemoteDevonClient

        config = DevonConnectionConfig()
        with pytest.raises(ValueError, match="Devon URL is required"):
            RemoteDevonClient(config)

    def test_init_with_url(self):
        from kitt.devon.client import RemoteDevonClient

        config = DevonConnectionConfig(url="http://localhost:8000")
        client = RemoteDevonClient(config)
        assert client._base_url == "http://localhost:8000"
        assert client._headers == {}

    def test_init_with_api_key(self):
        from kitt.devon.client import RemoteDevonClient

        config = DevonConnectionConfig(
            url="http://localhost:8000",
            api_key="test-token",
        )
        client = RemoteDevonClient(config)
        assert client._headers == {"Authorization": "Bearer test-token"}

    def test_strips_trailing_slash(self):
        from kitt.devon.client import RemoteDevonClient

        config = DevonConnectionConfig(url="http://localhost:8000/")
        client = RemoteDevonClient(config)
        assert client._base_url == "http://localhost:8000"

    def test_raises_without_httpx(self):
        with patch("kitt.devon.client.HTTPX_AVAILABLE", False):
            from kitt.devon.client import RemoteDevonClient

            config = DevonConnectionConfig(url="http://localhost:8000")
            with pytest.raises(ImportError, match="httpx is not installed"):
                RemoteDevonClient(config)


@pytest.fixture
def mock_client():
    """Create a RemoteDevonClient with a mocked httpx.Client."""
    from kitt.devon.client import RemoteDevonClient

    config = DevonConnectionConfig(
        url="http://devon:8000",
        api_key="test-key",
    )
    client = RemoteDevonClient(config)
    return client


@pytest.fixture
def mock_response():
    """Create a mock httpx response factory."""

    def _make(status_code=200, json_data=None, text=""):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.text = text
        resp.raise_for_status = MagicMock()
        if status_code >= 400:
            import httpx

            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=resp
            )
        return resp

    return _make


class TestHealth:
    def test_health_success(self, mock_client, mock_response):
        resp = mock_response(json_data={"status": "ok", "version": "1.0.0"})
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = mock_client.health()
            assert result == {"status": "ok", "version": "1.0.0"}
            mock_http.get.assert_called_once_with("/health")

    def test_is_healthy_true(self, mock_client, mock_response):
        resp = mock_response(json_data={"status": "ok"})
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            assert mock_client.is_healthy() is True

    def test_is_healthy_false_on_error(self, mock_client):
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.side_effect = Exception("connection refused")
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            assert mock_client.is_healthy() is False


class TestSearch:
    def test_search_basic(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "query": "llama",
                "source": "huggingface",
                "count": 1,
                "results": [
                    {
                        "source": "huggingface",
                        "model_id": "meta-llama/Llama-3.1-8B",
                        "model_name": "Llama-3.1-8B",
                    }
                ],
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            results = mock_client.search(query="llama", limit=5)
            assert len(results) == 1
            assert results[0]["model_id"] == "meta-llama/Llama-3.1-8B"

    def test_search_with_filters(self, mock_client, mock_response):
        resp = mock_response(json_data={"results": []})
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_client.search(
                query="qwen",
                provider="Qwen",
                params="7B",
                format="gguf",
                limit=10,
            )
            call_args = mock_http.get.call_args
            params = call_args[1]["params"]
            assert params["query"] == "qwen"
            assert params["provider"] == "Qwen"
            assert params["params"] == "7B"
            assert params["format"] == "gguf"


class TestListModels:
    def test_list_models(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "count": 2,
                "models": [
                    {"source": "huggingface", "model_id": "model/a", "path": "/data/a"},
                    {"source": "huggingface", "model_id": "model/b", "path": "/data/b"},
                ],
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            models = mock_client.list_models()
            assert len(models) == 2
            assert models[0]["model_id"] == "model/a"


class TestRemove:
    def test_remove_success(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "deleted": True,
                "model_id": "test/repo",
                "source": "huggingface",
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.delete.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            assert mock_client.remove("test/repo") is True

    def test_remove_not_found(self, mock_client, mock_response):
        resp = mock_response(status_code=404)
        resp.raise_for_status = MagicMock()  # Don't raise for 404
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.delete.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            assert mock_client.remove("missing/model") is False


class TestDownload:
    def test_download_success(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "model_id": "meta-llama/Llama-8B",
                "source": "huggingface",
                "path": "/data/models/huggingface/meta-llama/Llama-8B",
                "files": ["model.safetensors"],
                "size_bytes": 16000000000,
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.post.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            path = mock_client.download("meta-llama/Llama-8B")
            assert path == Path("/data/models/huggingface/meta-llama/Llama-8B")

    def test_download_with_patterns(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "model_id": "test/repo",
                "source": "huggingface",
                "path": "/data/models/test/repo",
                "files": ["model-Q4_K_M.gguf"],
                "size_bytes": 4000000000,
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.post.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_client.download("test/repo", allow_patterns=["*Q4_K_M*"])
            call_args = mock_http.post.call_args
            body = call_args[1]["json"]
            assert body["include_patterns"] == ["*Q4_K_M*"]

    def test_download_failure(self, mock_client, mock_response):
        resp = mock_response(status_code=500, json_data={"detail": "Download failed"})
        resp.raise_for_status = MagicMock()  # We check status manually
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.post.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(RuntimeError, match="Devon download failed"):
                mock_client.download("test/repo")


class TestStatus:
    def test_status(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "model_count": 5,
                "total_size_bytes": 50000000000,
                "storage_path": "/data/models",
                "sources": {"huggingface": {"count": 5, "size_bytes": 50000000000}},
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            status = mock_client.status()
            assert status["model_count"] == 5
            assert status["storage_path"] == "/data/models"


class TestDiskUsage:
    def test_disk_usage_from_model_info(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "local": {"size_bytes": 16 * 1024**3},
                "remote": None,
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            usage = mock_client.disk_usage_gb("test/repo")
            assert usage == pytest.approx(16.0)

    def test_disk_usage_not_found(self, mock_client, mock_response):
        resp = mock_response(status_code=404)
        resp.raise_for_status = MagicMock()
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            # model_info raises LookupError for 404, disk_usage_gb catches it
            assert mock_client.disk_usage_gb("missing/model") == 0.0


class TestFindPath:
    def test_find_path_found(self, mock_client, mock_response):
        resp = mock_response(
            json_data={
                "local": {"path": "/data/models/huggingface/test/repo"},
                "remote": None,
            }
        )
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            path = mock_client.find_path("test/repo")
            assert path == "/data/models/huggingface/test/repo"

    def test_find_path_not_found(self, mock_client, mock_response):
        resp = mock_response(status_code=404)
        resp.raise_for_status = MagicMock()
        with patch.object(mock_client, "_client") as mock_ctx:
            mock_http = MagicMock()
            mock_http.get.return_value = resp
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_http)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            assert mock_client.find_path("missing/model") is None
