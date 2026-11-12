#!/usr/bin/env python3
"""Dev secrets for the local stack (S03; Secrets & Key Management §3, DOC-015 §11.4, ADR-045).

`init`   : creates the age key (outside the repo) if no encrypted file exists yet, generates random secrets + a local PostgreSQL TLS
           CA/server certificate once, encrypts them with SOPS+age into infra/secrets/encrypted/local.enc.yaml (PER-MACHINE, git-ignored:
           it is encrypted to this machine's age key), and materialises them in infra/secrets/runtime/ (git-ignored, 0600/dir 0700).
           Existing encrypted secrets are NEVER regenerated or overwritten. If the encrypted file exists but cannot be decrypted with the
           current age key, it fails with an explanation instead of silently minting a new key.
`decrypt`: re-creates infra/secrets/runtime/ from the encrypted file.
`clean`  : removes infra/secrets/runtime/ (the encrypted file and the age key are kept).
No default credentials: every value is random per machine. Values are never printed.
"""
import argparse
import base64
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

INFRA = Path(__file__).resolve().parent.parent
ENCRYPTED = INFRA / "secrets" / "encrypted" / "local.enc.yaml"
RUNTIME = INFRA / "secrets" / "runtime"
AGE_KEY = Path(os.environ.get("AI_RES_AGE_KEY_FILE", Path.home() / ".config" / "ai-res" / "age" / "keys.txt"))
# CI only: Linux bind mounts keep host permissions while the containers run as several non-root uids, so an ephemeral runner needs
# world-readable files. Guarded: it is refused outside CI (GITHUB_ACTIONS/CI) so a developer machine cannot weaken permissions by accident.
WORLD_READABLE = os.environ.get("AI_RES_SECRETS_WORLD_READABLE") == "1"
if WORLD_READABLE and not (os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"):
    raise SystemExit("AI_RES_SECRETS_WORLD_READABLE=1 is only allowed in CI (GITHUB_ACTIONS/CI must be set)")
FILE_MODE, DIR_MODE = (0o644, 0o755) if WORLD_READABLE else (0o600, 0o700)
# S04: one password per PostgreSQL login identity (ADR-015); the secret files are mounted only into the services that need them
DOMAIN_DB_PASSWORDS = [
    "migrator_db_password", "api_db_password", "outbox_db_password", "consumer_db_password", "auditor_db_password", "backup_db_password",
]
# S07: mfa_encryption_key = base64 of 32 random bytes (AES-256-GCM key for TOTP seeds);
# bootstrap_secret = one-time first-administrator secret (never mounted into the API);
# S11: manager_signing_key = base64 of a 32-byte Ed25519 seed (service token signing key of the Manager Runtime, mounted ONLY there);
# service_public_keys = `<SERVICE_NAME> <base64 public key>` lines derived from it (public registry of the internal Platform API verifier)
# S09: idempotency_keyring = one line `<key_id> <base64 of 32 bytes>` (HMAC key ring of the API, ADR-024)
PASSWORDS = ["postgres_superuser_password", "temporal_db_password", "checkpointer_db_password", "minio_root_password", "cursor_hmac_key", *DOMAIN_DB_PASSWORDS,
             "mfa_encryption_key", "bootstrap_secret", "idempotency_keyring", "manager_signing_key", "service_public_keys",
             "grafana_admin_password"]  # S13: random per machine; mounted only into grafana
TLS = ["postgres_tls_ca_cert", "postgres_tls_server_cert", "postgres_tls_server_key"]
NAMES = [*PASSWORDS[:3], "minio_root_user", *PASSWORDS[3:], *TLS]
TLS_DAYS = "825"  # local dev certificate lifetime (WORKING)


_PKCS8_ED25519_PREFIX = bytes.fromhex("302e020100300506032b657004220420")
SERVICE_KEYS = {"MANAGER_RUNTIME": "manager_signing_key"}


def ed25519_public_b64(seed_b64: str) -> str:
    """Raw Ed25519 public key (base64) of a base64 32-byte seed, through openssl (the infra checks have no Python crypto dependency)."""
    seed = base64.b64decode(seed_b64, validate=True)
    if len(seed) != 32:
        raise ValueError("an Ed25519 seed is 32 bytes")
    der = subprocess.run(["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"], input=_PKCS8_ED25519_PREFIX + seed,  # noqa: S603
                         capture_output=True, check=True).stdout
    return base64.b64encode(der[-32:]).decode()


def derive_service_public_keys(values: dict[str, str]) -> str:
    return "".join(f"{service} {ed25519_public_b64(values[secret])}\n" for service, secret in SERVICE_KEYS.items())


def _generate(name: str) -> str:
    if name in SERVICE_KEYS.values():
        return base64.b64encode(secrets.token_bytes(32)).decode()
    if name == "minio_root_user":
        return "aires-" + secrets.token_hex(6)
    if name == "mfa_encryption_key":
        return base64.b64encode(secrets.token_bytes(32)).decode()
    if name == "idempotency_keyring":
        return "k1 " + base64.b64encode(secrets.token_bytes(32)).decode()
    return secrets.token_urlsafe(48)  # >= 64 chars, URL-safe: no quoting problems in psql/URLs; cursor key >= 32 bytes (platform.config)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env={**os.environ, "SOPS_AGE_KEY_FILE": str(AGE_KEY)}, **kw)  # noqa: S603


def generate_tls() -> dict[str, str]:
    """Local CA (key discarded after signing) + a server certificate for host `postgres` (ECDSA P-256)."""
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        ext = t / "ext.cnf"
        ext.write_text("subjectAltName=DNS:postgres,DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth\n")
        for key in ("ca.key", "srv.key"):
            (t / key).write_text(_run(["openssl", "ecparam", "-genkey", "-name", "prime256v1", "-noout"]).stdout)
        _run(["openssl", "req", "-x509", "-new", "-key", str(t / "ca.key"), "-subj", "/CN=ai-res-local-ca", "-days", TLS_DAYS, "-out", str(t / "ca.crt"),
              "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
        _run(["openssl", "req", "-new", "-key", str(t / "srv.key"), "-subj", "/CN=postgres", "-out", str(t / "srv.csr")])
        _run(["openssl", "x509", "-req", "-in", str(t / "srv.csr"), "-CA", str(t / "ca.crt"), "-CAkey", str(t / "ca.key"), "-CAcreateserial",
              "-days", TLS_DAYS, "-extfile", str(ext), "-out", str(t / "srv.crt")])
        return {"postgres_tls_ca_cert": (t / "ca.crt").read_text(), "postgres_tls_server_cert": (t / "srv.crt").read_text(),
                "postgres_tls_server_key": (t / "srv.key").read_text()}


def ensure_age_key(*, create: bool) -> str:
    if not AGE_KEY.exists():
        if not create:
            raise SystemExit(
                f"age key {AGE_KEY} not found but {ENCRYPTED.name} exists: it was encrypted to another machine's key. "
                "Remove it (dev secrets are per-machine: `rm infra/secrets/encrypted/local.enc.yaml`, then `make down` to reset volumes) "
                "or restore the key (AI_RES_AGE_KEY_FILE)."
            )
        AGE_KEY.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _run(["age-keygen", "-o", str(AGE_KEY)])
        AGE_KEY.chmod(0o600)
        print(f"created age key at {AGE_KEY} (back it up separately; it is NOT in the repository)")
    mode = stat.S_IMODE(AGE_KEY.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f"{AGE_KEY} must not be accessible by group/others (mode {oct(mode)})")
    return _run(["age-keygen", "-y", str(AGE_KEY)]).stdout.strip()


def write_runtime(values: dict[str, str]) -> None:
    """Idempotent: unchanged files are left untouched and changed ones are rewritten in place (same inode), because replacing the
    directory/files breaks the bind mounts of running containers (found while testing `make up` twice)."""
    RUNTIME.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    RUNTIME.chmod(DIR_MODE)
    for stale in RUNTIME.iterdir():
        if stale.name not in NAMES:
            stale.unlink()
    changed = 0
    for name in NAMES:
        p = RUNTIME / name
        if p.exists() and p.read_text() == values[name]:
            p.chmod(FILE_MODE)
            continue
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w") as fh:
            fh.write(values[name])  # no trailing newline for generated passwords; PEM files keep theirs
        p.chmod(FILE_MODE)
        changed += 1
    print(f"{len(NAMES)} secret files in {RUNTIME.relative_to(INFRA.parent)} ({changed} written)")


def _encrypt(values: dict[str, str], recipient: str) -> None:
    res = subprocess.run(  # noqa: S603
        ["sops", "--encrypt", "--age", recipient, "--input-type", "json", "--output-type", "yaml", "--filename-override", str(ENCRYPTED), "/dev/stdin"],  # noqa: S607
        input=json.dumps(values), capture_output=True, text=True, check=True,
    )
    # Atomic replace: a crash between truncate and write must never leave an empty/corrupt file (it holds every dev secret incl. the TLS CA).
    if ENCRYPTED.exists():
        shutil.copy2(ENCRYPTED, ENCRYPTED.with_suffix(".yaml.bak"))  # one-step-back copy, same git-ignored directory and permissions
    tmp = ENCRYPTED.with_suffix(".yaml.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(res.stdout)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ENCRYPTED)


def _decrypt_raw() -> dict[str, str]:
    try:
        out = _run(["sops", "--decrypt", "--input-type", "yaml", "--output-type", "json", str(ENCRYPTED)]).stdout
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"cannot decrypt {ENCRYPTED.name} with {AGE_KEY} (sops exit {exc.returncode}). The file is per-machine; remove it to regenerate "
            "(then `make down`: databases keep the old passwords)."
        ) from None
    return {k: str(v) for k, v in json.loads(out).items()}


def decrypt() -> dict[str, str]:
    data = _decrypt_raw()
    missing = [n for n in NAMES if not data.get(n)]
    if missing:
        raise SystemExit(f"encrypted file lacks: {', '.join(missing)} (run `make secrets-dev` to add them; existing values are kept)")
    return {n: data[n] for n in NAMES}


def init() -> None:
    recipient = ensure_age_key(create=not ENCRYPTED.exists())
    if ENCRYPTED.exists():
        existing = _decrypt_raw()
        added = [n for n in NAMES if not existing.get(n) and n not in TLS]
        if any(not existing.get(n) for n in TLS):
            raise SystemExit("the TLS material is missing from the encrypted file (remove it to regenerate; databases keep old passwords)")
        if added:  # new secret names introduced by a later stage: add ONLY the missing ones, never touch existing values
            merged = {**existing, **{n: _generate(n) for n in added if n != "service_public_keys"}}
            if "service_public_keys" in added:
                merged["service_public_keys"] = derive_service_public_keys(merged)
            _encrypt(merged, recipient)
            print(f"added {len(added)} new secret(s) to {ENCRYPTED.name}: {', '.join(added)}; existing values were kept")
        else:
            print("encrypted secrets already exist: keeping them (no regeneration)")
    else:
        ENCRYPTED.parent.mkdir(parents=True, exist_ok=True)
        fresh = {n: _generate(n) for n in NAMES if n not in TLS and n != "service_public_keys"}
        _encrypt({**fresh, "service_public_keys": derive_service_public_keys(fresh), **generate_tls()}, recipient)
        print(f"encrypted secrets written to {ENCRYPTED.relative_to(INFRA.parent)}")
    write_runtime(decrypt())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["init", "decrypt", "clean"])
    cmd = ap.parse_args().command
    if cmd == "init":
        init()
    elif cmd == "decrypt":
        ensure_age_key(create=False)
        write_runtime(decrypt())
    else:
        shutil.rmtree(RUNTIME, ignore_errors=True)
        if RUNTIME.exists():
            raise SystemExit(f"could not remove {RUNTIME}")
        print("runtime secrets removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
