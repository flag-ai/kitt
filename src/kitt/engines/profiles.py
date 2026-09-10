"""Engine configuration profiles."""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default profiles directory
_PROFILES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "configs"
    / "engines"
    / "profiles"
)


class EngineProfileManager:
    """Load and manage engine configuration profiles.

    Profiles are YAML files in configs/engines/profiles/ that define
    named engine configurations (e.g., llama_cpp-high-ctx.yaml).
    """

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self.profiles_dir = profiles_dir or _PROFILES_DIR

    def list_profiles(self, engine_name: str | None = None) -> list[str]:
        """List available profile names.

        Args:
            engine_name: Filter to profiles for a specific engine.

        Returns:
            List of profile names (without .yaml extension).
        """
        if not self.profiles_dir.exists():
            return []

        profiles = []
        for f in sorted(self.profiles_dir.glob("*.yaml")):
            name = f.stem
            if engine_name is None or name.startswith(f"{engine_name}-"):
                profiles.append(name)
        return profiles

    def load_profile(self, profile_name: str) -> dict[str, Any]:
        """Load a profile by name.

        Args:
            profile_name: Profile name (e.g., "llama_cpp-default").

        Returns:
            Configuration dict from the profile.

        Raises:
            FileNotFoundError: If profile doesn't exist.
        """
        profile_path = self.profiles_dir / f"{profile_name}.yaml"
        if not profile_path.exists():
            raise FileNotFoundError(
                f"Profile not found: {profile_name} (looked in {self.profiles_dir})"
            )

        with open(profile_path) as f:
            data = yaml.safe_load(f)
        return data if data else {}

    def merge_with_profile(
        self,
        base_config: dict[str, Any],
        profile_name: str,
    ) -> dict[str, Any]:
        """Merge a profile's config into a base config.

        Profile values are applied first, then base_config overrides.
        This means explicit user config takes precedence.

        Args:
            base_config: User-provided configuration.
            profile_name: Profile to load and merge.

        Returns:
            Merged configuration dict.
        """
        profile_data = self.load_profile(profile_name)
        merged = {**profile_data, **base_config}
        return merged
