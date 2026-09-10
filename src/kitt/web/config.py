"""Web application configuration model."""

from pathlib import Path

from pydantic import BaseModel, Field

from kitt.security.tls_config import TLSConfig


class WebConfig(BaseModel):
    """Configuration for the KITT web server."""

    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    secret_key: str = ""
    results_dir: Path = Field(default_factory=Path.cwd)
    db_path: Path = Field(default_factory=lambda: Path.home() / ".kitt" / "kitt.db")
    tls: TLSConfig = Field(default_factory=TLSConfig)
    insecure: bool = False
    legacy: bool = False
    auth_token: str = ""
