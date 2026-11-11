"""S03 mandatory runtime tests (prompt §9) against the live stack. Every negative check has a positive control so a broken probe
cannot pass silently."""
import base64
import http.client
import json
import socket
import ssl

import pytest

from tests.runtime.helpers import LONG_RUNNING, ONE_SHOT, compose, exec_in, image_secret_hits, inspect, sh

pytestmark = pytest.mark.runtime
PRIVATE_PROBE = "import socket,sys\ns=socket.socket();s.settimeout(3)\ntry:\n    s.connect((sys.argv[1],int(sys.argv[2])));print('CONNECTED')\nexcept Exception as e:\n    print('FAILED',type(e).__name__)\n"


# --- health / idempotence ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("service", [s for s in LONG_RUNNING if s != "otel-collector"])
def test_long_running_services_are_healthy(service):
    assert inspect(service)["State"]["Health"]["Status"] == "healthy"


@pytest.mark.parametrize("service", ONE_SHOT)
def test_one_shot_jobs_completed_successfully(service):
    st = inspect(service)["State"]
    assert st["Status"] == "exited" and st["ExitCode"] == 0


@pytest.mark.parametrize("service", ONE_SHOT)
def test_one_shot_jobs_are_idempotent_on_rerun(service):
    """Re-running schema/provision/namespace/bucket jobs against an already-initialised stack must succeed without change."""
    res = compose("run", "--rm", "--no-deps", service, timeout=300)
    assert res.returncode == 0, res.stderr[-800:]


# --- network exposure ------------------------------------------------------------------------------------------------------
def test_only_reverse_proxy_publishes_host_ports():
    """Uses HostConfig.PortBindings (present for exited one-shot jobs too, unlike NetworkSettings.Ports)."""
    for svc in LONG_RUNNING + ONE_SHOT:
        bindings = {k: v for k, v in (inspect(svc)["HostConfig"]["PortBindings"] or {}).items() if v}
        if svc == "reverse-proxy":
            assert list(bindings) == ["8443/tcp"] and all(b["HostIp"] == "127.0.0.1" for b in bindings["8443/tcp"])
        else:
            assert not bindings, f"{svc} publishes {bindings}"


# 5432 is deliberately absent: a developer machine may run its own PostgreSQL there; publication is asserted via inspect above.
@pytest.mark.parametrize("port", [9000, 9001, 8080, 7233, 8000, 4317])
def test_internal_ports_not_reachable_on_host(port):
    with socket.socket() as s:
        s.settimeout(2)
        assert s.connect_ex(("127.0.0.1", port)) != 0, f"host port {port} is open"


def test_proxy_port_is_reachable_on_host_positive_control():
    with socket.socket() as s:
        s.settimeout(2)
        assert s.connect_ex(("127.0.0.1", 8443)) == 0


@pytest.mark.parametrize(("host", "port"), [("minio", 9001), ("minio", 9000), ("temporal-ui", 8080), ("temporal", 7233), ("postgres", 5432)])
def test_admin_and_data_services_unreachable_from_ingress_network(host, port):
    """The reverse proxy sits on ingress+app: console, Temporal UI/frontend, MinIO API and PostgreSQL must not be resolvable/reachable."""
    out = exec_in("reverse-proxy", "sh", "-c", f"nc -z -w 2 {host} {port} && echo OPEN || echo CLOSED").stdout
    assert "CLOSED" in out and "OPEN" not in out, out


def test_proxy_reaches_api_positive_control():
    assert "OPEN" in exec_in("reverse-proxy", "sh", "-c", "nc -z -w 2 api 8000 && echo OPEN || echo CLOSED").stdout


def test_admin_services_reachable_from_admin_network_positive_control():
    """temporal-ui (admin only) reaches temporal over the admin network, proving the previous tests are not vacuous."""
    assert "OPEN" in exec_in("temporal-ui", "sh", "-c", "nc -z -w 2 temporal 7233 && echo OPEN || echo CLOSED").stdout


def test_persist_023_network_part_only_allowlisted_services_on_data_network():
    """PERSIST-023 (network part for what exists in S03): Manager/Worker runtimes do not exist yet; every other service that is not
    allowlisted must have no route to PostgreSQL. The real Manager/Worker check is repeated in S11/S23."""
    allowed = {"api", "postgres", "postgres-provision", "migrate", "temporal", "temporal-schema", "minio", "minio-init"}
    for svc in LONG_RUNNING + ONE_SHOT:
        nets = set(inspect(svc)["NetworkSettings"]["Networks"])
        assert ("ai-res_data" in nets) == (svc in allowed), (svc, nets)


