"""HTTP client for a remote Devon REST API instance.

This module provides RemoteDevonClient, which connects to a containerized
Devon instance over HTTP. It mirrors the DevonBridge interface so the two
can be used interchangeably by the campaign runner and web services.

Requires ``httpx``: ``pip install httpx`` (or ``pip install kitt[devon]``).
"""

import logging
from pathlib import Path
from typing import Any

from .config import DevonConnectionConfig

logger = logging.getLogger(__name__)

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class RemoteDevonClient:
    """HTTP client for a remote Devon REST API.

    Mirrors the DevonBridge interface: download, remove, find_path,
    list_models, disk_usage_gb. Also exposes search, status, and health
    for the web UI.
    """

    def __init__(self, config: DevonConnectionConfig) -> None:
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is not installed. Install with: pip install httpx  "
                "or: pip install kitt[devon]"
            )
        if not config.url:
            raise ValueError("Devon URL is required for remote connection")

        self._config = config
        self._base_url = config.url.rstrip("/")
        self._headers: dict[str, str] = {}
        if config.api_key:
            self._headers["Authorization"] = f"Bearer {config.api_key}"

    def _client(self, timeout: float | None = None) -> "httpx.Client":
        """Create an httpx client with configured defaults."""
        return httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout or self._config.timeout,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check Devon API health.

        Returns:
            Health response dict with 'status' and 'version' keys.

        Raises:
            ConnectionError: If the Devon instance is unreachable.
        """
        with self._client(timeout=5.0) as client:
            try:
                resp = client.get("/health")
                resp.raise_for_status()
                return resp.json()
            except httpx.ConnectError as e:
                raise ConnectionError(
                    f"Cannot reach Devon at {self._base_url}: {e}"
                ) from e

    def is_healthy(self) -> bool:
        """Check if the Devon instance is reachable."""
        try:
            result = self.health()
            return result.get("status") == "ok"
        except Exception as e:
            logger.debug(f"Devon health check failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str | None = None,
        source: str = "huggingface",
        provider: str | None = None,
        params: str | None = None,
        size: str | None = None,
        format: str | None = None,
        task: str | None = None,
        license: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for models on remote sources.

        Args:
            query: Search query string.
            source: Model source (default: "huggingface").
            provider: Filter by model author/provider.
            params: Filter by parameter count.
            size: Filter by model size.
            format: Filter by model format.
            task: Filter by task type.
            license: Filter by license.
            limit: Maximum results to return.

        Returns:
            List of model result dicts.
        """
        request_params: dict[str, Any] = {"source": source, "limit": limit}
        if query:
            request_params["query"] = query
        if provider:
            request_params["provider"] = provider
        if params:
            request_params["params"] = params
        if size:
            request_params["size"] = size
        if format:
            request_params["format"] = format
        if task:
            request_params["task"] = task
        if license:
            request_params["license"] = license

        with self._client() as client:
            resp = client.get("/api/v1/search", params=request_params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])

    # ------------------------------------------------------------------
    # Models (list, info, delete)
    # ------------------------------------------------------------------

    def list_models(self, source: str | None = None) -> list[dict[str, Any]]:
        """List locally downloaded models on the Devon instance.

        Args:
            source: Optional source filter.

        Returns:
            List of local model dicts with keys: source, model_id, path,
            size_bytes, downloaded_at, files, metadata.
        """
        request_params: dict[str, str] = {}
        if source:
            request_params["source"] = source

        with self._client() as client:
            resp = client.get("/api/v1/models", params=request_params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])

    def model_info(self, source: str, model_id: str) -> dict[str, Any]:
        """Get info for a specific model (local + remote metadata).

        Args:
            source: Model source (e.g. "huggingface").
            model_id: Model identifier (e.g. "Qwen/Qwen2.5-32B").

        Returns:
            Dict with 'local' and/or 'remote' keys.

        Raises:
            LookupError: If the model is not found locally or remotely.
        """
        with self._client() as client:
            resp = client.get(f"/api/v1/models/{source}/{model_id}")
            if resp.status_code == 404:
                raise LookupError(f"Model not found: {source}/{model_id}")
            resp.raise_for_status()
            return resp.json()

    def remove(self, repo_id: str, source: str = "huggingface") -> bool:
        """Remove a model from Devon's local storage.

        Args:
            repo_id: Model repository ID (e.g. "meta-llama/Llama-3.1-8B").
            source: Model source (default: "huggingface").

        Returns:
            True if deleted, False if not found.
        """
        with self._client() as client:
            resp = client.delete(f"/api/v1/models/{source}/{repo_id}")
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            data = resp.json()
            return data.get("deleted", False)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        repo_id: str,
        allow_patterns: list[str] | None = None,
        source: str = "huggingface",
        force: bool = False,
    ) -> Path:
        """Download a model via the Devon API.

        This is a synchronous operation — the Devon server downloads
        the model and responds when complete. Can take 30+ minutes
        for large models.

        Args:
            repo_id: HuggingFace repository ID.
            allow_patterns: Optional file patterns to include (e.g. ["*.gguf"]).
            source: Model source (default: "huggingface").
            force: Re-download even if already present.

        Returns:
            Path to the model on the Devon server's filesystem.

        Raises:
            RuntimeError: If the download fails.
        """
        body: dict[str, Any] = {
            "model_id": repo_id,
            "source": source,
            "force": force,
        }
        if allow_patterns:
            body["include_patterns"] = allow_patterns

        with self._client(timeout=self._config.download_timeout) as client:
            resp = client.post("/api/v1/downloads", json=body)
            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                if len(detail) > 200:
                    detail = detail[:197] + "..."
                raise RuntimeError(f"Devon download failed for {repo_id}: {detail}")
            data = resp.json()
            return Path(data["path"])

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Get storage statistics from Devon.

        Returns:
            Dict with model_count, total_size_bytes, storage_path, sources.
        """
        with self._client() as client:
            resp = client.get("/api/v1/status")
            resp.raise_for_status()
            return resp.json()

    def disk_usage_gb(self, repo_id: str, source: str = "huggingface") -> float:
        """Get disk usage for a specific model in GB.

        Args:
            repo_id: Model repository ID.
            source: Model source.

        Returns:
            Disk usage in GB, or 0.0 if unknown.
        """
        try:
            info = self.model_info(source, repo_id)
            local = info.get("local")
            if local and "size_bytes" in local:
                return local["size_bytes"] / (1024**3)
        except Exception:
            pass
        return 0.0

    def find_path(self, repo_id: str, source: str = "huggingface") -> str | None:
        """Find the storage path for a model on the Devon server.

        Args:
            repo_id: Model repository ID.
            source: Model source.

        Returns:
            Path string on the Devon server, or None if not found.
        """
        try:
            info = self.model_info(source, repo_id)
            local = info.get("local")
            if local:
                return local.get("path")
        except Exception:
            pass
        return None

    def clean(
        self,
        unused: bool = False,
        days: int = 30,
        all_models: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Clean up models on the Devon server.

        Args:
            unused: Remove models not used within 'days' days.
            days: Number of days for the unused cutoff.
            all_models: Remove all models.
            dry_run: Preview what would be removed without deleting.

        Returns:
            Dict with removed count, freed_bytes, dry_run flag, model list.
        """
        body = {
            "unused": unused,
            "days": days,
            "all": all_models,
            "dry_run": dry_run,
        }
        with self._client() as client:
            resp = client.post("/api/v1/clean", json=body)
            resp.raise_for_status()
            return resp.json()

    def export(self, fmt: str = "kitt") -> dict[str, Any]:
        """Export model list from Devon.

        Args:
            fmt: Export format — "kitt" for paths, "json" for full details.

        Returns:
            Dict with format, count, and content.
        """
        with self._client() as client:
            resp = client.post("/api/v1/export", json={"format": fmt})
            resp.raise_for_status()
            return resp.json()
