"""Certificate preparation for the opt-in, local G02 transport."""

import hashlib
import os
import re
import secrets
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Leaf:
    name: str
    san: str
    usages: tuple[str, ...]
    pin: str | None = None


_CLIENTS = {
    "operator": "operator",
    "dispatcher": "dispatcher",
    "cancellation": "backend-cancellation",
    "manager": "manager",
    "reconciliation": "reconciliation-observer",
}
TLS_GROUPS = {
    "temporal_frontend_ca": (
        Leaf("temporal_frontend", "DNS:temporal-workflow", ("serverAuth",)),
        *(Leaf(f"temporal_{file}", f"URI:spiffe://ai-res/temporal/{role}", ("clientAuth",), role) for file, role in _CLIENTS.items()),
    ),
    "temporal_internode_ca": (Leaf("temporal_internode", "DNS:temporal-internode", ("serverAuth", "clientAuth")),),
    "temporal_platform_ca": (Leaf("g02_platform_tls", "DNS:platform-api", ("serverAuth",)),),
    "g02_delivery_ca": (Leaf("g02_delivery_tls", "DNS:assigned-delivery", ("serverAuth",)),),
}
TLS_NAMES = frozenset(TLS_GROUPS) | {
    f"{leaf.name}_{suffix}" for leaves in TLS_GROUPS.values() for leaf in leaves for suffix in ("cert", "key")
}
_PEM_CERTIFICATE = re.compile(r"-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----(?:\r?\n)?")
_EC_PRIVATE_KEY_LABEL = "EC PRIVATE KEY"
_PEM_PRIVATE_KEY = re.compile(
    rf"-----BEGIN {_EC_PRIVATE_KEY_LABEL}-----\r?\n[A-Za-z0-9+/=\r\n]+-----END {_EC_PRIVATE_KEY_LABEL}-----(?:\r?\n)?",
)
_PURPOSE = {"serverAuth": "sslserver", "clientAuth": "sslclient"}
_EXTENDED_KEY_USAGE = {"serverAuth": "TLS Web Server Authentication", "clientAuth": "TLS Web Client Authentication"}
# Linux Compose mounts each credential file individually. Its non-root service UIDs need read
# permission on those mounts. On the host, only the invoking user can traverse the enclosing directory.
RUNTIME_MODE = 0o700
MOUNT_FILE_MODE = 0o444
PIN_DIRECTORY_MODE = 0o755