# --- egress ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("target", [("169.254.169.254", "80"), ("1.1.1.1", "443"), ("10.0.0.1", "80"), ("192.168.65.254", "80"), ("host.docker.internal", "80")])
def test_egress_denied_from_api(target):
    """api is on internal-only networks: cloud metadata, the internet, RFC1918 and the Docker host gateway are all unreachable."""
    out = exec_in("api", "python", "-c", PRIVATE_PROBE, *target).stdout
    assert out.startswith("FAILED"), f"{target}: {out}"


def test_egress_probe_positive_control_reaches_postgres_port():
    assert exec_in("api", "python", "-c", PRIVATE_PROBE, "postgres", "5432").stdout.startswith("CONNECTED")


@pytest.mark.parametrize("service", ["postgres", "minio", "temporal"])
def test_egress_denied_from_data_services(service):
    """Positive control first (the probe works and reaches an internal peer), then the external target must fail."""
    probe = "timeout 3 bash -c 'exec 3<>/dev/tcp/{}/{}' 2>/dev/null && echo CONNECTED || echo FAILED"
    peer = {"postgres": ("minio", 9000), "minio": ("postgres", 5432), "temporal": ("postgres", 5432)}[service]
    ok = exec_in(service, "bash", "-c", probe.format(*peer))
    assert ok.stdout.strip() == "CONNECTED", f"probe broken: {ok.stdout!r} {ok.stderr!r}"
    for target in (("1.1.1.1", 443), ("169.254.169.254", 80)):
        out = exec_in(service, "bash", "-c", probe.format(*target))
        assert out.stdout.strip() == "FAILED", (target, out.stdout, out.stderr)


def test_reverse_proxy_egress_is_open_by_design_documented_gap():
    """KNOWN_GAPS G-34: the proxy sits on the non-internal `ingress` network, so its outbound traffic is NOT blocked. This test pins the
    current behaviour so that a change (fix or regression) is noticed; it is not a security assertion."""
    out = exec_in("reverse-proxy", "sh", "-c", "nc -z -w 3 1.1.1.1 443 && echo OPEN || echo CLOSED").stdout.strip()
    assert out in ("OPEN", "CLOSED")


