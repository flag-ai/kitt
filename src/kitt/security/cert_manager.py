"""Self-signed CA and certificate generation for KITT TLS.

Uses the `cryptography` library to generate:
- A self-signed Certificate Authority (CA)
- Server certificates signed by the CA
- Agent certificates signed by the CA

All certs are stored in ~/.kitt/certs/ by default.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .tls_config import DEFAULT_CERTS_DIR

logger = logging.getLogger(__name__)

# Certificate validity
CA_VALIDITY_DAYS = 3650  # 10 years
CERT_VALIDITY_DAYS = 365  # 1 year


def _ensure_cryptography():
    """Import and return cryptography modules, raising helpful error if missing."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        return x509, hashes, serialization, rsa, NameOID
    except ImportError:
        raise ImportError(
            "The 'cryptography' package is required for TLS certificate generation. "
            "Install with: pip install 'kitt[web]'"
        ) from None


def get_ca_fingerprint(ca_cert_path: Path) -> str:
    """Get the SHA-256 fingerprint of a CA certificate.

    Args:
        ca_cert_path: Path to the CA certificate PEM file.

    Returns:
        Colon-separated SHA-256 fingerprint string.
    """
    x509, hashes, serialization, _, _ = _ensure_cryptography()
    cert_pem = ca_cert_path.read_bytes()
    cert = x509.load_pem_x509_certificate(cert_pem)
    digest = cert.fingerprint(hashes.SHA256())
    return ":".join(f"{b:02X}" for b in digest)


def generate_ca(
    certs_dir: Path | None = None,
    cn: str = "KITT CA",
) -> tuple[Path, Path]:
    """Generate a self-signed Certificate Authority.

    Args:
        certs_dir: Directory to store certs. Defaults to ~/.kitt/certs/.
        cn: Common Name for the CA certificate.

    Returns:
        Tuple of (ca_cert_path, ca_key_path).
    """
    x509, hashes, serialization, rsa, NameOID = _ensure_cryptography()

    certs_dir = certs_dir or DEFAULT_CERTS_DIR
    certs_dir.mkdir(parents=True, exist_ok=True)

    ca_key_path = certs_dir / "ca-key.pem"
    ca_cert_path = certs_dir / "ca.pem"

    # Generate CA private key
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    # Build CA certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "KITT"),
        ]
    )

    now = datetime.now(timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=CA_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Write key with restricted permissions
    ca_key_path.write_bytes(
        ca_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    os.chmod(ca_key_path, 0o600)

    # Write certificate
    ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))

    logger.info(f"Generated CA certificate: {ca_cert_path}")
    fingerprint = get_ca_fingerprint(ca_cert_path)
    logger.info(f"CA fingerprint (SHA-256): {fingerprint}")

    return ca_cert_path, ca_key_path


def generate_cert(
    name: str,
    ca_cert_path: Path,
    ca_key_path: Path,
    certs_dir: Path | None = None,
    san_dns: list[str] | None = None,
    san_ips: list[str] | None = None,
    is_server: bool = True,
) -> tuple[Path, Path]:
    """Generate a certificate signed by the CA.

    Args:
        name: Certificate name (used for filename and CN).
        ca_cert_path: Path to CA certificate.
        ca_key_path: Path to CA private key.
        certs_dir: Output directory. Defaults to ~/.kitt/certs/.
        san_dns: DNS Subject Alternative Names.
        san_ips: IP Subject Alternative Names.
        is_server: If True, add server auth extended key usage.

    Returns:
        Tuple of (cert_path, key_path).
    """
    x509, hashes, serialization, rsa, NameOID = _ensure_cryptography()
    import ipaddress

    from cryptography.x509.oid import ExtendedKeyUsageOID

    certs_dir = certs_dir or DEFAULT_CERTS_DIR
    certs_dir.mkdir(parents=True, exist_ok=True)

    cert_path = certs_dir / f"{name}.pem"
    key_path = certs_dir / f"{name}-key.pem"

    # Load CA
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)

    # Generate key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "KITT"),
        ]
    )

    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=CERT_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )

    # Extended key usage
    usages = []
    if is_server:
        usages.append(ExtendedKeyUsageOID.SERVER_AUTH)
    usages.append(ExtendedKeyUsageOID.CLIENT_AUTH)
    builder = builder.add_extension(x509.ExtendedKeyUsage(usages), critical=False)

    # Subject Alternative Names
    san_entries: list = []
    for dns in san_dns or ["localhost"]:
        san_entries.append(x509.DNSName(dns))
    for ip_str in san_ips or ["127.0.0.1", "::1"]:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(ip_str)))
    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries), critical=False
        )

    cert = builder.sign(ca_key, hashes.SHA256())

    # Write key with restricted permissions
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    os.chmod(key_path, 0o600)

    # Write certificate
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    logger.info(f"Generated certificate '{name}': {cert_path}")
    return cert_path, key_path


