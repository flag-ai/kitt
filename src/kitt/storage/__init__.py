"""Storage backends for KITT benchmark results."""

from .base import ResultStore
from .json_store import JsonStore

__all__ = ["ResultStore", "JsonStore"]
