"""Freeze and private-file boundary regressions for the standalone operator."""
import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import docker
import pytest
from scripts.slice01 import cli, common
from scripts.slice01 import prepare as plans
from scripts.slice01.common import SliceRefused, bundle, canonical, decode, digest, load_plan, read_owned, write_new
from scripts.slice01.ledger import SliceLedger
from scripts.slice01.runtime import SliceRuntime


@pytest.fixture
def plan_dir(tmp_path):
    import scripts.slice01.common as common
    directory = tmp_path / "config"
    directory.mkdir(mode=0o700)
    now = datetime.now(UTC)
    plan = {"version": "slice01/1", "promptBundle": bundle(),
            "toolHashes": {p.name: digest(p.read_bytes()) for p in common.Path(common.__file__).parent.glob("*.py")},
            "scriptsInitializerSha256": digest(common.Path(common.__file__).parent.parent.joinpath("__init__.py").read_bytes()),
            "tariffCheckedAt": now.isoformat(), "expiresAt": (now + timedelta(minutes=15)).isoformat()}
    plan["manifestSha256"] = digest(canonical(plan))
    write_new(directory / "plan.json", plan)
    return directory, plan


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'{"a":"\\ud800"}'])
def test_artifact_decode_rejects_ambiguous_json(raw):
    with pytest.raises((ValueError, UnicodeError)):
        decode(raw)


def test_private_artifact_cannot_be_overwritten_or_linked(tmp_path):
    path = tmp_path / "private.json"
    write_new(path, {"a": "safe"})
    assert decode(read_owned(path)) == {"a": "safe"}
    with pytest.raises(FileExistsError):
        write_new(path, {"a": "other"})
    linked = tmp_path / "linked.json"
    os.link(path, linked)
    with pytest.raises(SliceRefused):
        read_owned(path)


@pytest.mark.parametrize("mode", [0o644, 0o660, 0o666])
def test_shared_session_file_rejected(tmp_path, mode):
    path = tmp_path / "session.json"
    write_new(path, {"fixture": True})
    path.chmod(mode)
    with pytest.raises(SliceRefused):
        read_owned(path)


def test_symlink_session_file_rejected(tmp_path):
    target = tmp_path / "target.json"
    write_new(target, {"fixture": True})
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(OSError):
        read_owned(link)


def test_plan_manifest_and_tariff_freshness(plan_dir):
    directory, plan = plan_dir
    assert load_plan(directory) == plan
    plan["expiresAt"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    plan["manifestSha256"] = digest(canonical({k: v for k, v in plan.items() if k != "manifestSha256"}))
    (directory / "plan.json").write_bytes(canonical(plan))
    with pytest.raises(SliceRefused, match="EXPIRED"):
        load_plan(directory)
    assert load_plan(directory, for_execution=False) == plan


def test_plan_tampering_is_refused(plan_dir):
    directory, plan = plan_dir
    plan["promptBundle"]["version"] = "different"
    (directory / "plan.json").write_text(json.dumps(plan))
    with pytest.raises(SliceRefused, match="PLAN_CHANGED"):
        load_plan(directory)
    with pytest.raises(SliceRefused, match="PLAN_CHANGED"):
        load_plan(directory, for_execution=False)


def test_cleanup_only_runtime_cannot_start_or_verify_dispatch():
    runtime = object.__new__(SliceRuntime)
    runtime.cleanup_only = True
    with pytest.raises(SliceRefused, match="CLEANUP_ONLY"):
        runtime.start()
    with pytest.raises(SliceRefused, match="CLEANUP_ONLY"):
        runtime.verify()


def test_snapshot_mount_order_is_irrelevant_but_mount_fields_are_bound():
    mounts = [{"Destination": "/a", "Source": "/private/a", "RW": False},
              {"Destination": "/b", "Source": "/private/b", "RW": True}]
    attrs = {"State": {"Status": "running", "StartedAt": "fixed"}, "Id": "fixture", "Image": "sha256:fixture",
             "RestartCount": 0, "HostConfig": {"PortBindings": {}}, "Config": {},
             "NetworkSettings": {"Networks": {"private": {}}}, "Mounts": deepcopy(mounts)}
    container = SimpleNamespace(attrs=attrs, reload=lambda: None)
    runtime = object.__new__(SliceRuntime)
    original = runtime._snapshot(container)
    attrs["Mounts"].reverse()
    assert runtime._snapshot(container) == original
    attrs["Mounts"][0]["RW"] = False
    assert runtime._snapshot(container) != original


@pytest.mark.parametrize("field,value", [("RestartCount", 1), ("Image", "sha256:other")])
def test_snapshot_binds_restart_and_image(field, value):
    attrs = {"State": {"Status": "running", "StartedAt": "fixed"}, "Id": "fixture", "Image": "sha256:fixture",
             "RestartCount": 0, "HostConfig": {}, "Config": {}, "NetworkSettings": {"Networks": {}}, "Mounts": []}
    container = SimpleNamespace(attrs=attrs, reload=lambda: None)
    runtime = object.__new__(SliceRuntime)
    original = runtime._snapshot(container)
    attrs[field] = value
    assert runtime._snapshot(container) != original


@pytest.fixture
def human_approval(tmp_path, monkeypatch):
    results = tmp_path / "results"
    results.mkdir(mode=0o700)
    decision_id = str(uuid4())
    write_new(results / f"decision-{decision_id}.json", {"decisionId": decision_id, "acceptanceSha256": "a" * 64,
        "actions": ["ACCEPT_IDENTITY", "APPROVE_PROFILE_AND_ACCEPT_BIFROST"]})
    state = {"instance": "fixture"}
    container = Mock()
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = canonical({"status": "IDENTITY_AND_PROFILE_APPROVED"})
    client = Mock()
    client.containers.run.return_value = container
    runtime = SimpleNamespace(directory=tmp_path, plan={"mode": "live", "pythonImage": "sha256:fixture"},
                              client=client, verify=Mock(return_value=state))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "ПРИНИМАЮ")
    monkeypatch.setattr(cli, "latest_session", lambda: tmp_path / "fixture-session.json")
    return runtime, decision_id, state, container


