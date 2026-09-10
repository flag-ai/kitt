"""TLS configuration models for KITT server and agent."""

from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CERTS_DIR = Path.home() / ".kitt" / "certs"


class TLSConfig(BaseModel):
    """TLS configuration for server or agent."""

    enabled: bool = True
    cert: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "server.pem")
    key: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "server-key.pem")
    ca: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "ca.pem")

    def is_configured(self) -> bool:
        """Check if cert files exist on disk."""
        return self.cert.exists() and self.key.exists() and self.ca.exists()


class AgentTLSConfig(BaseModel):
    """TLS configuration for an agent."""

    cert: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "agent.pem")
    key: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "agent-key.pem")
    ca: Path = Field(default_factory=lambda: DEFAULT_CERTS_DIR / "ca.pem")

    def is_configured(self) -> bool:
        """Check if cert files exist on disk."""
        return self.cert.exists() and self.key.exists() and self.ca.exists()