def openssl(*args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        return subprocess.run(["openssl", *args], input=input_bytes or b"", capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise ValueError("OpenSSL could not process G02 certificate material") from None


def generate_tls(days: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as work:
        root = Path(work)
        ca_key, ca_cert = root / "ca.key", root / "ca.crt"
        csr, ext = root / "leaf.csr", root / "leaf.cnf"
        for ca, leaves in TLS_GROUPS.items():
            ca_key.write_bytes(openssl("ecparam", "-genkey", "-name", "prime256v1", "-noout"))
            ca_cert.write_bytes(openssl(
                "req", "-new", "-x509", "-sha256", "-key", str(ca_key), "-subj", f"/CN=ai-res-dev-{ca}", "-days", days,
                "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                "-addext", "subjectKeyIdentifier=hash",
            ))
            values[ca] = ca_cert.read_text()
            for leaf in leaves:
                key = openssl("ecparam", "-genkey", "-name", "prime256v1", "-noout")
                csr.write_bytes(openssl("req", "-new", "-sha256", "-key", "/dev/stdin", "-subj", f"/CN={leaf.name}", input_bytes=key))
                ext.write_text(
                    "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
                    "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n"
                    f"subjectAltName={leaf.san}\nextendedKeyUsage={','.join(leaf.usages)}\n"
                )
                values[f"{leaf.name}_cert"] = openssl(
                    "x509", "-req", "-sha256", "-in", str(csr), "-CA", str(ca_cert), "-CAkey", str(ca_key),
                    "-set_serial", "0x" + secrets.token_hex(16), "-days", days, "-extfile", str(ext),
                ).decode()
                values[f"{leaf.name}_key"] = key.decode()
    return values


def _certificate(value: str) -> bytes:
    if not _PEM_CERTIFICATE.fullmatch(value):
        raise ValueError("G02 certificate files must contain exactly one PEM certificate")
    return value.encode()


def validate_tls(values: dict[str, str]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    used_keys: set[bytes] = set()
    with tempfile.TemporaryDirectory() as work:
        trust_anchor, certificate_file = Path(work) / "ca.crt", Path(work) / "leaf.crt"
        for ca, leaves in TLS_GROUPS.items():
            trust_anchor.write_bytes(_certificate(values[ca]))
            ca_key = openssl("x509", "-in", str(trust_anchor), "-pubkey", "-noout")
            if ca_key in used_keys:
                raise ValueError("G02 certificates must use separate keys")
            used_keys.add(ca_key)
            for leaf in leaves:
                certificate = _certificate(values[f"{leaf.name}_cert"])
                certificate_file.write_bytes(certificate)
                for usage in leaf.usages:
                    openssl("verify", "-x509_strict", "-check_ss_sig", "-trusted", str(trust_anchor), "-purpose", _PURPOSE[usage], str(certificate_file))
                public_key = openssl("x509", "-pubkey", "-noout", input_bytes=certificate)
                private_key = values[f"{leaf.name}_key"]
                if not _PEM_PRIVATE_KEY.fullmatch(private_key):
                    raise ValueError("G02 key files must contain exactly one EC private key")
                if public_key in used_keys or public_key != openssl("pkey", "-pubout", "-passin", "pass:", input_bytes=private_key.encode()):
                    raise ValueError("G02 certificate and key must match without sharing keys")
                used_keys.add(public_key)
                report = openssl("x509", "-text", "-noout", input_bytes=certificate).decode().splitlines()
                extensions = {line.strip(): report[index + 1].strip() for index, line in enumerate(report[:-1]) if line.strip().startswith("X509v3 ")}
                usages = extensions.get("X509v3 Extended Key Usage:", "").split(", ")
                if extensions.get("X509v3 Subject Alternative Name:") != leaf.san or set(usages) != {_EXTENDED_KEY_USAGE[u] for u in leaf.usages}:
                    raise ValueError("G02 certificate SAN or purpose does not match its service")
                if leaf.pin is not None:
                    der = openssl("x509", "-outform", "der", input_bytes=certificate)
                    fingerprints[f"{leaf.pin}.sha256"] = hashlib.sha256(der).hexdigest() + "\n"
    return fingerprints


def materialize(root: Path, values: dict[str, str], pins: dict[str, str], *, publish_pins: bool) -> None:
    if root.exists() or root.is_symlink():
        active = root / "active-certs"
        if (not _safe_mode(root, RUNTIME_MODE, stat.S_ISDIR) or not _safe_mode(active, PIN_DIRECTORY_MODE, stat.S_ISDIR)
                or {p.name for p in root.iterdir()} != set(values) | {"active-certs"}
                or any(not _matching_file(root / name, value) for name, value in values.items())
                or any(p.name not in pins or not _matching_file(p, pins[p.name]) for p in active.iterdir())):
            raise ValueError("existing G02 runtime material is incomplete or inconsistent")
        # Missing fingerprint files may reflect deliberate revocation. Keep them absent.
        return

    with tempfile.TemporaryDirectory(prefix=".g02-", dir=root.parent) as work:
        stage = Path(work) / "runtime"
        active = stage / "active-certs"
        stage.mkdir(mode=RUNTIME_MODE)
        stage.chmod(RUNTIME_MODE)
        active.mkdir(mode=PIN_DIRECTORY_MODE)
        active.chmod(PIN_DIRECTORY_MODE)
        for directory, content in ((stage, values), (active, pins if publish_pins else {})):
            for name, value in content.items():
                path = directory / name
                path.write_text(value)
                path.chmod(MOUNT_FILE_MODE)
        stage.rename(root)


def _matching_file(path: Path, value: str) -> bool:
    return _safe_mode(path, MOUNT_FILE_MODE, stat.S_ISREG) and path.read_bytes() == value.encode()


def _safe_mode(path: Path, mode: int, kind: Callable[[int], bool]) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return kind(info.st_mode) and stat.S_IMODE(info.st_mode) == mode and info.st_uid == os.getuid()
