"""Exercise local credential preparation without touching real dev credentials."""

import hashlib
import os
import shutil
import ssl

import g02_credentials as credentials
import pytest
import secrets_dev as sd
import yaml


@pytest.fixture(scope="module")
def tls():
    return credentials.generate_tls("1")


def test_transport_certificates_have_distinct_trust_roots_and_exact_temporal_pins(tls):
    pins = credentials.validate_tls(tls)
    assert len({tls[ca] for ca in credentials.TLS_GROUPS}) == 4
    for stem, role in {
        "operator": "operator",
        "manager": "manager",
        "dispatcher": "dispatcher",
        "cancellation": "backend-cancellation",
        "reconciliation": "reconciliation-observer",
    }.items():
        der = ssl.PEM_cert_to_DER_cert(tls[f"temporal_{stem}_cert"])
        assert pins[f"{role}.sha256"] == hashlib.sha256(der).hexdigest() + "\n"
    assert len(pins) == 5


def test_encrypted_bundle_rejects_cross_role_and_cross_ca_certificate_material(tls):
    wrong_key = tls | {"temporal_operator_key": tls["temporal_dispatcher_key"]}
    with pytest.raises(ValueError, match="certificate and key must match"):
        credentials.validate_tls(wrong_key)
    wrong_role = wrong_key | {"temporal_operator_cert": tls["temporal_dispatcher_cert"]}
    with pytest.raises(ValueError, match="SAN or purpose"):
        credentials.validate_tls(wrong_role)
    wrong_ca = tls | {"temporal_platform_ca": tls["g02_delivery_ca"]}
    with pytest.raises(ValueError, match="could not process"):
        credentials.validate_tls(wrong_ca)


def test_key_material_must_be_exactly_one_expected_pem(tls):
    name = "temporal_frontend_key"
    with pytest.raises(ValueError, match="exactly one EC private key"):
        credentials.validate_tls(tls | {name: tls[name] + tls["temporal_operator_key"]})


def test_managed_files_cover_the_compose_mounts():
    # Read only the untagged top-level declaration so no Compose execution is needed.
    overlay = (sd.INFRA / "compose.g02.yaml").read_text()
    declarations = yaml.safe_load(overlay.split("\nsecrets:\n", 1)[1])
    assert declarations and declarations.keys() >= sd.G02_BASE_NAMES
    material = sd.G02_NAMES | sd.G02_BASE_NAMES
    for name, secret in declarations.items():
        assert name in material
        assert secret == {"file": "${G02_PROTECTED_DIR:?}/" + name}


@pytest.fixture
def local_bundle(tmp_path, monkeypatch, tls):
    base_file = tmp_path / "local.enc.yaml"
    base_file.touch()
    bundle = tmp_path / "g02.enc.yaml"
    runtime = tmp_path / "g02"
    monkeypatch.setattr(sd, "ENCRYPTED", base_file)
    monkeypatch.setattr(sd, "G02_ENCRYPTED", bundle)
    monkeypatch.setattr(sd, "G02_RUNTIME", runtime)
    monkeypatch.setattr(sd, "ensure_age_key", lambda **kwargs: "test-recipient")
    monkeypatch.setattr(credentials, "generate_tls", lambda days: tls.copy())
    base = {name: f"fixture-{name}" for name in sd.G02_BASE_NAMES}
    base["outbox_delivery_signing_key"] = sd._generate("outbox_delivery_signing_key")
    base["assigned_delivery_public_keys"] = sd.derive_assigned_delivery_public_keys(base)
    monkeypatch.setattr(sd, "decrypt", lambda: base)
    encrypted = {}

    def encrypt(values, recipient, *, path):
        assert recipient == "test-recipient" and path == bundle and not bundle.exists()
        encrypted.update(values)
        bundle.touch(mode=0o600)

    def decrypt(*, path):
        assert path == bundle and bundle.exists()
        return encrypted.copy()

    monkeypatch.setattr(sd, "_encrypt", encrypt)
    monkeypatch.setattr(sd, "_decrypt_raw", decrypt)
    return base, encrypted, runtime