def ensure_server_certs(
    certs_dir: Path | None = None,
    san_dns: list[str] | None = None,
    san_ips: list[str] | None = None,
) -> tuple[Path, Path, Path]:
    """Ensure CA and server certificates exist, generating if needed.

    Returns:
        Tuple of (ca_cert_path, server_cert_path, server_key_path).
    """
    certs_dir = certs_dir or DEFAULT_CERTS_DIR
    ca_cert_path = certs_dir / "ca.pem"
    ca_key_path = certs_dir / "ca-key.pem"
    server_cert_path = certs_dir / "server.pem"
    server_key_path = certs_dir / "server-key.pem"

    if not ca_cert_path.exists() or not ca_key_path.exists():
        ca_cert_path, ca_key_path = generate_ca(certs_dir)

    if not server_cert_path.exists() or not server_key_path.exists():
        server_cert_path, server_key_path = generate_cert(
            "server",
            ca_cert_path,
            ca_key_path,
            certs_dir=certs_dir,
            san_dns=san_dns,
            san_ips=san_ips,
            is_server=True,
        )

    return ca_cert_path, server_cert_path, server_key_path


def generate_agent_cert(
    agent_name: str,
    ca_cert_path: Path | None = None,
    ca_key_path: Path | None = None,
    certs_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Generate a certificate for a KITT agent.

    Args:
        agent_name: Agent name (used in cert filename and CN).
        ca_cert_path: Path to CA cert. Defaults to ~/.kitt/certs/ca.pem.
        ca_key_path: Path to CA key. Defaults to ~/.kitt/certs/ca-key.pem.
        certs_dir: Output directory.

    Returns:
        Tuple of (agent_cert_path, agent_key_path).
    """
    certs_dir = certs_dir or DEFAULT_CERTS_DIR
    ca_cert_path = ca_cert_path or certs_dir / "ca.pem"
    ca_key_path = ca_key_path or certs_dir / "ca-key.pem"

    return generate_cert(
        f"agent-{agent_name}",
        ca_cert_path,
        ca_key_path,
        certs_dir=certs_dir,
        san_dns=[agent_name, "localhost"],
        is_server=False,
    )


def create_ssl_context(
    cert_path: Path,
    key_path: Path,
    ca_path: Path,
    server_side: bool = True,
) -> Any:
    """Create an SSL context for server or client use.

    Args:
        cert_path: Path to the certificate PEM.
        key_path: Path to the private key PEM.
        ca_path: Path to the CA certificate PEM.
        server_side: True for server context, False for client.

    Returns:
        Configured ssl.SSLContext.
    """
    import ssl

    if server_side:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.verify_mode = ssl.CERT_OPTIONAL  # Accept but don't require client certs
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False  # We verify against our own CA

    ctx.load_cert_chain(str(cert_path), str(key_path))
    ctx.load_verify_locations(str(ca_path))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    return ctx
