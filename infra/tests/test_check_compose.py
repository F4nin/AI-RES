"""Policy checks over a normalised `docker compose config --format json` model. Each rule has a violating mutation
that must be reported (the checks must fail on intentional violations, ADR-037 layer 1)."""
import copy

import check_compose as cc

DIGEST = "sha256:" + "a" * 64


def good_service(**over):
    svc = {
        "image": f"registry.example/app:1.2.3@{DIGEST}",
        "user": "10001:10001",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "mem_limit": "512m",
        "pids_limit": 256,
        "healthcheck": {"test": ["CMD", "true"]},
        "networks": {"app": None},
    }
    svc.update(over)
    return svc


def good_model():
    return {
        "services": {
            "reverse-proxy": good_service(networks={"ingress": None, "app": None}, ports=[{"host_ip": "127.0.0.1", "published": "8443", "target": 8443}]),
            "api": good_service(networks={"app": None, "data": None}),
            "postgres": good_service(networks={"data": None}),
            "temporal-ui": good_service(networks={"admin": None}),
        },
        "networks": {"ingress": {}, "app": {"internal": True}, "data": {"internal": True}, "egress": {}, "admin": {"internal": True}},
    }


def run(model, dockerfiles=None, base_dir=None):
    return cc.check_model(model, dockerfiles or {}, base_dir)


def test_good_model_passes():
    assert run(good_model()) == []


def mutate(path_fn):
    m = copy.deepcopy(good_model())
    path_fn(m)
    return m


def has(violations, fragment):
    return any(fragment in v for v in violations)


# --- images -------------------------------------------------------------------------------------------------------
def test_latest_tag_rejected():
    v = run(mutate(lambda m: m["services"]["api"].update(image=f"x/y:latest@{DIGEST}")))
    assert has(v, "latest")


def test_missing_tag_rejected():
    v = run(mutate(lambda m: m["services"]["api"].update(image=f"x/y@{DIGEST}")))
    assert has(v, "tag")


def test_missing_digest_rejected():
    v = run(mutate(lambda m: m["services"]["api"].update(image="x/y:1.0")))
    assert has(v, "digest")


def test_built_service_exempt_but_dockerfile_must_pin():
    m = mutate(lambda m: m["services"]["api"].update(image="ai-res/api:dev", build={"context": "."}))
    assert run(m, {"api": ["FROM python:3.13"]}) != []
    assert has(run(m, {"api": ["FROM python:3.13"]}), "digest")
    ok = ["# comment", f"FROM python:3.13@{DIGEST} AS build", "FROM build AS final"]
    assert run(m, {"api": ok}) == []


def test_dockerfile_latest_rejected():
    m = mutate(lambda m: m["services"]["api"].update(image="ai-res/api:dev", build={"context": "."}))
    assert has(run(m, {"api": [f"FROM python:latest@{DIGEST}"]}), "latest")


# --- ports --------------------------------------------------------------------------------------------------------
def test_only_reverse_proxy_may_publish():
    v = run(mutate(lambda m: m["services"]["postgres"].update(ports=[{"host_ip": "127.0.0.1", "published": "5432", "target": 5432}])))
    assert has(v, "postgres") and has(v, "publish")


def test_reverse_proxy_must_bind_loopback():
    v = run(mutate(lambda m: m["services"]["reverse-proxy"].update(ports=[{"published": "443", "target": 443}])))
    assert has(v, "127.0.0.1")
    v = run(mutate(lambda m: m["services"]["reverse-proxy"].update(ports=[{"host_ip": "0.0.0.0", "published": "443", "target": 443}])))  # noqa: S104
    assert has(v, "127.0.0.1")


# --- hardening ----------------------------------------------------------------------------------------------------
def test_root_user_rejected():
    for u in (None, "root", "0", "0:0"):
        m = mutate(lambda m, u=u: m["services"]["api"].pop("user") if u is None else m["services"]["api"].update(user=u))
        assert has(run(m), "non-root"), u


def test_read_only_required():
    assert has(run(mutate(lambda m: m["services"]["api"].update(read_only=False))), "read_only")