def test_rerun_preserves_credentials_inode_and_revocation(local_bundle):
    base, encrypted, runtime = local_bundle
    sd.init_g02()
    state = encrypted.copy()
    server = runtime / "temporal_frontend_key"
    inode = server.stat().st_ino
    inherited_inodes = {name: (runtime / name).stat().st_ino for name in sd.G02_BASE_NAMES}
    assert server.stat().st_mode & 0o777 == 0o444
    assert runtime.stat().st_mode & 0o777 == 0o700
    assert {name: (runtime / name).read_text() for name in inherited_inodes} == base
    assert state.keys().isdisjoint(base)
    assert (runtime / "g02_platform_public_keys").read_text() == sd._g02_platform_registry(state)
    assert {line.split()[0] for line in state["g02_platform_public_keys"].splitlines()} == {"MANAGER_RUNTIME", "TEMPORAL_AUTH_CONTROL"}
    revoked = runtime / "active-certs" / "manager.sha256"
    revoked.unlink()
    sd.init_g02()
    assert not revoked.exists() and server.stat().st_ino == inode and encrypted == state
    assert {name: (runtime / name).stat().st_ino for name in inherited_inodes} == inherited_inodes


def test_restoring_deleted_runtime_copies_files_without_republishing_any_client_pin(local_bundle):
    _, encrypted, runtime = local_bundle
    sd.init_g02()
    assert len(list((runtime / "active-certs").iterdir())) == 5
    state = encrypted.copy()
    shutil.rmtree(runtime)
    sd.init_g02()
    assert encrypted == state and (runtime / "temporal_operator_cert").read_text() == state["temporal_operator_cert"]
    assert not list((runtime / "active-certs").iterdir())


def test_runtime_from_partial_or_changed_bundle_is_rejected_without_overwrite(local_bundle, capsys):
    _, encrypted, runtime = local_bundle
    sd.init_g02()
    registry = runtime / "g02_platform_public_keys"
    registry.chmod(0o600)
    registry.write_text("untrusted-runtime-text")
    registry.chmod(0o444)
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()
    assert registry.read_text() == "untrusted-runtime-text"
    del encrypted["temporal_operator_key"]
    with pytest.raises(SystemExit, match="could not prepare G02 credentials") as raised:
        sd.init_g02()
    assert "untrusted-runtime-text" not in capsys.readouterr().out + str(raised.value)


def test_partial_base_registry_is_rejected_before_preparing_g02(local_bundle):
    base, encrypted, runtime = local_bundle
    base["assigned_delivery_public_keys"] = "\n".join(base["assigned_delivery_public_keys"].split())
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()
    assert not encrypted and not runtime.exists()


def test_missing_inherited_secret_is_rejected_before_preparing_g02(local_bundle):
    base, encrypted, runtime = local_bundle
    del base["postgres_tls_server_key"]
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()
    assert not encrypted and not runtime.exists()


def test_inherited_secret_drift_keeps_the_existing_copy(local_bundle):
    base, encrypted, runtime = local_bundle
    sd.init_g02()
    state = encrypted.copy()
    inherited_secret = runtime / "api_db_password"
    inode = inherited_secret.stat().st_ino
    original = base["api_db_password"]
    base["api_db_password"] = f"{original}-changed"
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()
    assert inherited_secret.read_text() == original and inherited_secret.stat().st_ino == inode and encrypted == state


def test_mount_sources_are_readable_by_service_uids_behind_a_private_host_directory(local_bundle):
    _, _, runtime = local_bundle
    sd.init_g02()
    assert runtime.stat().st_uid == os.getuid()
    assert runtime.stat().st_mode & 0o777 == 0o700
    assert (runtime / "active-certs").stat().st_mode & 0o777 == 0o755
    for source in (file for file in runtime.rglob("*") if file.is_file()):
        assert source.stat().st_mode & 0o777 == 0o444
    runtime.chmod(0o755)
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()


def test_existing_symlink_mount_source_is_rejected(local_bundle):
    _, _, runtime = local_bundle
    sd.init_g02()
    key = runtime / "temporal_frontend_key"
    renamed = runtime.parent / "test-renamed-key"
    key.rename(renamed)
    key.symlink_to(renamed)
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()


@pytest.mark.parametrize("unsafe", ["parent", "lock", "bundle"])
def test_untrusted_g02_storage_is_rejected(local_bundle, unsafe):
    _, _, runtime = local_bundle
    if unsafe == "bundle":
        sd.init_g02()
        sd.G02_ENCRYPTED.chmod(0o644)
    elif unsafe == "lock":
        sd.G02_ENCRYPTED.with_suffix(".lock").touch(mode=0o644)
    else:
        runtime.parent.chmod(0o777)
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()


def test_symlink_lock_is_rejected_before_taking_lock_or_creating_bundle(local_bundle, tmp_path):
    _, encrypted, runtime = local_bundle
    target = tmp_path / "g02-lock-target"
    target.touch(mode=0o600)
    sd.G02_ENCRYPTED.with_suffix(".lock").symlink_to(target)
    with pytest.raises(SystemExit, match="could not prepare G02 credentials"):
        sd.init_g02()
    assert not encrypted and not runtime.exists()
