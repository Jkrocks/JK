"""Home HTTPS.

Browsers only allow the microphone on secure (https) pages. To let phones,
tablets and TVs talk to Tejas over home Wi-Fi with no internet, Tejas makes
its own little certificate authority ("Tejas Home CA") and a certificate for
this computer's local addresses. Everything is made offline, once.

Install tejas-home-ca.crt on a device (from the Connect screen) to remove the
"not private" warning; or just tap "Advanced → Proceed" once.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def lan_ips() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    ips.discard("0.0.0.0")
    return sorted(i for i in ips if not i.startswith("127."))


def _key():
    return ec.generate_private_key(ec.SECP256R1())


def _write_key(key, path: Path):
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def ensure(folder: Path) -> tuple[Path, Path, Path]:
    """Return (cert, key, ca_cert), creating or refreshing them if needed."""
    folder.mkdir(parents=True, exist_ok=True)
    ca_crt, ca_key = folder / "tejas-home-ca.crt", folder / "tejas-home-ca.key"
    crt, key = folder / "server.crt", folder / "server.key"
    now = dt.datetime.now(dt.timezone.utc)

    if not (ca_crt.exists() and ca_key.exists()):
        k = _key()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Tejas Home CA"),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tejas AI (this home only)")])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
                .not_valid_after(now + dt.timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                             content_commitment=False, key_encipherment=False,
                                             data_encipherment=False, key_agreement=False,
                                             encipher_only=False, decipher_only=False), critical=True)
                .sign(k, hashes.SHA256()))
        _write_key(k, ca_key)
        ca_crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        for p in (crt, key):
            p.unlink(missing_ok=True)

    host = socket.gethostname()
    ips = lan_ips()
    want_dns = sorted({"localhost", host, f"{host}.local", "tejas.local"})
    want_ips = sorted(set(ips) | {"127.0.0.1"})

    if crt.exists() and key.exists():
        cur = x509.load_pem_x509_certificate(crt.read_bytes())
        try:
            san = cur.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            have_ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
            fresh = cur.not_valid_after_utc - now > dt.timedelta(days=30)
            if fresh and set(want_ips) <= have_ips:
                return crt, key, ca_crt
        except x509.ExtensionNotFound:
            pass

    ca_k = serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
    ca = x509.load_pem_x509_certificate(ca_crt.read_bytes())
    k = _key()
    san = [x509.DNSName(d) for d in want_dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in want_ips]
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Tejas AI")]))
            .issuer_name(ca.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=800))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_k, hashes.SHA256()))
    _write_key(k, key)
    # Full chain (this computer + home CA) so the Tejas apps can check it against the pinned CA.
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca_crt.read_bytes())
    return crt, key, ca_crt


def ca_fingerprint(ca_crt: Path) -> str:
    """Short code shown on the Connect screen, so families can check the apps paired with the right computer."""
    c = x509.load_pem_x509_certificate(ca_crt.read_bytes())
    h = c.fingerprint(hashes.SHA256()).hex().upper()
    return " ".join(h[i:i + 4] for i in range(0, 16, 4))