def test_cap_drop_all_required():
    assert has(run(mutate(lambda m: m["services"]["api"].update(cap_drop=["NET_RAW"]))), "cap_drop")


def test_cap_add_rejected():
    assert has(run(mutate(lambda m: m["services"]["api"].update(cap_add=["SYS_ADMIN"]))), "cap_add")


def test_no_new_privileges_required():
    assert has(run(mutate(lambda m: m["services"]["api"].update(security_opt=[]))), "no-new-privileges")


def test_privileged_rejected():
    assert has(run(mutate(lambda m: m["services"]["api"].update(privileged=True))), "privileged")


def test_docker_socket_rejected():
    vol = {"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
    assert has(run(mutate(lambda m: m["services"]["api"].update(volumes=[vol]))), "docker.sock")
    vol = {"type": "bind", "source": "/run/docker.sock", "target": "/x"}
    assert has(run(mutate(lambda m: m["services"]["api"].update(volumes=[vol]))), "docker.sock")


def test_host_namespaces_rejected():
    for mode in ("host", "bridge", "service:postgres", "container:abc"):
        assert has(run(mutate(lambda m, mode=mode: m["services"]["api"].update(network_mode=mode))), "network_mode"), mode
    assert has(run(mutate(lambda m: m["services"]["api"].update(pid="host"))), "pid")
    assert has(run(mutate(lambda m: m["services"]["api"].update(ipc="host"))), "ipc")


def test_resource_limits_required():
    assert has(run(mutate(lambda m: m["services"]["api"].pop("mem_limit"))), "mem_limit")
    assert has(run(mutate(lambda m: m["services"]["api"].pop("pids_limit"))), "pids_limit")


def test_healthcheck_required_unless_declared_one_shot():
    assert has(run(mutate(lambda m: m["services"]["api"].pop("healthcheck"))), "healthcheck")
    # restart: "no" alone is not an exemption for an arbitrary service ...
    assert has(run(mutate(lambda m: (m["services"]["api"].pop("healthcheck"), m["services"]["api"].update(restart="no")))), "healthcheck")
    # ... only the declared one-shot jobs may omit it
    m = mutate(lambda m: m["services"].update({"postgres-provision": good_service(networks={"data": None}, restart="no")}))
    m["services"]["postgres-provision"].pop("healthcheck")
    assert run(m) == []


def test_migrate_job_may_hold_only_the_migration_identity_secret():
    """S04: runtime role passwords never reach the migration job, and the migration password never reaches any other service."""
    def migrate_with(secret: str):
        return mutate(lambda m: m["services"].update({"migrate": good_service(networks={"data": None}, restart="no", secrets=[{"source": secret}])}))
    assert not [x for x in run(migrate_with("migrator_db_password")) if "not allowed to have" in x]
    for leaked in ("api_db_password", "backup_db_password", "postgres_superuser_password"):
        assert has(run(migrate_with(leaked)), "not allowed to have"), leaked
    v = run(mutate(lambda m: m["services"]["api"].update(secrets=[{"source": "migrator_db_password"}])))
    assert has(v, "not allowed to have")


def test_disabled_healthcheck_rejected():
    assert has(run(mutate(lambda m: m["services"]["api"].update(healthcheck={"disable": True}))), "disabled")


def test_empty_model_does_not_pass():
    assert has(run({"services": {}, "networks": {}}), "no services")


# --- secrets in environment -----------------------------------------------------------------------------------------
def test_secret_in_environment_rejected():
    for key in ("POSTGRES_PASSWORD", "API_TOKEN", "MINIO_ROOT_PASSWORD", "SOME_SECRET", "SIGNING_KEY"):
        v = run(mutate(lambda m, key=key: m["services"]["api"].update(environment={key: "x"})))
        assert has(v, key), key


def test_secret_file_pointer_allowed():
    assert run(mutate(lambda m: m["services"]["api"].update(environment={"POSTGRES_PASSWORD_FILE": "/run/secrets/pg"}))) == []


def test_secret_file_pointer_must_reference_run_secrets():
    v = run(mutate(lambda m: m["services"]["api"].update(environment={"POSTGRES_PASSWORD_FILE": "hunter2hunter2"})))
    assert has(v, "POSTGRES_PASSWORD_FILE")


def test_secret_allowlist_per_service():
    assert has(run(mutate(lambda m: m["services"]["api"].update(secrets=[{"source": "postgres_superuser_password"}]))), "not allowed to have")
    assert run(mutate(lambda m: m["services"]["api"].update(secrets=[{"source": "cursor_hmac_key"}]))) == []
    assert has(run(mutate(lambda m: m["services"]["temporal-ui"].update(secrets=[{"source": "cursor_hmac_key"}]))), "not allowed to have")


def test_credentials_in_url_rejected():
    v = run(mutate(lambda m: m["services"]["api"].update(environment={"DATABASE_URL": "postgresql://u:p@db/x"})))
    assert has(v, "DATABASE_URL")


# --- network segmentation -----------------------------------------------------------------------------------------------
def test_app_and_data_must_be_internal():
    assert has(run(mutate(lambda m: m["networks"]["data"].update(internal=False))), "data")
    assert has(run(mutate(lambda m: m["networks"]["app"].pop("internal"))), "app")


def test_admin_services_not_on_ingress():
    assert has(run(mutate(lambda m: m["services"]["temporal-ui"].update(networks={"admin": None, "ingress": None}))), "admin")


def test_reverse_proxy_not_on_data_or_admin():
    assert has(run(mutate(lambda m: m["services"]["reverse-proxy"].update(networks={"ingress": None, "data": None}))), "reverse-proxy")


def test_manager_worker_have_no_data_network():
    """PERSIST-023 (structural part): no network path from Manager/Worker Runtime to PostgreSQL."""
    for name in ("manager-runtime", "worker-runtime", "worker-runtime-2"):
        m = mutate(lambda m, name=name: m["services"].update({name: good_service(networks={"app": None, "data": None})}))
        assert has(run(m), name), name
    for bad_net in ("egress", "admin", "ingress"):
        m = mutate(lambda m, bad_net=bad_net: m["services"].update({"worker-runtime": good_service(networks={"app": None, bad_net: None})}))
        assert has(run(m), "worker-runtime"), bad_net
    ok = mutate(lambda m: m["services"].update({"worker-runtime": good_service(networks={"app": None})}))
    assert run(ok) == []


def test_only_allowlisted_services_on_data_network():
    v = run(mutate(lambda m: m["services"].update({"mystery": good_service(networks={"data": None})})))
    assert has(v, "mystery")


def test_services_must_declare_networks():
    assert has(run(mutate(lambda m: m["services"]["api"].pop("networks"))), "networks")


def test_egress_network_only_for_controlled_egress_services():
    assert has(run(mutate(lambda m: m["services"]["api"].update(networks={"app": None, "egress": None}))), "egress")
    ok = mutate(lambda m: m["services"].update({"llm-gateway": good_service(networks={"app": None, "egress": None})}))
    assert run(ok) == []


def test_ingress_network_only_for_proxy_and_never_with_data():
    assert has(run(mutate(lambda m: m["services"]["postgres"].update(networks={"data": None, "ingress": None}))), "ingress")
    assert has(run(mutate(lambda m: m["services"]["api"].update(networks={"app": None, "data": None, "egress": None}))), "egress")


def test_bind_mounts_must_stay_inside_project(tmp_path):
    inside = {"type": "bind", "source": str(tmp_path / "config" / "x.conf"), "target": "/x"}
    assert run(mutate(lambda m: m["services"]["api"].update(volumes=[inside])), base_dir=tmp_path) == []
    for src in ("/var/run", "/", "/etc", str(tmp_path.parent)):
        vol = {"type": "bind", "source": src, "target": "/x"}
        assert has(run(mutate(lambda m, vol=vol: m["services"]["api"].update(volumes=[vol])), base_dir=tmp_path), "outside the project"), src


def test_dockerfile_copy_from_image_must_be_pinned_and_file_must_exist():
    m = mutate(lambda m: m["services"]["api"].update(image="ai-res/api:dev", build={"context": "."}))
    bad = [f"FROM python:3.13@{DIGEST}", "COPY --from=evil/tool:latest /x /x"]
    assert has(run(m, {"api": bad}), "latest")
    assert has(run(m, {"api": [f"FROM python:3.13@{DIGEST} AS b", "COPY --from=b /x /x"]}), "") is False
    assert has(run(m, {"api": []}), "nothing was checked")


def test_custom_non_internal_network_rejected():
    m = mutate(lambda m: m["networks"].update(debug={}))
    m["services"]["api"]["networks"]["debug"] = None
    assert has(run(m), "network 'debug': must be internal")


def test_secrets_directory_bind_mount_rejected(tmp_path):
    for src in (tmp_path / "secrets" / "runtime", tmp_path / "secrets"):
        vol = {"type": "bind", "source": str(src), "target": "/s"}
        assert has(run(mutate(lambda m, vol=vol: m["services"]["api"].update(volumes=[vol])), base_dir=tmp_path), "secrets directory"), src


def test_load_model_renders_all_profiles():
    import inspect

    assert '"--profile", "*"' in inspect.getsource(cc.load_model)


# --- S07: identity secrets -----------------------------------------------------------------------------------------
def bootstrap_model(**over):
    svc = good_service(networks={"data": None}, restart="no", secrets=[{"source": "api_db_password"}, {"source": "bootstrap_secret"}], profiles=["bootstrap"])
    svc.pop("healthcheck")
    svc.update(over)
    return mutate(lambda m: m["services"].update({"bootstrap": svc}))


def test_bootstrap_job_may_hold_the_bootstrap_secret_but_the_api_may_not():
    assert run(bootstrap_model()) == []
    assert has(run(mutate(lambda m: m["services"]["api"].update(secrets=[{"source": "bootstrap_secret"}]))), "not allowed to have")  # the one-time secret never reaches the API
    assert has(run(bootstrap_model(secrets=[{"source": "mfa_encryption_key"}])), "not allowed to have")  # and the job gets no MFA key


def test_api_gets_runtime_db_identity_and_mfa_key_but_no_other_identity():
    ok = [{"source": s} for s in ("cursor_hmac_key", "api_db_password", "postgres_tls_ca_cert", "mfa_encryption_key", "idempotency_keyring")]
    assert run(mutate(lambda m: m["services"]["api"].update(secrets=ok))) == []
    for other in ("migrator_db_password", "outbox_db_password", "postgres_superuser_password"):
        assert has(run(mutate(lambda m, o=other: m["services"]["api"].update(secrets=[{"source": o}]))), "not allowed to have")


def test_bootstrap_job_is_hardened_like_every_other_service():
    assert has(run(bootstrap_model(read_only=False)), "read_only")
    assert has(run(bootstrap_model(networks={"ingress": None})), "not allowed on the ingress network")


# --- ADR-071: trusted proxy address ------------------------------------------------------------------------------
def trusted_model(cidr="172.28.20.2/32", fixed="172.28.20.2", ip_range="172.28.20.128/25"):
    m = copy.deepcopy(good_model())
    m["services"]["api"]["environment"] = {"AI_RES_TRUSTED_PROXY_CIDRS": cidr}
    m["services"]["reverse-proxy"]["networks"] = {"ingress": None, "app": {"ipv4_address": fixed} if fixed else None}
    cfg = {"subnet": "172.28.20.0/24"}
    if ip_range:
        cfg["ip_range"] = ip_range
    m["networks"]["app"] = {"internal": True, "ipam": {"config": [cfg]}}
    return m


def test_trusted_proxy_setup_passes_when_pinned_and_outside_the_dynamic_range():
    assert run(trusted_model()) == []


def test_trusted_proxy_cidr_must_be_exactly_the_proxy_address():
    assert has(run(trusted_model(cidr="172.28.20.0/24")), "must be exactly the reverse-proxy address")


def test_trusted_proxy_needs_a_fixed_address():
    assert has(run(trusted_model(fixed=None)), "no fixed ipv4_address")


def test_dynamic_range_must_exclude_the_proxy_address():
    assert has(run(trusted_model(ip_range=None)), "ip_range must exclude")
    assert has(run(trusted_model(ip_range="172.28.20.0/24")), "ip_range must exclude")
