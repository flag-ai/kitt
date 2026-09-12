"""Model storage manager — copy models from NFS share to local storage."""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelStorageManager:
    """Manages local model storage with optional NFS share mounting."""

    def __init__(
        self,
        storage_dir: str,
        share_source: str = "",
        share_mount: str = "",
        auto_cleanup: bool = True,
    ) -> None:
        self.storage_dir = Path(storage_dir).expanduser()
        self.share_source = share_source
        self.share_mount = Path(share_mount).expanduser() if share_mount else None
        self.auto_cleanup = auto_cleanup

        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def update_settings(
        self,
        storage_dir: str = "",
        share_source: str = "",
        share_mount: str = "",
        auto_cleanup: bool | None = None,
    ) -> None:
        """Update settings from server-synced values."""
        if storage_dir:
            self.storage_dir = Path(storage_dir).expanduser()
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        if share_source:
            self.share_source = share_source
        if share_mount:
            self.share_mount = Path(share_mount).expanduser()
        if auto_cleanup is not None:
            self.auto_cleanup = auto_cleanup

    def ensure_share_mounted(self) -> bool:
        """Check if share_mount has content. If empty, attempt mount.

        Returns:
            True if the share is mounted and accessible, False otherwise.
        """
        if not self.share_mount:
            logger.warning("No share_mount configured — cannot mount NFS share")
            return False

        # Check if already mounted
        if self.share_mount.is_mount():
            logger.debug("Share already mounted at %s", self.share_mount)
            return True

        # Check if path has content (might be a bind mount or symlink)
        if self.share_mount.exists() and any(self.share_mount.iterdir()):
            logger.debug("Share path %s has content (bind/symlink)", self.share_mount)
            return True

        # Create mount point if needed
        try:
            self.share_mount.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            logger.warning(
                "Cannot create mount point %s — trying with sudo", self.share_mount
            )
            try:
                subprocess.run(
                    ["sudo", "mkdir", "-p", str(self.share_mount)],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
            except Exception as e:
                logger.error("Failed to create mount point %s: %s", self.share_mount, e)
                return False

        # Attempt mount (works if fstab is configured)
        try:
            result = subprocess.run(
                ["mount", str(self.share_mount)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Mounted share at %s via fstab", self.share_mount)
                return True
            logger.debug(
                "fstab mount failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
        except Exception as e:
            logger.debug("fstab mount failed: %s", e)

        # Fallback: explicit NFS mount
        if self.share_source:
            try:
                result = subprocess.run(
                    [
                        "sudo",
                        "mount",
                        "-t",
                        "nfs",
                        self.share_source,
                        str(self.share_mount),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logger.info(
                        "Mounted NFS share %s at %s",
                        self.share_source,
                        self.share_mount,
                    )
                    return True
                logger.error(
                    "NFS mount failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
            except Exception as e:
                logger.error("NFS mount failed: %s", e)
        else:
            logger.warning(
                "Share not mounted at %s and no share_source configured for NFS mount",
                self.share_mount,
            )

        return False

    def _find_on_share(self, model_path: str) -> Path | None:
        """Search the share for a model using progressively broader matches.

        Tries (in order):
        1. Relative path from the model_path (strip leading /data/models or similar)
        2. Recursive glob for the final directory name
        """
        if not self.share_mount or not self.share_mount.exists():
            return None

        parts = Path(model_path).parts

        # Strategy 1: Try stripping common prefixes to get the relative path
        # e.g., /data/models/huggingface/Qwen/Qwen3.5-27B → huggingface/Qwen/Qwen3.5-27B
        share_root = self.share_mount.resolve()
        for i in range(len(parts)):
            candidate = (self.share_mount / Path(*parts[i:])).resolve()
            try:
                candidate.relative_to(share_root)
            except ValueError:
                continue  # path traversal — skip
            if candidate.exists():
                logger.debug("Found model on share at %s (from part %d)", candidate, i)
                return candidate

        # Strategy 2: Recursive glob for the final directory name (cap at first match)
        model_name = parts[-1] if parts else ""
        if model_name:
            for match in self.share_mount.glob(f"**/{model_name}"):
                # Validate glob result stays under share root (symlinks may escape)
                try:
                    match.resolve().relative_to(share_root)
                except ValueError:
                    logger.debug("Glob match %s escapes share root — skipping", match)
                    continue
                logger.debug("Found model on share via glob: %s", match)
                return match

        return None

    def resolve_model(
        self,
        model_path: str,
        on_log: Callable[[str], None] | None = None,
    ) -> str:
        """Ensure model is available in local storage. Returns local path.

        1. If model_path is already under storage_dir, return as-is.
        2. If model exists on the NFS share, copy to storage_dir.
        3. If model_path is directly accessible, return as-is.

        Args:
            model_path: Path or identifier for the model.
            on_log: Optional callback for progress logging.

        Returns:
            Local path to the model.
        """

        def _log(msg: str) -> None:
            if on_log:
                on_log(msg)
            logger.info(msg)

        model_name = Path(model_path).name
        local_path = self.storage_dir / model_name

        # Already in local storage
        if local_path.exists():
            _log(f"Model already in local storage: {local_path}")
            return str(local_path)

        # model_path is under storage_dir (absolute match)
        if (
            Path(model_path).is_relative_to(self.storage_dir)
            and Path(model_path).exists()
        ):
            _log(f"Model at local path: {model_path}")
            return model_path

        # Try to mount share and find the model on it
        if self.share_mount:
            mounted = self.ensure_share_mounted()
            if mounted:
                share_model = self._find_on_share(model_path)
                if share_model:
                    _log(f"Copying model from share: {share_model} -> {local_path}")
                    try:
                        if share_model.is_dir():
                            shutil.copytree(
                                share_model,
                                local_path,
                                dirs_exist_ok=True,
                            )
                        else:
                            shutil.copy2(share_model, local_path)
                        _log(f"Model copied to local storage: {local_path}")
                        return str(local_path)
                    except Exception as e:
                        _log(f"Failed to copy model from share: {e}")
                else:
                    _log(f"Model not found on share for path: {model_path}")
            else:
                _log("Share mount failed — cannot look up model on share")

        # Fall through: model_path is directly accessible (e.g., absolute path)
        if Path(model_path).exists():
            _log(f"Using model at original path: {model_path}")
            return model_path

        # Last resort: return original path and let the benchmark fail
        # with a clear error if needed
        _log(f"Model not found locally or on share, using as-is: {model_path}")
        return model_path

    def cleanup_model(self, local_path: str) -> None:
        """Remove a model from local storage.

        Only deletes if path is under storage_dir (safety check).
        """
        path = Path(local_path)
        if not path.exists():
            return

        # Safety: only delete files under our storage directory
        try:
            path.resolve().relative_to(self.storage_dir.resolve())
        except ValueError:
            logger.warning(
                "Refusing to delete %s — not under storage_dir %s",
                local_path,
                self.storage_dir,
            )
            return

        logger.info("Cleaning up model: %s", local_path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def get_storage_usage(self) -> dict[str, float | int]:
        """Return storage usage statistics.

        Returns:
            Dict with used_gb, free_gb, and model_count.
        """
        try:
            usage = shutil.disk_usage(self.storage_dir)
            used_gb = round(usage.used / (1024**3), 2)
            free_gb = round(usage.free / (1024**3), 2)
        except OSError:
            used_gb = 0.0
            free_gb = 0.0

        # Count model directories/files in storage
        model_count = 0
        if self.storage_dir.exists():
            model_count = sum(
                1 for p in self.storage_dir.iterdir() if not p.name.startswith(".")
            )

        return {
            "used_gb": used_gb,
            "free_gb": free_gb,
            "model_count": model_count,
        }
