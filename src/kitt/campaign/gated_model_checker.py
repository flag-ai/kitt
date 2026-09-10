"""Gated model detection — check HuggingFace model access."""

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

HF_API_BASE = "https://huggingface.co/api/models"


class GatedModelChecker:
    """Check whether HuggingFace models are gated or restricted."""

    def __init__(self, hf_token: str | None = None) -> None:
        self.hf_token = hf_token

    def is_gated(self, repo_id: str) -> bool:
        """Check if a model is gated (requires acceptance of terms).

        Args:
            repo_id: HuggingFace model repo ID (e.g. "meta-llama/Llama-3.1-8B").

        Returns:
            True if the model is gated.
        """
        info = self._fetch_model_info(repo_id)
        if info is None:
            return False
        return info.get("gated", False) is not False

    def check_access(self, repo_id: str) -> dict[str, Any]:
        """Check access status for a model.

        Returns:
            Dict with keys: repo_id, gated, accessible, error.
        """
        info = self._fetch_model_info(repo_id)
        if info is None:
            return {
                "repo_id": repo_id,
                "gated": False,
                "accessible": False,
                "error": "Could not fetch model info",
            }

        gated = info.get("gated", False) is not False
        # If gated and we don't have a token, assume inaccessible
        accessible = True
        if gated and not self.hf_token:
            accessible = False

        return {
            "repo_id": repo_id,
            "gated": gated,
            "accessible": accessible,
            "error": None,
        }

    def filter_accessible(self, repo_ids: list[str]) -> tuple[list[str], list[str]]:
        """Filter a list of repos into accessible and inaccessible.

        Returns:
            Tuple of (accessible, inaccessible) repo ID lists.
        """
        accessible = []
        inaccessible = []

        for repo_id in repo_ids:
            status = self.check_access(repo_id)
            if status["accessible"]:
                accessible.append(repo_id)
            else:
                inaccessible.append(repo_id)
                logger.warning(
                    f"Model {repo_id} is gated/inaccessible: "
                    f"gated={status['gated']}, error={status.get('error')}"
                )

        return accessible, inaccessible

    def _fetch_model_info(self, repo_id: str) -> dict[str, Any] | None:
        """Fetch model info from HuggingFace API."""
        url = f"{HF_API_BASE}/{repo_id}"
        headers = {}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                logger.debug(f"Unauthorized access to {repo_id}")
                return {"gated": True}
            elif e.code == 404:
                logger.debug(f"Model not found: {repo_id}")
                return None
            else:
                logger.debug(f"HTTP {e.code} fetching {repo_id}")
                return None
        except Exception as e:
            logger.debug(f"Error fetching model info for {repo_id}: {e}")
            return None
