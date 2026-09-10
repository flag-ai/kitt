"""Configuration for remote Devon connections."""

from pydantic import BaseModel, Field


class DevonConnectionConfig(BaseModel):
    """Connection settings for a remote Devon instance.

    Attributes:
        url: Base URL of the Devon REST API (e.g. "http://192.168.1.50:8000").
        api_key: Bearer token for Devon API authentication. Only required
            when the Devon instance has DEVON_API_KEY set.
        timeout: Timeout in seconds for normal API requests.
        download_timeout: Timeout in seconds for model downloads (can take 30+ min).
    """

    url: str | None = None
    api_key: str | None = None
    timeout: float = Field(default=30.0, ge=1.0)
    download_timeout: float = Field(default=7200.0, ge=60.0)
