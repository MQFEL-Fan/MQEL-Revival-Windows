#!/usr/bin/env python3
"""Generate self-signed TLS certificate using Python's cryptography library.

This script creates a self-signed certificate and private key for local testing.
It will attempt to install the cryptography library if not already installed.
"""

import datetime
import ipaddress
import os
import subprocess
import sys


def install_cryptography():
    """Install the cryptography library."""
    print("Installing cryptography library...")
    try:
        # Try different methods to install the package
        commands = [
            ["pip", "install", "cryptography"],
            ["python", "-m", "pip", "install", "cryptography"],
            ["py", "-m", "pip", "install", "cryptography"]
        ]
        
        for cmd in commands:
            try:
                result = subprocess.run(cmd, check=True, capture_output=True)
                print("Successfully installed cryptography library")
                return True
            except Exception as e:
                print(f"Failed to install with {cmd}: {e}")
        
        raise Exception("All installation methods failed")
    except Exception as e:
        print(f"Error installing cryptography library: {e}")
        raise


def generate_certificate(cert_path="cert.pem", key_path="key.pem"):
    """Generate a self-signed certificate using Python's cryptography library."""
    
    # Create directories if they don't exist
    cert_dir = os.path.dirname(cert_path)
    key_dir = os.path.dirname(key_path)
    
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir, exist_ok=True)
    if not os.path.exists(key_dir):
        os.makedirs(key_dir, exist_ok=True)
    
    # Try to import cryptography library
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
        print("Cryptography library not found. Installing...")
        install_cryptography()
        
        # Try importing again after installation
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives.serialization import (
                Encoding, PrivateFormat, NoEncryption
            )
        except ImportError as e:
            print(f"Failed to install or import cryptography library: {e}")
            raise
    
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
    cert_path = "server/state/tls/cert.pem"
    key_path = "server/state/tls/key.pem"
    
    if len(sys.argv) >= 3:
        cert_path = sys.argv[1]
        key_path = sys.argv[2]
    
    try:
        generate_certificate(cert_path, key_path)
    except Exception as e:
        print(f"Error generating certificate: {e}")
        sys.exit(1)
