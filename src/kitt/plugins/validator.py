"""Plugin compatibility validation."""

import logging

logger = logging.getLogger(__name__)


class PluginValidator:
    """Validate plugin compatibility and requirements."""

    def validate_manifest(self, manifest_data: dict) -> tuple[bool, list[str]]:
        """Validate a plugin manifest has required fields.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        errors = []
        required = ["name", "version", "plugin_type", "entry_point"]

        for field in required:
            if not manifest_data.get(field):
                errors.append(f"Missing required field: {field}")

        valid_types = {"engine", "benchmark", "reporter"}
        ptype = manifest_data.get("plugin_type", "")
        if ptype and ptype not in valid_types:
            errors.append(
                f"Invalid plugin_type: {ptype}. Must be one of: {valid_types}"
            )

        return len(errors) == 0, errors

    def check_dependencies(self, package_name: str) -> tuple[bool, list[str]]:
        """Check if a plugin's dependencies are satisfiable.

        Returns:
            Tuple of (all_satisfied, list_of_missing).
        """
        try:
            from importlib.metadata import distribution

            dist = distribution(package_name)
            requires = dist.requires or []
        except Exception:
            return True, []  # Can't check, assume OK

        missing = []
        for req in requires:
            # Strip extras and version constraints for basic check
            pkg = (
                req.split(";")[0]
                .split("[")[0]
                .split(">=")[0]
                .split("<=")[0]
                .split("==")[0]
                .strip()
            )
            try:
                from importlib.metadata import distribution as dist_fn

                dist_fn(pkg)
            except Exception:
                missing.append(pkg)

        return len(missing) == 0, missing

    def validate_entry_point(self, entry_point: str) -> bool:
        """Check if an entry point is importable.

        Args:
            entry_point: Module path like "my_plugin.engine:MyEngine".

        Returns:
            True if the entry point can be resolved.
        """
        try:
            if ":" in entry_point:
                module_path, attr_name = entry_point.split(":", 1)
            else:
                return False

            import importlib

            mod = importlib.import_module(module_path)
            return hasattr(mod, attr_name)
        except Exception:
            return False
