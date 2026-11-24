#!/usr/bin/env python3
"""Generate self-signed TLS certificate using Python's cryptography library.

This script creates a self-signed certificate and private key for local testing.
It doesn't require external OpenSSL installation.
"""

import datetime
import ipaddress
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PrivateFormat, NoEncryption
    )
except ImportError:
    print("Error: cryptography library not installed.")
    print("Install it with: pip install cryptography")
    exit(1)


def generate_certificate(cert_path="cert.pem", key_path="key.pem"):
    """Generate a self-signed certificate and private key."""
    
    # Generate private key
    print("Generating RSA private key...")
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Define certificate subject
    subject = x509.Name([
        x509.Attribute(NameOID.COUNTRY_NAME, "US"),
        x509.Attribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.Attribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.Attribute(NameOID.ORGANIZATION_NAME, "MQEL Revival"),
        x509.Attribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    # Create certificate
    print("Creating self-signed certificate...")
    cert = (
        x509.CertificateBuilder()
        .subject(subject)
        .issuer(subject)  # Self-signed: issuer == subject
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    
    # Write certificate and key to files
    cert_path = Path(cert_path)
    key_path = Path(key_path)
    
    # Create directories if they don't exist
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(Encoding.PEM))
    
    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                Encoding.PEM,
                PrivateFormat.TraditionalOpenSSL,
                NoEncryption(),
            )
        )
    
    print(f"Certificate written to: {cert_path}")
    print(f"Private key written to: {key_path}")


if __name__ == "__main__":
    import sys
    
    cert_path = "server/state/tls/cert.pem"
    key_path = "server/state/tls/key.pem"
    
    if len(sys.argv) >= 3:
        cert_path = sys.argv[1]
        key_path = sys.argv[2]
    
    generate_certificate(cert_path, key_path)