def test_runtime_change_during_human_review_prevents_owner_process(human_approval):
    runtime, decision_id, state, _ = human_approval
    runtime.verify.side_effect = [state, SliceRefused("RUNTIME_CHANGED")]
    with pytest.raises(SliceRefused, match="RUNTIME_CHANGED"):
        cli.approve(runtime, decision_id)
    runtime.client.containers.run.assert_not_called()


def test_drift_after_owner_commit_is_reported_as_uncertain_not_rollback(human_approval):
    runtime, decision_id, state, container = human_approval
    runtime.verify.side_effect = [state, state, SliceRefused("RUNTIME_CHANGED")]
    with pytest.raises(SliceRefused, match="APPROVAL_MAY_HAVE_COMMITTED"):
        cli.approve(runtime, decision_id)
    container.remove.assert_called_once_with(force=True)


def test_declining_human_review_opens_no_owner_process(human_approval, monkeypatch):
    runtime, decision_id, _, _ = human_approval
    monkeypatch.setattr("builtins.input", lambda prompt: "НЕТ")
    with pytest.raises(SliceRefused, match="HUMAN_DECLINED"):
        cli.approve(runtime, decision_id)
    runtime.client.containers.run.assert_not_called()


def test_cleanup_continues_after_previously_removed_owned_resources(tmp_path):
    write_new(tmp_path / "runtime.json", {"instance": "fixture", "containers": {"a": {"id": "present"}, "b": {"id": "gone"}},
                                          "networks": ["present-network", "gone-network"]})
    runtime = object.__new__(SliceRuntime)
    runtime.directory = tmp_path
    runtime.client = Mock()
    container, network = Mock(), Mock()
    container.labels = {"ai_res.instance": "fixture"}
    network.attrs = {"Labels": {"ai_res.instance": "fixture"}}
    runtime.client.containers.get.side_effect = [docker.errors.NotFound("fixture"), container]
    runtime.client.networks.get.side_effect = [docker.errors.NotFound("fixture"), network]
    runtime.stop()
    container.remove.assert_called_once_with(force=True)
    network.remove.assert_called_once_with()
    runtime.client.containers.get.side_effect = docker.errors.NotFound("fixture")
    runtime.client.networks.get.side_effect = docker.errors.NotFound("fixture")
    runtime.stop()  # completed cleanup is safely repeatable


def test_live_versions_share_one_fixed_wallet_and_require_canonical_paths(tmp_path, monkeypatch):
    base = tmp_path / "authorization"
    monkeypatch.setattr(common, "AUTHORIZATION_ROOT", base)
    assert common.wallet_directory(base, "live") == base / "wallet"
    assert common.wallet_directory(base / "versions/2", "live") == base / "wallet"
    assert common.wallet_directory(base / "versions/3", "live") == base / "wallet"
    assert common.wallet_directory(tmp_path / "fixture", "fixture") == tmp_path / "fixture/wallet"
    for invalid in (base / "versions/02", base / "versions/1", base / "versions/2/wallet", tmp_path / "other"):
        with pytest.raises(SliceRefused, match="AUTHORIZATION_PATH_REQUIRED"):
            common.wallet_directory(invalid, "live")


