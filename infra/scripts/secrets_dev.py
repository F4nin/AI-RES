#!/usr/bin/env python3
"""Dev secrets for the local stack (S03; Secrets & Key Management §3, DOC-015 §11.4, ADR-045).

`init`   : creates the age key (outside the repo) if no encrypted file exists yet, generates random secrets + a local PostgreSQL TLS
           CA/server certificate once, encrypts them with SOPS+age into infra/secrets/encrypted/local.enc.yaml (PER-MACHINE, git-ignored:
           it is encrypted to this machine's age key), and materialises them in infra/secrets/runtime/ (git-ignored, 0600/dir 0700).
           Existing encrypted secrets are NEVER regenerated or overwritten. If the encrypted file exists but cannot be decrypted with the
           current age key, it fails with an explanation instead of silently minting a new key.
`decrypt`: re-creates infra/secrets/runtime/ from the encrypted file.
`clean`  : removes infra/secrets/runtime/ (the encrypted file and the age key are kept).
`init-g02`: prepares the optional protected G02 transport after `init`. Its separate encrypted bundle and
           material under infra/secrets/g02 are kept across runs, including individual client revocations.
           Recovering a deleted G02 runtime directory leaves all client pins inactive.
No default credentials: every value is random per machine. Values are never printed.
"""
import argparse
import base64
import fcntl
import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from . import g02_credentials
else:
    import g02_credentials

