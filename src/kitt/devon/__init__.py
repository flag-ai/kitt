"""Remote Devon client for HTTP-based model management.

This package provides a client for connecting to a containerized Devon
instance over HTTP. It's the remote counterpart to the local DevonBridge
in ``kitt.campaign.devon_bridge``.

Resolution order used by KITT:
1. Remote Devon (this package) — when a Devon URL is configured
2. Local DevonBridge — when Devon is installed as a Python package
3. Devon CLI — subprocess fallback
"""

from .client import HTTPX_AVAILABLE, RemoteDevonClient
from .config import DevonConnectionConfig

__all__ = [
    "DevonConnectionConfig",
    "RemoteDevonClient",
    "HTTPX_AVAILABLE",
]
