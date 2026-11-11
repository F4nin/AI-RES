#!/usr/bin/env python3
"""Infrastructure policy checks over the *rendered* Compose model (`docker compose config --format json`, all profiles).

Enforces DOC-015 §9.2/§9.4/§11.5/§12.2/§17, Secrets §3/§4, THR-005/013/017 (S03). Fails (exit 1) on any violation, and on a model
that contains no services (a check that read nothing must not pass). Never prints environment values (only variable names).
Usage: check_compose.py [-f compose.yaml ...]   (default: compose.yaml)
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PUBLISHER = "reverse-proxy"  # the only service allowed to publish a host port (ADR-020)
PUBLISH_HOST_IP = "127.0.0.1"  # local profile; a different bind needs an owner decision
OPEN_NETWORKS = {"ingress", "egress"}  # the only networks with a gateway; membership is allowlisted per service below
INGRESS_ALLOWED = {"reverse-proxy", "frontend"}
EGRESS_ALLOWED = {"llm-gateway", "connector-platform"}  # DOC-015 §9.1: only controlled egress services (they do not exist yet)
DATA_ALLOWED = {"api", "postgres", "postgres-provision", "migrate", "temporal", "temporal-schema", "minio", "minio-init"}
MANAGER_WORKER_PREFIXES = ("manager-runtime", "worker-runtime")  # PERSIST-023: no network path to PostgreSQL
MANAGER_WORKER_NETWORKS = {"app", "workflow"}  # never data, admin, ingress or egress
ONE_SHOT = {"postgres-provision", "migrate", "temporal-schema", "temporal-namespace", "minio-init"}  # may omit healthcheck (restart: "no")
HEALTHCHECK_EXEMPT = {"otel-collector"}  # distroless image: no shell/HTTP client for an in-container probe; probed externally in S13
ADMIN_ONLY = {"temporal-ui"}  # Temporal Web UI / MinIO console: admin network only, never ingress
# Which Compose secrets each service may mount (Secrets §4: each service gets only what it needs). Unlisted service => no secrets.
SECRET_ALLOWED: dict[str, set[str]] = {
    "api": {"cursor_hmac_key"},
    "postgres": {"postgres_superuser_password", "postgres_tls_server_cert", "postgres_tls_server_key"},
    "postgres-provision": {"postgres_superuser_password", "temporal_db_password", "checkpointer_db_password", "postgres_tls_ca_cert",
                           "migrator_db_password", "api_db_password", "outbox_db_password", "consumer_db_password", "auditor_db_password",
                           "backup_db_password"},
    "migrate": {"migrator_db_password", "postgres_tls_ca_cert"},  # S04: only the migration identity; runtime role secrets arrive with their consumers
    "temporal-schema": {"temporal_db_password", "postgres_tls_ca_cert"},
    "temporal": {"temporal_db_password", "postgres_tls_ca_cert"},
    "minio": {"minio_root_user", "minio_root_password"},
    "minio-init": {"minio_root_user", "minio_root_password"},
}
SECRET_NAME = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|CREDENTIAL)", re.I)
CREDENTIAL_URL = re.compile(r"^[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@", re.I)
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")
SOCKET = re.compile(r"docker\.sock$")


def _tag(ref: str) -> str | None:
    name = DIGEST.sub("", ref)
    last = name.rsplit("/", 1)[-1]
    return last.split(":", 1)[1] if ":" in last else None


def _image_violations(where: str, ref: str, *, need_digest: bool = True) -> list[str]:
    out: list[str] = []
    tag = _tag(ref)
    if tag is None:
        out.append(f"{where}: image '{ref}' has no explicit tag")
    elif tag == "latest":
        out.append(f"{where}: image '{ref}' uses the 'latest' tag")
    if need_digest and not DIGEST.search(ref):
        out.append(f"{where}: image '{ref}' is not pinned by sha256 digest")
    return out


def check_dockerfile(name: str, lines: list[str]) -> list[str]:
    out: list[str] = []
    where = f"Dockerfile[{name}]"
    stages: set[str] = set()
    if not any(re.match(r"\s*FROM\s", ln, re.I) for ln in lines):
        return [f"{where}: missing, empty or without FROM (nothing was checked)"]
    for raw in lines:
        m = re.match(r"\s*FROM\s+(?:--\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", raw, re.I)
        if m:
            ref, alias = m.group(1), m.group(2)
            if ref.lower() not in stages and ref.lower() != "scratch":
                out += _image_violations(where, ref)
            if alias:
                stages.add(alias.lower())
            continue
        c = re.match(r"\s*COPY\s+(?:--\S+\s+)*?--from=(\S+)", raw, re.I)  # COPY --from=<image> pulls an unpinned image just like FROM
        if c and c.group(1).lower() not in stages and not c.group(1).isdigit():
            out += _image_violations(where + " COPY --from", c.group(1))
    return out


def _networks_of(svc: dict) -> set[str]:
    nets = svc.get("networks") or {}
    return set(nets if isinstance(nets, dict) else nets)


def _user_is_root(user: object) -> bool:
    if user in (None, ""):
        return True
    return str(user).split(":", 1)[0] in ("root", "0")


def _mounted_secrets(svc: dict) -> set[str]:
    out: set[str] = set()
    for s in svc.get("secrets") or []:
        out.add(str(s.get("source")) if isinstance(s, dict) else str(s))
    return out


def check_service(name: str, svc: dict, dockerfiles: dict[str, list[str]], base_dir: Path | None = None) -> list[str]:
    out: list[str] = []
    w = f"service '{name}'"
    if "build" in svc:
        if name not in dockerfiles:
            out.append(f"{w}: Dockerfile not provided for build")
        out += check_dockerfile(name, dockerfiles.get(name, []))
        if svc.get("image"):
            out += _image_violations(w, svc["image"], need_digest=False)
    elif svc.get("image"):
        out += _image_violations(w, svc["image"])
    else:
        out.append(f"{w}: neither image nor build")

    if _user_is_root(svc.get("user")):
        out.append(f"{w}: must run as a non-root user")
    if svc.get("read_only") is not True:
        out.append(f"{w}: read_only must be true")
    if "ALL" not in [str(c).upper() for c in svc.get("cap_drop") or []]:
        out.append(f"{w}: cap_drop must contain ALL")
    if svc.get("cap_add"):
        out.append(f"{w}: cap_add is not allowed")
    if "no-new-privileges:true" not in [str(s).lower().replace("=", ":") for s in svc.get("security_opt") or []]:
        out.append(f"{w}: security_opt must contain no-new-privileges:true")
    if svc.get("privileged"):
        out.append(f"{w}: privileged is not allowed")
    if svc.get("network_mode"):  # host, bridge, service:<x>, container:<x> all bypass the segmentation model
        out.append(f"{w}: network_mode is not allowed (networks must be declared explicitly)")
    for key in ("pid", "ipc", "userns_mode", "uts"):
        if str(svc.get(key, "")).lower() == "host" or str(svc.get(key, "")).lower().startswith(("service:", "container:")):
            out.append(f"{w}: {key}={svc[key]} is not allowed")
    for vol in svc.get("volumes") or []:
        is_bind = (vol.get("type") == "bind") if isinstance(vol, dict) else str(vol).startswith(("/", ".", "~"))
        src = str(vol.get("source", "")) if isinstance(vol, dict) else str(vol).split(":", 1)[0]
        if SOCKET.search(src):
            out.append(f"{w}: mounts docker.sock")
        elif is_bind and base_dir is not None:
            p = Path(src)
            if not (p.is_absolute() and (p == base_dir or base_dir in p.parents)):
                out.append(f"{w}: bind mount '{src}' is outside the project directory")
            elif (base_dir / "secrets") in (p, *p.parents):  # secrets are mounted only via the `secrets:` key, which SECRET_ALLOWED governs
                out.append(f"{w}: bind mount '{src}' exposes the secrets directory (use a Compose secret)")
    if not (svc.get("mem_limit") or ((svc.get("deploy") or {}).get("resources") or {}).get("limits", {}).get("memory")):
        out.append(f"{w}: mem_limit is required (value is WORKING, DOC-015 §9.4)")
    if not svc.get("pids_limit"):
        out.append(f"{w}: pids_limit is required")
    hc = svc.get("healthcheck")
    if hc and hc.get("disable"):
        out.append(f"{w}: healthcheck must not be disabled")
    elif not hc and name not in HEALTHCHECK_EXEMPT and not (name in ONE_SHOT and str(svc.get("restart", "")).lower() == "no"):
        out.append(f"{w}: healthcheck is required (only declared one-shot jobs with restart: 'no' may omit it)")

    for key, value in (svc.get("environment") or {}).items():
        if SECRET_NAME.search(key):
            if not key.endswith("_FILE"):
                out.append(f"{w}: environment variable {key} looks like a secret; use a Compose secret and a *_FILE pointer")
            elif not str(value).startswith("/run/secrets/"):
                out.append(f"{w}: {key} must point to a Compose secret under /run/secrets/ (not a literal value)")
        elif isinstance(value, str) and CREDENTIAL_URL.match(value):
            out.append(f"{w}: environment variable {key} embeds credentials in a URL")

    extra = _mounted_secrets(svc) - SECRET_ALLOWED.get(name, set())
    if extra:
        out.append(f"{w}: mounts secrets it is not allowed to have: {', '.join(sorted(extra))}")

    if "networks" not in svc or not svc["networks"]:
        out.append(f"{w}: must declare networks explicitly")
    nets = _networks_of(svc)
    if name in ADMIN_ONLY and nets - {"admin"}:
        out.append(f"{w}: admin-only service must be on the admin network only")
    if "admin" in nets and "ingress" in nets:
        out.append(f"{w}: admin and ingress networks must not be combined")
    if "ingress" in nets and name not in INGRESS_ALLOWED:
        out.append(f"{w}: not allowed on the ingress network")
    if "egress" in nets and name not in EGRESS_ALLOWED:
        out.append(f"{w}: not allowed on the egress network (only LLM Gateway / Connector Platform)")
    if "data" in nets and nets & {"ingress", "egress"}:
        out.append(f"{w}: data network must not be combined with ingress/egress")
    if name == PUBLISHER and nets & {"data", "admin"}:
        out.append(f"{w}: reverse-proxy must not join data/admin networks")
    if name.startswith(MANAGER_WORKER_PREFIXES):
        bad = nets - MANAGER_WORKER_NETWORKS
        if bad:
            out.append(f"{w}: Manager/Worker Runtime may join only {sorted(MANAGER_WORKER_NETWORKS)}, not {sorted(bad)} (PERSIST-023)")
    elif "data" in nets and name not in DATA_ALLOWED:
        out.append(f"{w}: not allowlisted for the data network")
    return out


def check_ports(model: dict) -> list[str]:
    out: list[str] = []
    for name, svc in model["services"].items():
        for p in svc.get("ports") or []:
            if name != PUBLISHER:
                out.append(f"service '{name}': must not publish host ports (only {PUBLISHER} may)")
            elif p.get("host_ip") != PUBLISH_HOST_IP:
                out.append(f"service '{name}': published port must bind {PUBLISH_HOST_IP} explicitly")
    return out


def check_networks(model: dict) -> list[str]:
    nets = model.get("networks") or {}
    # every network except the two named non-internal ones must be internal, so a new custom network cannot grant internet egress
    msg = "network '{}': must be internal (no gateway, egress deny-by-default, THR-005)"
    return [msg.format(n) for n, d in nets.items() if n not in OPEN_NETWORKS and not (d or {}).get("internal")]


def check_model(model: dict, dockerfiles: dict[str, list[str]], base_dir: Path | None = None) -> list[str]:
    if not model.get("services"):
        return ["model has no services: nothing was checked"]
    out = check_ports(model) + check_networks(model)
    for name, svc in model["services"].items():
        out += check_service(name, svc, dockerfiles, base_dir)
    return out


def load_model(files: list[str], cwd: Path) -> dict:
    cmd = ["docker", "compose", "--profile", "*", *[a for f in files for a in ("-f", f)], "config", "--format", "json"]
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    if res.returncode != 0:
        raise SystemExit(f"docker compose config failed:\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def gather_dockerfiles(model: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, svc in model["services"].items():
        build = svc.get("build")
        if build:
            df = Path(build["context"]) / build.get("dockerfile", "Dockerfile")
            out[name] = df.read_text().splitlines() if df.is_file() else []
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-f", dest="files", action="append")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent))
    args = ap.parse_args(argv)
    os.environ.setdefault("COMPOSE_PROJECT_NAME", "ai-res")
    base = Path(args.dir).resolve()
    model = load_model(args.files or ["compose.yaml"], base)
    violations = check_model(model, gather_dockerfiles(model), base)
    for v in violations:
        print(f"VIOLATION: {v}")
    print(f"{len(model.get('services', {}))} services checked, {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
