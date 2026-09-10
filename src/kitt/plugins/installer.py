"""Plugin installer — pip install wrapper with version pinning."""

import logging
import subprocess
import sys

logger = logging.getLogger(__name__)


def install_plugin(
    package: str,
    version: str | None = None,
    upgrade: bool = False,
) -> bool:
    """Install a plugin package via pip.

    Args:
        package: Package name (e.g. "kitt-plugin-example").
        version: Optional version pin (e.g. ">=0.2.0").
        upgrade: If True, upgrade to latest compatible version.

    Returns:
        True if installation succeeded.
    """
    spec = package
    if version:
        spec = f"{package}{version}"

    args = [sys.executable, "-m", "pip", "install", spec]
    if upgrade:
        args.append("--upgrade")

    logger.info(f"Installing plugin: {spec}")

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            logger.error(f"pip install failed: {result.stderr}")
            return False
        logger.info(f"Successfully installed {spec}")
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"Installation timed out for {spec}")
        return False
    except Exception as e:
        logger.error(f"Installation failed: {e}")
        return False


def uninstall_plugin(package: str) -> bool:
    """Uninstall a plugin package via pip.

    Args:
        package: Package name to remove.

    Returns:
        True if removal succeeded.
    """
    args = [sys.executable, "-m", "pip", "uninstall", "-y", package]

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.error(f"pip uninstall failed: {result.stderr}")
            return False
        logger.info(f"Uninstalled {package}")
        return True
    except Exception as e:
        logger.error(f"Uninstall failed: {e}")
        return False


def list_installed_plugins() -> list:
    """List installed KITT plugin packages.

    Returns:
        List of dicts with name, version for packages matching kitt-plugin-*.
    """
    try:
        from importlib.metadata import distributions

        plugins = []
        for dist in distributions():
            name = dist.metadata["Name"]
            if name and name.startswith("kitt-plugin-"):
                plugins.append(
                    {
                        "name": name,
                        "version": dist.metadata["Version"],
                    }
                )
        return plugins
    except Exception:
        return []
