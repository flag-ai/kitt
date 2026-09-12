"""Plugin discovery via Python entry points."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Entry point group names
ENGINE_GROUP = "kitt.engines"
BENCHMARK_GROUP = "kitt.benchmarks"
REPORTER_GROUP = "kitt.reporters"


def _load_entry_points(group: str) -> list[Any]:
    """Load entry points for a given group.

    Uses importlib.metadata (Python 3.10+).
    """
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        # Python 3.12+ returns a SelectableGroups, 3.10-3.11 returns dict
        if isinstance(eps, dict):
            return list(eps.get(group, []))
        return list(eps.select(group=group))
    except Exception as e:
        logger.debug(f"Could not load entry points for {group}: {e}")
        return []


def discover_external_engines() -> list[type]:
    """Discover and load external engine plugins.

    Returns:
        List of engine classes found via entry points.
    """
    engines = []
    for ep in _load_entry_points(ENGINE_GROUP):
        try:
            cls = ep.load()
            engines.append(cls)
            logger.info(f"Discovered external engine plugin: {ep.name}")
        except Exception as e:
            logger.warning(f"Failed to load engine plugin '{ep.name}': {e}")
    return engines


def discover_external_benchmarks() -> list[type]:
    """Discover and load external benchmark plugins.

    Returns:
        List of benchmark classes found via entry points.
    """
    benchmarks = []
    for ep in _load_entry_points(BENCHMARK_GROUP):
        try:
            cls = ep.load()
            benchmarks.append(cls)
            logger.info(f"Discovered external benchmark plugin: {ep.name}")
        except Exception as e:
            logger.warning(f"Failed to load benchmark plugin '{ep.name}': {e}")
    return benchmarks


def discover_external_reporters() -> list[type]:
    """Discover and load external reporter plugins.

    Returns:
        List of reporter classes found via entry points.
    """
    reporters = []
    for ep in _load_entry_points(REPORTER_GROUP):
        try:
            cls = ep.load()
            reporters.append(cls)
            logger.info(f"Discovered external reporter plugin: {ep.name}")
        except Exception as e:
            logger.warning(f"Failed to load reporter plugin '{ep.name}': {e}")
    return reporters


def discover_plugins() -> dict[str, list[type]]:
    """Discover all external plugins across all groups.

    Returns:
        Dict mapping group name to list of loaded classes.
    """
    return {
        "engines": discover_external_engines(),
        "benchmarks": discover_external_benchmarks(),
        "reporters": discover_external_reporters(),
    }