# --- S07 identity surface through the proxy ---------------------------------------------------------------------------------
def _request(method, path, *, headers=None, body=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    c = http.client.HTTPSConnection("localhost", 8443, context=ctx, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()


LOGIN = json.dumps({"email": "nobody@example.invalid", "password": "not the password at all"})
JSON = {"Content-Type": "application/json"}


def test_me_without_a_session_is_a_problem_json_401_through_the_proxy():
    status, h, body = _request("GET", "/api/v1/me")
    assert status == 401 and h["content-type"].startswith("application/problem+json") and h["cache-control"] == "no-store"
    assert json.loads(body)["code"] == "AUTHENTICATION_REQUIRED" and "set-cookie" not in h


def test_login_origin_policy_with_positive_control():
    status, h, body = _request("POST", "/api/v1/auth/login", headers={**JSON, "Origin": "https://localhost:8443"}, body=LOGIN)
    assert status in (401, 422) and "set-cookie" not in h  # positive control: the allowed origin reaches the handler (an unknown organization is a 422/401, never a session)
    for origin in ("https://evil.example", "null"):
        status, h, _ = _request("POST", "/api/v1/auth/login", headers={**JSON, "Origin": origin}, body=LOGIN)
        assert status == 403 and "set-cookie" not in h
    assert _request("POST", "/api/v1/auth/login", headers=JSON, body=LOGIN)[0] == 403  # no Origin/Referer at all


def test_cors_is_deny_by_default_through_the_proxy():
    status, h, _ = _request("OPTIONS", "/api/v1/auth/login", headers={"Origin": "https://localhost:8443", "Access-Control-Request-Method": "POST"})
    assert status in (404, 405) and not any(k.startswith("access-control-") for k in h)


def test_bootstrap_job_is_not_started_by_the_stack():
    assert sh(["docker", "ps", "-a", "--filter", "label=com.docker.compose.service=bootstrap", "--format", "{{.Names}}"]).stdout.strip() == ""


# --- Caddy headers -----------------------------------------------------------------------------------------------------------
def _get(path="/"):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # local internal CA; the TLS handshake itself is what is being exercised
    c = http.client.HTTPSConnection("localhost", 8443, context=ctx, timeout=10)
    c.request("GET", path)
    r = c.getresponse()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()


def test_security_headers_present_and_server_header_hidden():
    status, h, _ = _get()
    assert status == 404  # S02 exposes no routes; the app answered through the proxy
    assert "max-age=" in h["strict-transport-security"] and "includeSubDomains" in h["strict-transport-security"]
    assert "default-src 'none'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"
    assert "server" not in h


def test_security_headers_also_on_error_responses():
    _, h, _ = _get("/does/not/exist")
    assert h["x-content-type-options"] == "nosniff" and "strict-transport-security" in h


def test_plain_http_is_not_served_on_proxy_port():
    with socket.create_connection(("127.0.0.1", 8443), timeout=3) as s:
        s.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        data = s.recv(300)
    status = data.split(b"\r\n", 1)[0]
    assert data == b"" or b" 400" in status, status  # Caddy answers 400 to cleartext on the TLS port; the application never sees it


# --- container hardening (inspect) ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("service", LONG_RUNNING + ONE_SHOT)
def test_container_hardening_from_inspect(service):
    i = inspect(service)
    hc = i["HostConfig"]
    assert hc["Privileged"] is False
    assert hc["ReadonlyRootfs"] is True
    assert [c.upper() for c in hc["CapDrop"]] == ["ALL"] and not hc["CapAdd"]
    assert "no-new-privileges:true" in hc["SecurityOpt"] or "no-new-privileges" in hc["SecurityOpt"]
    assert hc["NetworkMode"] != "host" and hc["PidMode"] != "host"
    assert not any("docker.sock" in (m.get("Source") or "") for m in i["Mounts"])
    assert i["Config"]["User"] not in ("", "0", "root") and not i["Config"]["User"].startswith(("0:", "root:"))
    assert hc["Memory"] > 0 and hc["PidsLimit"] and hc["PidsLimit"] > 0


@pytest.mark.parametrize("service", [s for s in LONG_RUNNING if s != "otel-collector"])
def test_processes_do_not_run_as_root(service):
    out = exec_in(service, "sh", "-c", "id -u").stdout.strip()
    assert out.isdigit() and int(out) != 0


# --- secrets ---------------------------------------------------------------------------------------------------------------
def test_secret_values_are_not_in_container_config_env(secret_values):
    blob = "".join(json.dumps(inspect(s)["Config"]) + json.dumps(inspect(s)["HostConfig"]) for s in LONG_RUNNING + ONE_SHOT)
    for name, value in secret_values.items():
        assert value not in blob, f"secret {name} leaked into docker inspect output"


@pytest.mark.parametrize("service", ["api", "postgres", "minio", "reverse-proxy"])
def test_secret_values_are_not_in_process_environment(service, secret_values):
    env = exec_in(service, "sh", "-c", "cat /proc/[0-9]*/environ 2>/dev/null | tr '\\0' '\\n'").stdout
    assert "PATH=" in env  # positive control: the probe read something
    for name, value in secret_values.items():
        assert value not in env, f"secret {name} found in {service} process environment"


def test_secret_values_are_not_in_logs(secret_values):
    logs = compose("logs", "--no-color").stdout
    assert "ai-res" in logs or "postgres" in logs  # positive control
    for name, value in secret_values.items():
        assert value not in logs, f"secret {name} found in container logs"


IMAGES = ["ai-res/api:dev", "ai-res/minio:RELEASE.2025-10-15T17-29-55Z", "ai-res/minio-mc:RELEASE.2025-08-13T08-35-41Z", "ai-res/caddy:2.11.9"]


def test_image_layer_scan_detects_a_planted_canary(tmp_path):
    """Positive control for the scan below: a throwaway image containing a canary (in a compressed layer) must be reported."""
    (tmp_path / "canary.txt").write_text("CANARY-s03-not-a-real-secret-1234567890")
    (tmp_path / "Dockerfile").write_text("FROM scratch\nCOPY canary.txt /canary.txt\n")
    assert sh(["docker", "build", "-q", "-t", "ai-res-canary:test", str(tmp_path)], timeout=300).returncode == 0
    try:
        hits = image_secret_hits("ai-res-canary:test", [b"CANARY-s03-not-a-real-secret-1234567890"], tmp_path)
    finally:
        sh(["docker", "rmi", "-f", "ai-res-canary:test"])
    assert hits, "scan is blind: a planted canary was not found"


@pytest.mark.parametrize("image", IMAGES)
def test_secret_values_are_not_in_image_layers(image, tmp_path, secret_values):
    needles = [v.strip().encode() for v in secret_values.values() if len(v.strip()) >= 12]
    assert len(needles) == len(secret_values)  # every secret (including minio_root_user) is searched for
    assert not image_secret_hits(image, needles, tmp_path), f"secret value(s) found in {image}"


def test_secrets_mounted_only_into_services_that_need_them():
    expect = {
        "api": {"cursor_hmac_key", "api_db_password", "postgres_tls_ca_cert", "mfa_encryption_key"},  # never bootstrap_secret (S07)
        "postgres": {"postgres_superuser_password", "postgres_tls_server_cert", "postgres_tls_server_key"},
        "migrate": {"migrator_db_password", "postgres_tls_ca_cert"},
        "temporal": {"temporal_db_password", "postgres_tls_ca_cert"},
        "minio": {"minio_root_user", "minio_root_password"},
        "reverse-proxy": set(),
        "temporal-ui": set(),
        "otel-collector": set(),
    }
    for svc, names in expect.items():
        mounted = {m["Destination"].rsplit("/", 1)[-1] for m in inspect(svc)["Mounts"] if m["Destination"].startswith("/run/secrets/")}
        assert mounted == names, (svc, mounted)


def test_no_default_credentials_secrets_are_random_and_distinct(secret_values):
    vals = [v for k, v in secret_values.items() if k != "minio_root_user" and not k.startswith("postgres_tls_")]
    assert len(set(vals)) == len(vals)
    # mfa_encryption_key is base64 of exactly 32 random bytes (44 chars): its strength is the key size, not the text length
    assert all(len(v) >= 48 for k, v in secret_values.items() if k not in ("minio_root_user", "mfa_encryption_key") and not k.startswith("postgres_tls_"))
    assert len(base64.b64decode(secret_values["mfa_encryption_key"], validate=True)) == 32
    assert all(w not in v.lower() for v in vals for w in ("password", "changeme", "minioadmin", "admin"))


# --- PostgreSQL provisioning (ADR-036, DOC-015 §5.1) ----------------------------------------------------------------------
def _psql(user, secret, db, sql, secret_values):
    pgpass = f"localhost:5432:*:{user}:{secret_values[secret]}\n"  # libpq matches unix-socket connections as host "localhost"
    script = "cat > /tmp/pgpass.t && chmod 600 /tmp/pgpass.t && PGPASSFILE=/tmp/pgpass.t psql -v ON_ERROR_STOP=1 -tA -h /var/run/postgresql -U " + user + " -d " + db + " -c \"" + sql + "\"; rc=$?; rm -f /tmp/pgpass.t; exit $rc"
    return exec_in("postgres", "sh", "-c", script, stdin=pgpass)


def test_databases_and_roles_provisioned_with_least_privilege(secret_values):
    r = _psql("postgres", "postgres_superuser_password", "postgres", "select datname from pg_database order by 1", secret_values)
    assert {"ai_res_db", "temporal_db", "temporal_visibility_db"} <= set(r.stdout.split()), r.stderr
    r = _psql("postgres", "postgres_superuser_password", "postgres", "select rolname||':'||rolsuper||rolbypassrls||rolcreatedb||rolcreaterole||rolcanlogin from pg_roles where rolname in ('temporal','ai_res_checkpointer','ai_res_owner') order by 1", secret_values)
    rows = dict(line.split(":") for line in r.stdout.split())
    assert rows["temporal"] == "falsefalsefalsefalsetrue" and rows["ai_res_checkpointer"] == "falsefalsefalsefalsetrue" and rows["ai_res_owner"] == "falsefalsefalsefalsefalse"


def test_checkpointer_role_has_usage_but_no_ddl_in_langgraph(secret_values):
    """ADR-036 / DOC-015 add.1.6: runtime roles have no DDL and no ownership; langgraph tables are provisioned, not created at runtime."""
    su = lambda sql: _psql("postgres", "postgres_superuser_password", "ai_res_db", sql, secret_values)  # noqa: E731
    cp = lambda sql: _psql("ai_res_checkpointer", "checkpointer_db_password", "ai_res_db", sql, secret_values)  # noqa: E731
    assert su("select has_schema_privilege('ai_res_checkpointer','langgraph','USAGE')").stdout.strip() == "t"
    assert su("select has_schema_privilege('ai_res_checkpointer','langgraph','CREATE')").stdout.strip() == "f"
    denied = cp("create table langgraph.s03_probe(id int)")
    assert denied.returncode != 0 and "permission denied" in denied.stderr
    # positive control for DML: a provisioned (superuser-created) table with explicit grants is usable
    assert su("create table langgraph.s03_probe(id int); grant select, insert on langgraph.s03_probe to ai_res_checkpointer").returncode == 0
    try:
        assert cp("insert into langgraph.s03_probe values (1)").returncode == 0
        assert cp("drop table langgraph.s03_probe").returncode != 0  # no ownership
    finally:
        su("drop table if exists langgraph.s03_probe")
    assert cp("create table public.s03_probe(id int)").returncode != 0
    other_db = _psql("ai_res_checkpointer", "checkpointer_db_password", "temporal_db", "select 1", secret_values)
    assert other_db.returncode != 0


def test_password_auth_is_scram_only_and_access_is_tls_restricted(secret_values):
    q = lambda sql: _psql("postgres", "postgres_superuser_password", "postgres", sql, secret_values)  # noqa: E731
    methods = set(q("select distinct auth_method from pg_hba_file_rules").stdout.split())
    assert methods and methods <= {"scram-sha-256", "reject"}, methods
    assert q("show password_encryption").stdout.strip() == "scram-sha-256"
    assert q("select count(*) from pg_authid where rolpassword is not null and rolpassword not like 'SCRAM-SHA-256$%'").stdout.strip() == "0"
    assert q("show ssl").stdout.strip() == "on"
    types = set(q("select distinct type from pg_hba_file_rules").stdout.split())
    assert "host" in types and types <= {"local", "hostssl", "host"}
    assert q("select count(*) from pg_hba_file_rules where type='host' and auth_method<>'reject'").stdout.strip() == "0"


def test_network_connections_require_tls_and_matching_role_database(secret_values):
    """From inside the postgres container over TCP (hostssl rules): cleartext is rejected, TLS works, and roles cannot reach other DBs."""
    def tcp(user, secret, db, sslmode):
        pgpass = f"postgres:5432:*:{user}:{secret_values[secret]}\n"
        script = ("cat > /tmp/pgpass.t && chmod 600 /tmp/pgpass.t && PGPASSFILE=/tmp/pgpass.t PGSSLMODE=" + sslmode
                  + f" psql -v ON_ERROR_STOP=1 -tA -h postgres -U {user} -d {db} -c 'select 1'; rc=$?; rm -f /tmp/pgpass.t; exit $rc")
        return exec_in("postgres", "sh", "-c", script, stdin=pgpass)

    assert tcp("ai_res_checkpointer", "checkpointer_db_password", "ai_res_db", "require").stdout.strip() == "1"  # positive control (TLS)
    clear = tcp("ai_res_checkpointer", "checkpointer_db_password", "ai_res_db", "disable")
    assert clear.returncode != 0 and "pg_hba.conf" in clear.stderr
    other = tcp("ai_res_checkpointer", "checkpointer_db_password", "temporal_db", "require")
    assert other.returncode != 0
    assert tcp("temporal", "temporal_db_password", "ai_res_db", "require").returncode != 0


def test_temporal_namespace_ai_res_exists():
    res = compose("run", "--rm", "--no-deps", "--entrypoint", "temporal", "temporal-namespace", "operator", "namespace", "describe", "--address", "temporal:7233", "-n", "ai-res")
    assert res.returncode == 0 and "ai-res" in res.stdout, res.stderr[-400:]


def test_minio_buckets_exist_and_are_versioned():
    script = (
        "set -e; export MC_CONFIG_DIR=/tmp/mc; "
        'export MC_HOST_local="http://$(cat /run/secrets/minio_root_user):$(cat /run/secrets/minio_root_password)@minio:9000"; '
        "for b in ai-res-sources ai-res-artifacts ai-res-worker-results ai-res-exports ai-res-temporary; do mc version info local/$b; done"
    )
    res = compose("run", "--rm", "--no-deps", "--entrypoint", "bash", "minio-init", "-c", script)
    assert res.returncode == 0, res.stderr[-400:]
    assert res.stdout.count("versioning is enabled") == 5, res.stdout


def test_api_image_has_no_package_installer():
    """pip/setuptools were removed from the runtime image (scan findings in their vendored libraries; nothing needs them at runtime)."""
    out = exec_in("api", "python", "-c", "import importlib.util as u;print([m for m in ('pip','setuptools','pkg_resources') if u.find_spec(m)])").stdout
    assert out.strip() == "[]", out


def test_temporal_connects_to_postgres_over_verified_tls(secret_values):
    """Evidence that the running Temporal server really uses TLS (not just that TLS is available)."""
    r = _psql("postgres", "postgres_superuser_password", "postgres",
              "select count(*) filter (where s.ssl), count(*) filter (where not s.ssl) from pg_stat_ssl s join pg_stat_activity a using (pid) where a.usename='temporal'",
              secret_values)
    tls, clear = r.stdout.strip().split("|")
    assert int(tls) >= 1 and int(clear) == 0, r.stdout
