"""Remote plugin registry index."""

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/kirizan/kitt-plugins/main/index.json"
)


class PluginIndex:
    """Remote plugin registry for discovering available plugins."""

    def __init__(self, index_url: str | None = None) -> None:
        self.index_url = index_url or DEFAULT_INDEX_URL
        self._cache: list[dict[str, Any]] | None = None

    def _fetch_index(self) -> list[dict[str, Any]]:
        """Fetch the plugin index from remote."""
        if self._cache is not None:
            return self._cache

        try:
            req = urllib.request.Request(self.index_url, headers={"User-Agent": "kitt"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                self._cache = data.get("plugins", [])
                return self._cache
        except Exception as e:
            logger.error(f"Failed to fetch plugin index: {e}")
            return []

    def search(
        self, query: str = "", plugin_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Search for plugins.

        Args:
            query: Search term (matches name or description).
            plugin_type: Filter by type (engine, benchmark, reporter).

        Returns:
            List of matching plugin info dicts.
        """
        plugins = self._fetch_index()
        results = []

        for p in plugins:
            if plugin_type and p.get("plugin_type") != plugin_type:
                continue
            if query:
                name = p.get("name", "").lower()
                desc = p.get("description", "").lower()
                if query.lower() not in name and query.lower() not in desc:
                    continue
            results.append(p)

        return results

    def get_info(self, name: str) -> dict[str, Any] | None:
        """Get detailed info for a plugin by name."""
        plugins = self._fetch_index()
        for p in plugins:
            if p.get("name") == name:
                return p
        return None

    def check_compatibility(self, name: str, kitt_version: str = "") -> bool:
        """Check if a plugin is compatible with the current KITT version.

        Args:
            name: Plugin name.
            kitt_version: Current KITT version string.

        Returns:
            True if compatible (or no constraint specified).
        """
        info = self.get_info(name)
        if not info:
            return False

        min_version = info.get("min_kitt_version", "")
        if not min_version or not kitt_version:
            return True

        # Simple version comparison
        try:
            from packaging.version import Version

            return Version(kitt_version) >= Version(min_version)
        except ImportError:
            # Fallback: compare as tuples
            curr = tuple(int(x) for x in kitt_version.split(".")[:3] if x.isdigit())
            req = tuple(int(x) for x in min_version.split(".")[:3] if x.isdigit())
            return curr >= req