@pytest.fixture
def next_plan(tmp_path, monkeypatch):
    base = tmp_path / "authorization"
    base.mkdir(mode=0o700)
    (base / "wallet").mkdir(mode=0o700)
    child_directory = base / "versions/2"
    child_directory.mkdir(mode=0o700, parents=True)
    monkeypatch.setattr(common, "AUTHORIZATION_ROOT", base)
    monkeypatch.setattr(plans, "AUTHORIZATION_ROOT", base)
    parent = {"manifestSha256": "a" * 64}
    child = {"mode": "live", "parentManifestSha256": parent["manifestSha256"], "manifestSha256": "b" * 64,
             "admissionGeneration": 2, "immutableProfileSha256": digest(b"fixture-immutable"),
             "requests": {"new-probe": {"bodySha256": "d" * 64, "payloadBytes": 20}}}
    path = base / "wallet/ledger.jsonl"
    SliceLedger.initialize(path, manifest_sha256=parent["manifestSha256"],
                           requests={"old-probe": {"bodySha256": "c" * 64, "payloadBytes": 10}})
    write_new(base / "runtime.json", {"version": "slice01-runtime/1", "containers": {"caller": {"id": "old-caller"}}})
    client = Mock()
    client.containers.get.side_effect = docker.errors.NotFound("fixture")
    monkeypatch.setattr(plans.docker, "from_env", lambda **kwargs: client)
    monkeypatch.setattr(plans, "load_plan", lambda directory, for_execution=True: child if for_execution else parent)
    monkeypatch.setattr(plans, "_database_profile", lambda client: ('{"status":"APPROVED"}', "fixture-immutable", 1))
    return base, child_directory, child, parent, client


async def test_next_plan_activation_appends_to_existing_wallet_without_initialization(next_plan, monkeypatch):
    base, directory, child, _, _ = next_plan
    path = base / "wallet/ledger.jsonl"
    before = path.read_bytes()
    monkeypatch.setattr(plans.SliceLedger, "initialize", Mock(side_effect=AssertionError("reinitialization forbidden")))
    result = await plans.activate_version(directory)
    assert result["status"] == "NEXT_VERSION_AUTHORIZED_SAME_ACCOUNT"
    assert result["remainingUSD"] == "10"
    assert path.read_bytes().startswith(before)
    assert not (directory / "wallet").exists()
    assert (await SliceLedger(path, manifest_sha256=child["manifestSha256"]).balance()).attempts == 0


@pytest.mark.parametrize("case", ["running-parent", "wrong-parent", "wrong-generation", "changed-profile", "sql-inflight"])
async def test_next_plan_cannot_activate_with_stale_or_active_parent(next_plan, monkeypatch, case):
    base, directory, child, _, client = next_plan
    path = base / "wallet/ledger.jsonl"
    before = path.read_bytes()
    if case == "running-parent":
        client.containers.get.side_effect = None
    elif case == "wrong-parent":
        child["parentManifestSha256"] = "e" * 64
    elif case == "wrong-generation":
        child["admissionGeneration"] = 3
    elif case == "changed-profile":
        child["immutableProfileSha256"] = "e" * 64
    else:
        monkeypatch.setattr(plans, "_database_profile", Mock(side_effect=SliceRefused("ADMISSION_BUSY_OR_BLOCKED")))
    with pytest.raises(SliceRefused):
        await plans.activate_version(directory)
    assert path.read_bytes() == before


def test_identity_only_confirmation_selects_exact_offline_action(human_approval):
    runtime, decision_id, _, _ = human_approval
    runtime.plan["profileStatus"] = "APPROVED"
    path = runtime.directory / "results" / f"decision-{decision_id}.json"
    decision = decode(read_owned(path))
    decision["actions"] = ["ACCEPT_IDENTITY"]
    path.write_bytes(canonical(decision))
    cli.approve(runtime, decision_id, action="accept-identity")
    command = runtime.client.containers.run.call_args.args[1]
    assert command[4] == "accept-identity"


def test_missing_exact_action_list_never_opens_owner_process(human_approval):
    runtime, decision_id, _, _ = human_approval
    path = runtime.directory / "results" / f"decision-{decision_id}.json"
    decision = decode(read_owned(path))
    del decision["actions"]
    path.write_bytes(canonical(decision))
    with pytest.raises(SliceRefused, match="EXACT_HUMAN_ACTION_REQUIRED"):
        cli.approve(runtime, decision_id)
    runtime.client.containers.run.assert_not_called()


@pytest.mark.parametrize("stderr,saved", [
    (b'{"status":"SLICE_REFUSED","reason":"RESULT_REJECTED","stage":"VALIDATION"}', True),
    (b'ValueError: private content must stay out of receipts', False),
    (b'{"status":"SLICE_REFUSED","reason":"Bearer private-value"}', False),
])
def test_failed_producer_saves_only_bounded_machine_receipt(tmp_path, stderr, saved):
    (tmp_path / "results").mkdir(mode=0o700)
    runtime = object.__new__(SliceRuntime)
    runtime.directory = tmp_path
    runtime.plan = {"mode": "live"}
    runtime.verify = Mock(return_value={"containers": {"caller": {"id": "fixture"}}})
    runtime.client = Mock()
    runtime.client.containers.get.return_value.exec_run.return_value = SimpleNamespace(exit_code=2, output=(None, stderr))
    with pytest.raises(SliceRefused, match="PRODUCER_REFUSED"):
        runtime.execute("run")
    receipt = tmp_path / "results/run-failure.json"
    assert receipt.exists() is saved
    if saved:
        assert decode(read_owned(receipt))["reason"] == "RESULT_REJECTED"
