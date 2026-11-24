"""Self-signed certificate for the local HTTPS game port (--tls-port 8443).

Replaces the openssl call in game_server.tls_cert() on Windows machines
without openssl. Writes server/state/tls/cert.pem + key.pem (CN=MQEL,
SAN = 127.0.0.1, localhost and this PC's LAN IP), valid 10 years.
For a public server add the public IP (--ip) and/or a host name (--dns,
e.g. a free DynDNS name) that remote players put in PublicLauncherSettings.json.

Usage: python tools/make_local_cert.py [--force] [--ip 203.0.113.7 ...] [--dns mqel.example.org ...]
Then bake cert.pem into the game exe: tools/patch_ca.py (see docs/60-client.md).
"""

import argparse
import datetime
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import secrets
from cryptography.x509.oid import NameOID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TLS = os.path.join(ROOT, "server", "state", "tls")


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.connect(("192.0.2.1", 9))
            return u.getsockname()[0]
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="overwrite an existing certificate")
    ap.add_argument("--ip", action="append", default=[], help="extra IP for the certificate")
    ap.add_argument("--dns", action="append", default=[], help="extra host name for the certificate")
    ap.add_argument("--minimal", action="store_true",
                    help="leave out localhost and the LAN IP: the certificate must fit slot 3 "
                         "of the exe (1057 bytes PEM), see tools/setup_public_server.ps1")
    args = ap.parse_args()

    cert_path, key_path = os.path.join(TLS, "cert.pem"), os.path.join(TLS, "key.pem")
    if os.path.exists(cert_path) and not args.force:
        print("exists:", cert_path, "(use --force to replace)")
        return
    os.makedirs(TLS, exist_ok=True)

    ips = {"127.0.0.1", *args.ip}
    if lan_ip() and not args.minimal:
        ips.add(lan_ip())
    # RSA only: the game's OpenSSL 1.0.1e offers no ECDSA cipher suites
    # (EC certificate -> "no shared cipher", tested 2026-11-20)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MQEL")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(secrets.randbits(31) | 1 << 30)  # short serial: fewer bytes
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(
                [x509.DNSName(d) for d in ([] if args.minimal else ["localhost"]) + sorted(set(args.dns))]
                + [x509.IPAddress(ipaddress.ip_address(i)) for i in sorted(ips)]),
                critical=False)
            .sign(key, hashes.SHA256()))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("certificate:", cert_path, "IPs:", ", ".join(sorted(ips)),
          "names:", ", ".join(([] if args.minimal else ["localhost"]) + sorted(set(args.dns))),
          "size:", len(cert.public_bytes(serialization.Encoding.PEM)), "bytes")


if __name__ == "__main__":
    main()