INFRA = Path(__file__).resolve().parent.parent
ENCRYPTED = INFRA / "secrets" / "encrypted" / "local.enc.yaml"
RUNTIME = INFRA / "secrets" / "runtime"
G02_ENCRYPTED = INFRA / "secrets" / "g02.enc.yaml"
G02_RUNTIME = INFRA / "secrets" / "g02"
AGE_KEY = Path(os.environ.get("AI_RES_AGE_KEY_FILE", Path.home() / ".config" / "ai-res" / "age" / "keys.txt"))
# CI only: Linux bind mounts keep host permissions while the containers run as several non-root uids, so an ephemeral runner needs
# world-readable files. Guarded: it is refused outside CI (GITHUB_ACTIONS/CI) so a developer machine cannot weaken permissions by accident.
WORLD_READABLE = os.environ.get("AI_RES_SECRETS_WORLD_READABLE") == "1"
if WORLD_READABLE and not (os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"):
    raise SystemExit("AI_RES_SECRETS_WORLD_READABLE=1 is only allowed in CI (GITHUB_ACTIONS/CI must be set)")
FILE_MODE, DIR_MODE = (0o644, 0o755) if WORLD_READABLE else (0o600, 0o700)
# S04: one password per PostgreSQL login identity (ADR-015); the secret files are mounted only into the services that need them
DOMAIN_DB_PASSWORDS = [
    "migrator_db_password", "api_db_password", "platform_api_db_password", "outbox_db_password",
    "consumer_db_password", "auditor_db_password", "backup_db_password",
]
# S07: mfa_encryption_key = base64 of 32 random bytes (AES-256-GCM key for TOTP seeds);
# bootstrap_secret = one-time first-administrator secret (never mounted into the API);
# S11: manager_signing_key = base64 of a 32-byte Ed25519 seed (service token signing key of the Manager Runtime, mounted ONLY there);
# service_public_keys = `<SERVICE_NAME> <base64 public key>` lines derived from it (public registry of the internal Platform API verifier)
# S09: idempotency_keyring = one line `<key_id> <base64 of 32 bytes>` (HMAC key ring of the API, ADR-024)
PASSWORDS = ["postgres_superuser_password", "temporal_db_password", "checkpointer_db_password", "minio_root_password", "cursor_hmac_key", *DOMAIN_DB_PASSWORDS,
             "mfa_encryption_key", "bootstrap_secret", "idempotency_keyring", "manager_signing_key", "service_public_keys", "outbox_delivery_signing_key",
             "grafana_admin_password", "bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth"]
# S16: gateway-only dev identities, not provider keys. Hex is safe to render into the ephemeral Bifrost JSON with shell builtins.
LLM_POC_CREDENTIALS = {"bifrost_admin_password", "bifrost_virtual_key", "llm_relay_auth"}
TLS = ["postgres_tls_ca_cert", "postgres_tls_server_cert", "postgres_tls_server_key"]
NAMES = [*PASSWORDS[:3], "minio_root_user", *PASSWORDS[3:], "assigned_delivery_public_keys", *TLS]
TLS_DAYS = "825"  # local dev certificate lifetime (WORKING)


_PKCS8_ED25519_PREFIX = bytes.fromhex("302e020100300506032b657004220420")
_SPKI_ED25519_PREFIX = bytes.fromhex("302a300506032b6570032100")
SERVICE_KEYS = {"MANAGER_RUNTIME": "manager_signing_key"}
ASSIGNED_DELIVERY_KEYS = {"OUTBOX_DISPATCHER": "outbox_delivery_signing_key"}
G02_PLATFORM_KEYS = {"MANAGER_RUNTIME": "g02_manager_signing_key", "TEMPORAL_AUTH_CONTROL": "temporal_auth_control_signing_key"}
G02_NAMES = g02_credentials.TLS_NAMES | set(G02_PLATFORM_KEYS.values()) | {"g02_platform_public_keys"}
# Copy only the base secrets mounted by the G02 transport and its provisioning jobs. The
# encrypted base bundle remains their source, and the local base runtime files keep their modes.
G02_BASE_NAMES = frozenset({
    "postgres_superuser_password", "temporal_db_password", "checkpointer_db_password", "migrator_db_password",
    "api_db_password", "platform_api_db_password", "outbox_db_password", "consumer_db_password", "auditor_db_password",
    "backup_db_password", "postgres_tls_ca_cert", "postgres_tls_server_cert", "postgres_tls_server_key",
    "cursor_hmac_key", "mfa_encryption_key", "idempotency_keyring", "outbox_delivery_signing_key", "assigned_delivery_public_keys",
})


def ed25519_public_b64(seed_b64: str) -> str:
    """Raw Ed25519 public key (base64) of a base64 32-byte seed, through openssl (the infra checks have no Python crypto dependency)."""
    seed = base64.b64decode(seed_b64, validate=True)
    if len(seed) != 32:
        raise ValueError("an Ed25519 seed is 32 bytes")
    try:
        result = subprocess.run(["openssl", "pkey", "-inform", "DER", "-pubout", "-outform", "DER"],  # noqa: S603
                                input=_PKCS8_ED25519_PREFIX + seed, capture_output=True, check=False)
    except OSError:
        raise RuntimeError("OpenSSL with Ed25519 support is required on PATH") from None
    if result.returncode != 0:
        raise RuntimeError("OpenSSL with Ed25519 support is required on PATH")
    der = result.stdout
    if len(der) != len(_SPKI_ED25519_PREFIX) + 32 or not der.startswith(_SPKI_ED25519_PREFIX):
        raise RuntimeError("OpenSSL returned an invalid Ed25519 public key")
    return base64.b64encode(der[len(_SPKI_ED25519_PREFIX):]).decode()


def derive_service_public_keys(values: dict[str, str]) -> str:
    return "".join(f"{service} {ed25519_public_b64(values[secret])}\n" for service, secret in SERVICE_KEYS.items())


def derive_assigned_delivery_public_keys(values: dict[str, str]) -> str:
    """Public verification material for the private assigned-delivery listener only."""
    return "".join(f"{service} {ed25519_public_b64(values[secret])}\n" for service, secret in ASSIGNED_DELIVERY_KEYS.items())


def merge_missing_secrets(existing: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Add new dev secrets without rotating identities or accepting a mismatched delivery keypair."""
    signer, registry = "outbox_delivery_signing_key", "assigned_delivery_public_keys"
    if existing.get(registry) and not existing.get(signer):
        raise SystemExit("assigned delivery public keys exist without their signing seed; restore the matching seed before updating dev secrets")
    added = [name for name in NAMES if not existing.get(name) and name not in TLS]
    merged = {**existing, **{
        name: _generate(name) for name in added if name not in {"service_public_keys", registry}
    }}
    if "service_public_keys" in added:
        merged["service_public_keys"] = derive_service_public_keys(merged)
    if not merged.get(registry) and merged.get(signer):
        merged[registry] = derive_assigned_delivery_public_keys(merged)
    elif merged.get(registry) and merged.get(signer):
        expected = tuple(derive_assigned_delivery_public_keys(merged).split())
        records = {tuple(line.split()) for line in merged[registry].splitlines() if line.split()}
        if expected not in records:
            raise SystemExit("assigned delivery public keys do not contain the public key for the configured signing seed")
    return merged, added


def _generate(name: str) -> str:
    if name in LLM_POC_CREDENTIALS:
        return secrets.token_hex(32)
    if name in (*SERVICE_KEYS.values(), *ASSIGNED_DELIVERY_KEYS.values()):
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
        _run(["openssl", "req", "-x509", "-new", "-sha256", "-key", str(t / "ca.key"), "-subj", "/CN=ai-res-local-ca",
              "-days", TLS_DAYS, "-out", str(t / "ca.crt"), "-addext", "basicConstraints=critical,CA:TRUE",
              "-addext", "keyUsage=critical,keyCertSign,cRLSign"])
        _run(["openssl", "req", "-new", "-sha256", "-key", str(t / "srv.key"), "-subj", "/CN=postgres", "-out", str(t / "srv.csr")])
        _run(["openssl", "x509", "-req", "-sha256", "-in", str(t / "srv.csr"), "-CA", str(t / "ca.crt"), "-CAkey", str(t / "ca.key"), "-CAcreateserial",
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


def _encrypt(values: dict[str, str], recipient: str, *, path: Path | None = None) -> None:
    path = ENCRYPTED if path is None else path
    res = subprocess.run(  # noqa: S603
        ["sops", "--encrypt", "--age", recipient, "--input-type", "json", "--output-type", "yaml", "--filename-override", str(path), "/dev/stdin"],  # noqa: S607
        input=json.dumps(values), capture_output=True, text=True, check=True,
    )
    if path != ENCRYPTED:
        with tempfile.TemporaryDirectory(prefix=".g02-encrypt-", dir=path.parent) as work:
            tmp = Path(work) / "bundle"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as fh:
                fh.write(res.stdout)
            os.link(tmp, path)
        return
    # Atomic replace: a crash between truncate and write must never leave an empty/corrupt file (it holds every dev secret incl. the TLS CA).
    if path.exists():
        shutil.copy2(path, path.with_suffix(".yaml.bak"))  # one-step-back copy, same git-ignored directory and permissions
    tmp = path.with_suffix(".yaml.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(res.stdout)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _decrypt_raw(*, path: Path | None = None) -> dict[str, str]:
    path = ENCRYPTED if path is None else path
    try:
        out = _run(["sops", "--decrypt", "--input-type", "yaml", "--output-type", "json", str(path)]).stdout
    except subprocess.CalledProcessError as exc:
        if path != ENCRYPTED:
            raise SystemExit(f"cannot decrypt {path.name} with the configured age key (sops exit {exc.returncode})") from None
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
        merged, added = merge_missing_secrets(existing)
        if any(not existing.get(n) for n in TLS):
            raise SystemExit("the TLS material is missing from the encrypted file (remove it to regenerate; databases keep old passwords)")
        if added:  # new secret names introduced by a later stage: add ONLY the missing ones, never touch existing values
            _encrypt(merged, recipient)
            print(f"added {len(added)} new secret(s) to {ENCRYPTED.name}: {', '.join(added)}; existing values were kept")
        else:
            print("encrypted secrets already exist: keeping them (no regeneration)")
    else:
        ENCRYPTED.parent.mkdir(parents=True, exist_ok=True)
        fresh = {n: _generate(n) for n in NAMES if n not in TLS and n not in {"service_public_keys", "assigned_delivery_public_keys"}}
        _encrypt({**fresh, "service_public_keys": derive_service_public_keys(fresh),
                  "assigned_delivery_public_keys": derive_assigned_delivery_public_keys(fresh), **generate_tls()}, recipient)
        print(f"encrypted secrets written to {ENCRYPTED.relative_to(INFRA.parent)}")
    write_runtime(decrypt())


def _g02_platform_registry(values: dict[str, str]) -> str:
    for seed in G02_PLATFORM_KEYS.values():
        if base64.b64encode(base64.b64decode(values[seed], validate=True)).decode() != values[seed]:
            raise ValueError("invalid G02 signing seed encoding")
    public_keys = {service: ed25519_public_b64(values[seed]) for service, seed in G02_PLATFORM_KEYS.items()}
    if len(set(public_keys.values())) != len(G02_PLATFORM_KEYS):
        raise ValueError("G02 Platform signers must have different keys")
    return "".join(f"{service} {public}\n" for service, public in public_keys.items())


def _trusted_g02_file(info: os.stat_result) -> bool:
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid() and info.st_nlink == 1


def init_g02() -> None:
    if not ENCRYPTED.is_file():
        raise SystemExit("the local stack secrets must be initialized before init-g02")
    recipient = ensure_age_key(create=False)
    lock = G02_ENCRYPTED.with_suffix(".lock")
    try:
        parent = G02_ENCRYPTED.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != os.getuid() or parent.st_mode & 0o022:
            raise ValueError("the G02 secret directory must be controlled by the invoking user")
        with os.fdopen(os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600), "r+b") as guard:
            if not _trusted_g02_file(os.fstat(guard.fileno())):
                raise ValueError("the G02 lock must be a private regular file")
            fcntl.flock(guard, fcntl.LOCK_EX)
            base = decrypt()
            if any(not base.get(name) for name in G02_BASE_NAMES):
                raise ValueError("the base bundle is missing G02 transport material")
            signer, registry = ASSIGNED_DELIVERY_KEYS["OUTBOX_DISPATCHER"], "assigned_delivery_public_keys"
            records = [line.split() for line in base[registry].splitlines() if line.split()]
            if (records != [derive_assigned_delivery_public_keys(base).split()]
                    or base64.b64encode(base64.b64decode(base[signer], validate=True)).decode() != base[signer]):
                raise ValueError("the base assigned-delivery registry must contain only the matching Dispatcher key")

            try:
                bundle = G02_ENCRYPTED.lstat()
            except FileNotFoundError:
                bundle = None
            if bundle is not None and not _trusted_g02_file(bundle):
                raise ValueError("the encrypted G02 bundle must be a private regular file")
            fresh = bundle is None
            if fresh and (G02_RUNTIME.exists() or G02_RUNTIME.is_symlink()):
                raise ValueError("G02 runtime material exists without its encrypted bundle")
            if fresh:
                values = g02_credentials.generate_tls(TLS_DAYS)
                values.update({name: base64.b64encode(secrets.token_bytes(32)).decode() for name in G02_PLATFORM_KEYS.values()})
                values["g02_platform_public_keys"] = _g02_platform_registry(values)
            else:
                values = _decrypt_raw(path=G02_ENCRYPTED)
            if set(values) != G02_NAMES or any(not value for value in values.values()):
                raise ValueError("the encrypted G02 bundle is incomplete")
            if values["g02_platform_public_keys"] != _g02_platform_registry(values):
                raise ValueError("the G02 Platform registry does not match its signing keys")
            if len({base[signer], *(values[name] for name in G02_PLATFORM_KEYS.values())}) != 3:
                raise ValueError("G02 Dispatcher, Manager and Temporal signers must have different keys")
            pins = g02_credentials.validate_tls(values)

            if fresh:
                _encrypt(values, recipient, path=G02_ENCRYPTED)
            runtime = {**values, **{name: base[name] for name in G02_BASE_NAMES}}
            g02_credentials.materialize(G02_RUNTIME, runtime, pins, publish_pins=fresh)
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError):
        # A third-party parser's error text may contain credential contents.
        raise SystemExit("could not prepare G02 credentials; check tools, encrypted bundles and runtime material") from None
    print("G02 development credentials are ready in infra/secrets/g02")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["init", "decrypt", "clean", "init-g02"])
    cmd = ap.parse_args().command
    if cmd == "init":
        init()
    elif cmd == "decrypt":
        ensure_age_key(create=False)
        write_runtime(decrypt())
    elif cmd == "init-g02":
        init_g02()
    else:
        shutil.rmtree(RUNTIME, ignore_errors=True)
        if RUNTIME.exists():
            raise SystemExit(f"could not remove {RUNTIME}")
        print("runtime secrets removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
