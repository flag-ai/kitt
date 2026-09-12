"""Python-level integration bridge to Devon model manager.

Devon manages model downloads, storage, and lifecycle. This bridge
wraps Devon's Python API directly (no subprocess calls) for use
in KITT campaigns.

Falls back gracefully when Devon is not installed.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEVON_AVAILABLE = False
try:
    from devon.sources.huggingface import HuggingFaceSource
    from devon.storage.manager import ModelStorage

    DEVON_AVAILABLE = True
except ImportError:
    pass


class DevonBridge:
    """Bridge to Devon for model lifecycle management.

    Provides download, remove, and path lookup operations
    via Devon's Python API.
    """

    def __init__(self, storage_path: str | None = None) -> None:
        """Initialize the Devon bridge.

        Args:
            storage_path: Override Devon's model storage path.
                Defaults to Devon's configured storage location.

        Raises:
            ImportError: If Devon is not installed.
        """
        if not DEVON_AVAILABLE:
            raise ImportError(
                "Devon is not installed. "
                "Install with: pip install devon  "
                "or: pip install kitt[devon]"
            )

        self._storage = ModelStorage(root=Path(storage_path) if storage_path else None)
        self._hf_source = HuggingFaceSource()

    @property
    def storage_root(self) -> Path:
        """Devon's model storage root directory."""
        return self._storage.root

    def download(
        self,
        repo_id: str,
        allow_patterns: list[str] | None = None,
    ) -> Path:
        """Download a model from HuggingFace.

        Args:
            repo_id: HuggingFace repository ID (e.g. "meta-llama/Llama-3.1-8B").
            allow_patterns: Optional file patterns to include (e.g. ["*.gguf"]).

        Returns:
            Path to the downloaded model directory.

        Raises:
            RuntimeError: If download fails.
        """
        logger.info(
            f"Downloading {repo_id} via Devon"
            + (f" (patterns: {allow_patterns})" if allow_patterns else "")
        )
        try:
            path = self._hf_source.download_model(
                repo_id,
                storage=self._storage,
                allow_patterns=allow_patterns,
            )
            logger.info(f"Download complete: {path}")
            return path
        except Exception as e:
            raise RuntimeError(f"Devon download failed for {repo_id}: {e}") from e

    def remove(self, repo_id: str) -> bool:
        """Remove a downloaded model.

        Args:
            repo_id: HuggingFace repository ID.

        Returns:
            True if removed successfully.
        """
        logger.info(f"Removing {repo_id} via Devon")
        try:
            self._storage.remove(repo_id)
            return True
        except Exception as e:
            logger.warning(f"Remove failed for {repo_id}: {e}")
            return False

    def find_path(self, repo_id: str) -> Path | None:
        """Find the local path for a downloaded model.

        Args:
            repo_id: HuggingFace repository ID.

        Returns:
            Path to model directory, or None if not found.
        """
        try:
            path = self._storage.get_path(repo_id)
            if path and path.exists():
                return path
        except Exception:
            pass
        return None

    def list_models(self) -> list[str]:
        """List all downloaded model repository IDs.

        Returns:
            List of repo IDs currently in Devon storage.
        """
        try:
            return self._storage.list_models()
        except Exception as e:
            logger.warning(f"Failed to list models: {e}")
            return []

    def disk_usage_gb(self, repo_id: str) -> float:
        """Get disk usage for a specific model in GB.

        Args:
            repo_id: HuggingFace repository ID.

        Returns:
            Disk usage in GB, or 0.0 if unknown.
        """
        path = self.find_path(repo_id)
        if not path:
            return 0.0

        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return total / (1024**3)


def is_devon_available() -> bool:
    """Check if Devon is importable."""
    return DEVON_AVAILABLE
