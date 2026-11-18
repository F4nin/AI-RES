"""Actual pinned Bifrost -> real relay/codec -> synthetic MockTransport provider.

The network is internal with no external route or published ports. Probe helpers
run INSIDE it. Existing Compose services/secrets are never used or changed.
The accounting control is a TEST DOUBLE, so this is wire compatibility evidence
only. Real service auth/TLS/PostgreSQL have their own integration tests.
"""
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import time
from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import docker
import pytest
from docker.utils.build import exclude_paths
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

REPO = Path(__file__).resolve().parents[3]
IMAGE = "maximhq/bifrost:v2.5.1@sha256:5ec9873acaf1687556b6e4dd854b92b539d9debf87a5a683b66338648b84d3c8"
AUTH = "synthetic-relay-credential-" + "a" * 40
_CACHE_LABEL = "ai-res.candidate-wire-fixture.context-sha256"
_MAX_IGNORE_BYTES = 65_536
_MAX_BUILD_FILE_BYTES = 4_194_304
_MAX_BUILD_CONTEXT_BYTES = 33_554_432


def _bounded_build_input(path: Path, limit: int) -> tuple[bytes, int]:
    """Check the opened descriptor BEFORE reading even the ignore rules.

    Nonblocking open makes a FIFO fail without a writer. No symlink target or
    nonregular/oversize input is read. Size and byte-count checks also refuse a
    file that changes size while this exact build snapshot is being captured.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= limit:
                raise OSError
            content = source.read(limit + 1)
            if len(content) != info.st_size or len(content) > limit:
                raise OSError
            return content, stat.S_IMODE(info.st_mode)
    except (OSError, ValueError):
        raise AssertionError("Candidate fixture requires a bounded regular build input.") from None


def _fixture_build_context(backend: Path) -> bytes:
    """Snapshot precisely the existing Dockerfile's host COPY inputs.

    The same deterministic tar bytes are hashed AND sent to Docker, so dirty
    source cannot be paired with an unrelated HEAD-based cache key. Docker's own
    ignore matcher applies; secrets/tests/caches never enter this small context.
    A future COPY of another input fails to build until this scope is updated.
    """
    required = {"Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock", "alembic.ini"}
    captured = {name: _bounded_build_input(backend / name, _MAX_IGNORE_BYTES if name == ".dockerignore" else _MAX_BUILD_FILE_BYTES)
                for name in sorted(required)}
    try:
        patterns = captured[".dockerignore"][0].decode("utf-8").splitlines()
    except UnicodeError:
        raise AssertionError("Candidate fixture ignore rules require bounded regular build input UTF-8.") from None
    allowed = exclude_paths(str(backend), patterns)
    assert required <= allowed, "Required candidate fixture build input is excluded."
    selected = sorted(name for name in allowed if name in required or name == "src" or name.startswith("src/"))
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name in selected:
            source = backend / name
            assert not source.is_symlink(), "Candidate fixture COPY input cannot be a symlink."
            info = tarfile.TarInfo(name)
            if name not in required and source.is_dir():
                info.mode = stat.S_IMODE(source.stat().st_mode)
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            else:
                content, info.mode = captured[name] if name in captured else _bounded_build_input(source, _MAX_BUILD_FILE_BYTES)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
            assert stream.tell() <= _MAX_BUILD_CONTEXT_BYTES, "Candidate fixture context exceeds its bounded size."
    content = stream.getvalue()
    assert len(content) <= _MAX_BUILD_CONTEXT_BYTES, "Candidate fixture context exceeds its bounded size."
    return content


def _fixture_image(backend: Path = REPO / "backend") -> str:
    """Build/reuse our local cache only; never pull or retag the main API image.

    Existing Dockerfile bases are pinned and dependencies use uv --locked. Build
    may obtain those declared inputs; all actual probe containers stay internal.
    The task-specific tag is retained as a reusable local build cache, while the
    container always starts by immutable image ID. No image/volume prune occurs.
    """
    context = _fixture_build_context(backend)
    digest = hashlib.sha256(context).hexdigest()
    tag = "ai-res-candidate-wire-fixture:" + digest
    client = docker.from_env()
    try:
        try:
            image = client.images.get(tag)
        except docker.errors.ImageNotFound:
            try:
                image, _ = client.images.build(fileobj=io.BytesIO(context), custom_context=True, dockerfile="Dockerfile", tag=tag,
                                               labels={_CACHE_LABEL: digest}, pull=False, rm=True, forcerm=True)
            except docker.errors.BuildError:
                raise AssertionError("Candidate fixture image build failed; no runtime tests were skipped.") from None
        assert image.labels.get(_CACHE_LABEL) == digest, "Candidate fixture cache label differs from its exact build context."
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", image.id), "Candidate fixture requires an immutable local image ID."
        return str(image.id)
    finally:
        client.close()


def _wait(container, command):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        code, _ = container.exec(command)
        if code == 0:
            return
        time.sleep(0.1)
    raise AssertionError("Isolated synthetic fixture did not become ready.")


@pytest.fixture(scope="module")
def pinned_bifrost(tmp_path_factory) -> Iterator[SimpleNamespace]:
    directory = tmp_path_factory.mktemp("flash-bifrost-wire")
    template = (REPO / "infra/llm_poc/config.template.json").read_text()
    key = "sk-bf-" + uuid4().hex + uuid4().hex
    config = template.replace("$LLM_RELAY_AUTH", AUTH).replace("$BIFROST_ADMIN_PASSWORD", uuid4().hex + uuid4().hex)
    config = config.replace("sk-bf-$BIFROST_VIRTUAL_KEY", key)
    config_file = directory / "config.json"
    config_file.write_text(config)
    config_file.chmod(0o644)  # synthetic-only fixture, readable by nonroot container UID
    fixture_image_id = _fixture_image()
    with ExitStack() as stack:
        network = stack.enter_context(Network(docker_network_kw={"internal": True}))
        relay = DockerContainer(fixture_image_id).with_network(network).with_network_aliases("llm-gateway")
        relay.with_env("PYTHONPATH", "/candidate-src").with_env("PYTHONDONTWRITEBYTECODE", "1")
        relay.with_volume_mapping(REPO / "backend/src", "/candidate-src", "ro")
        relay.with_volume_mapping(REPO / "infra/llm_poc/relay.py", "/fixture/relay.py", "ro")
        relay.with_volume_mapping(REPO / "backend/tests/fixtures/flash_candidate_fake_relay.py", "/fixture/fake.py", "ro")
        relay.with_volume_mapping(config_file, "/fixture/config.json", "ro")
        relay.with_kwargs(user="10001:10001", read_only=True, cap_drop=["ALL"], security_opt=["no-new-privileges:true"],
                          mem_limit="256m", pids_limit=128)
        relay.tmpfs = {"/tmp": "uid=10001,gid=10001,mode=0700"}
        relay.with_command(["python", "-B", "/fixture/fake.py"])
        stack.enter_context(relay)
        _wait(relay, ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=1)"])
        bifrost = DockerContainer(IMAGE).with_network(network).with_network_aliases("bifrost-poc")
        bifrost.with_volume_mapping(config_file, "/fixture/config.json", "ro")
        for resource in ("pricing.json", "model-parameters.json", "mcp-library.json"):
            bifrost.with_volume_mapping(REPO / "infra/llm_poc" / resource, "/etc/bifrost/" + resource, "ro")
        bifrost.with_kwargs(entrypoint=["/bin/sh", "-c"], user="1000:1000", read_only=True, cap_drop=["ALL"],
                            security_opt=["no-new-privileges:true"], mem_limit="512m", pids_limit=256)
        bifrost.tmpfs = {"/app/data": "uid=1000,gid=1000,mode=0700", "/tmp": "uid=1000,gid=1000,mode=0700"}
        bifrost.with_command(["cp /fixture/config.json /app/data/config.json && exec /app/main -app-dir /app/data "
                              "-host 0.0.0.0 -port 8080 -log-level error -log-style json"])
        stack.enter_context(bifrost)
        _wait(bifrost, ["wget", "-q", "--spider", "http://127.0.0.1:8080/health"])
        assert network._unwrap_network.attrs["Internal"] is True
        for container in (relay, bifrost):
            wrapped = container.get_wrapped_container()
            wrapped.reload()
            assert set(wrapped.attrs["NetworkSettings"]["Networks"]) == {network.name}
            assert not wrapped.attrs["HostConfig"]["PortBindings"]
            assert not any(wrapped.attrs["NetworkSettings"]["Ports"].values())
        yield SimpleNamespace(relay=relay)


@pytest.mark.parametrize("case", ["TEXT", "JSON", "TOOL"])
def test_actual_pinned_bifrost_native_conversion_reaches_exact_canonical_relay_bytes(pinned_bifrost, case):
    code, raw = pinned_bifrost.relay.exec(["python", "-B", "/fixture/fake.py", "--probe", case])
    assert code == 0, "Synthetic probe helper failed (no raw process output is exported)."
    captured = json.loads(raw)
    result, facts, digest = captured["evidence"], captured["diagnostics"], captured["expected_sha256"]
    assert "error" not in result, "Pinned Bifrost wire refused; metadata=" + json.dumps(captured, sort_keys=True)
    assert result["outcome"] == "COMPLETE" and result["capabilityOk"]
    assert result["identity"]["provider"] == "deepseek" and result["identity"]["routingModelId"] == "deepseek-flash"
    assert result["identity"]["responseModelId"] == "deepseek-flash"
    assert result["identity"]["fingerprint"] == {"presence": "VALUE", "value": "synthetic-wire-fingerprint"}
    assert result["usage"] == {"inputTokens": 12, "outputTokens": 2}
    assert sum(item.get("canonical_sha256") == digest for item in facts["received"]) == 1
    assert facts["claims"].count(digest) == 1
    assert sum(item["sha256"] == digest for item in facts["outgoing"]) == 1
    assert sum(item["body_sha256"] == digest and item["outcome"] == "KNOWN" for item in facts["settlements"]) == 1


@pytest.mark.parametrize("case", ["ALT_FLASH", "ALT_PRO"])
def test_actual_bifrost_changed_response_label_is_refused_as_server_side_fallback(pinned_bifrost, case):
    code, raw = pinned_bifrost.relay.exec(["python", "-B", "/fixture/fake.py", "--probe", case])
    assert code == 0, "Synthetic probe helper failed."
    captured = json.loads(raw)
    assert captured["evidence"] == {"error": "INVALID_RESPONSE"}
    assert captured["bifrost_response"][0]["routing_checks"]["server_side_fallback_is_response_model"] is True
    digest, facts = captured["expected_sha256"], captured["diagnostics"]
    assert facts["claims"].count(digest) == 1 and sum(item["sha256"] == digest for item in facts["outgoing"]) == 1


@pytest.mark.parametrize("case,outcome", [("CANCEL", "CANCELLED"), ("TIMEOUT", "TIMEOUT")])
def test_actual_bifrost_controlled_cancel_and_timeout_are_not_completed_evidence(pinned_bifrost, case, outcome):
    code, raw = pinned_bifrost.relay.exec(["python", "-B", "/fixture/fake.py", "--probe", case])
    assert code == 0, "Synthetic probe helper failed."
    captured = json.loads(raw)
    result, facts, digest = captured["evidence"], captured["diagnostics"], captured["expected_sha256"]
    assert "error" not in result, "Pinned Bifrost control refused; metadata=" + json.dumps(captured, sort_keys=True)
    assert result["outcome"] == outcome and result["capabilityOk"] is False and result["usage"] is None
    assert facts["claims"].count(digest) == 1 and sum(item["sha256"] == digest for item in facts["outgoing"]) == 1


def test_actual_pinned_bifrost_refuses_bifrost_terminal_fingerprint_loss(pinned_bifrost):
    """Known SDK compatibility gap, NOT successful SSE capability evidence.

    The first positive SSE run failed despite identical provider fingerprints on
    every fake upstream frame. This regression preserves the measured failure:
    pinned Bifrost emits an empty terminal fingerprint and our adapter refuses.
    A passing test cannot establish SSE readiness or close model admission.
    """
    code, raw = pinned_bifrost.relay.exec(["python", "-B", "/fixture/fake.py", "--probe", "SSE"])
    assert code == 0, "Synthetic probe helper failed."
    captured = json.loads(raw)
    assert captured["evidence"] == {"error": "INVALID_RESPONSE"}
    events = captured["bifrost_response"][0]["events"]
    assert events[0]["fingerprint_matches"] is True and events[0]["fingerprint_empty"] is False
    terminal = next(event for event in events if event.get("finish_stop"))
    assert terminal["usage_present"] is True and terminal["fingerprint_empty"] is True
    assert terminal["fingerprint_matches"] is False
    assert all(event["provider_ref_matches"] and event["response_model_matches"] for event in events)
    digest, facts = captured["expected_sha256"], captured["diagnostics"]
    assert sum(item.get("canonical_sha256") == digest for item in facts["received"]) == 1
    assert facts["claims"].count(digest) == 1
    assert sum(item["sha256"] == digest for item in facts["outgoing"]) == 1
    settlements = [item for item in facts["settlements"] if item["body_sha256"] == digest]
    assert settlements == [{"outcome": "KNOWN", "body_sha256": digest, "input_tokens": 12, "output_tokens": 2}]
    assert facts["requests"][-1]["cache_control_is_no_cache"] is True


def _synthetic_build_tree(directory):
    (directory / "src/pkg").mkdir(parents=True)
    for name, content in {"Dockerfile": "FROM scratch\nCOPY src /src\n", ".dockerignore": "secrets\n**/__pycache__\ntests\n",
                          "pyproject.toml": "synthetic manifest", "uv.lock": "synthetic lock", "alembic.ini": "synthetic config",
                          "src/pkg/module.py": "synthetic source"}.items():
        (directory / name).write_text(content)


def test_fixture_build_context_tracks_dirty_copied_source_and_locked_inputs(tmp_path):
    _synthetic_build_tree(tmp_path)
    original = _fixture_build_context(tmp_path)
    assert original == _fixture_build_context(tmp_path)
    (tmp_path / "src/pkg/module.py").write_text("changed uncommitted source")
    assert _fixture_build_context(tmp_path) != original
    changed = _fixture_build_context(tmp_path)
    (tmp_path / "uv.lock").write_text("changed lock")
    assert _fixture_build_context(tmp_path) != changed


def test_fixture_build_context_obeys_dockerignore_and_excludes_unrelated_secret_data(tmp_path):
    _synthetic_build_tree(tmp_path)
    original = _fixture_build_context(tmp_path)
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets/private").write_text("synthetic hidden material")
    (tmp_path / "src/pkg/__pycache__").mkdir()
    (tmp_path / "src/pkg/__pycache__/cache.pyc").write_bytes(b"ignored cache")
    (tmp_path / "src/pkg/notes.pem").write_text("synthetic excluded input")
    (tmp_path / ".dockerignore").write_text((tmp_path / ".dockerignore").read_text() + "src/pkg/notes.pem\n")
    current = _fixture_build_context(tmp_path)
    assert current != original  # Ignore rules themselves affect the build contract.
    with tarfile.open(fileobj=io.BytesIO(current)) as archive:
        names = archive.getnames()
    assert "src/pkg/module.py" in names and "uv.lock" in names
    assert all(not any(part in name for part in ("secrets", "__pycache__", ".pem")) for name in names)


def test_fixture_build_context_refuses_copy_input_symlink_escape(tmp_path):
    _synthetic_build_tree(tmp_path)
    (tmp_path / "src/pkg/link").symlink_to(tmp_path / "uv.lock")
    with pytest.raises(AssertionError, match="symlink"):
        _fixture_build_context(tmp_path)


@pytest.mark.parametrize("cached", [False, True])
def test_fixture_image_builds_or_reuses_only_its_local_content_tag_and_returns_immutable_id(tmp_path, monkeypatch, cached):
    _synthetic_build_tree(tmp_path)
    context = _fixture_build_context(tmp_path)
    digest = hashlib.sha256(context).hexdigest()
    image = SimpleNamespace(id="sha256:" + "1" * 64, labels={_CACHE_LABEL: digest})
    calls = []

    class Images:
        def get(self, tag):
            calls.append(("get", tag))
            if not cached:
                raise docker.errors.ImageNotFound("fixture missing locally")
            return image

        def build(self, **options):
            calls.append(("build", options))
            assert options["fileobj"].read() == context and options["custom_context"] is True
            assert options["pull"] is False and options["labels"] == {_CACHE_LABEL: digest}
            assert options["tag"] == "ai-res-candidate-wire-fixture:" + digest
            return image, iter(())

    monkeypatch.setattr(docker, "from_env", lambda: SimpleNamespace(images=Images(), close=lambda: calls.append(("close",))))
    assert _fixture_image(tmp_path) == image.id
    assert calls[0] == ("get", "ai-res-candidate-wire-fixture:" + digest)
    assert sum(call[0] == "build" for call in calls) == (0 if cached else 1)
    assert calls[-1] == ("close",)


def test_fixture_dockerignore_symlink_is_refused_before_any_unbounded_path_read(tmp_path, monkeypatch):
    _synthetic_build_tree(tmp_path)
    ignore = tmp_path / ".dockerignore"
    ignore.unlink()
    outside = tmp_path / "outside-ignore"
    outside.write_text("synthetic forbidden target")
    ignore.symlink_to(outside)
    original = Path.read_text

    class ForbiddenRead(RuntimeError):
        pass

    def guarded(path, *args, **kwargs):
        if path == ignore:
            raise ForbiddenRead("Unbounded .dockerignore read was attempted before safety validation.")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    with pytest.raises(AssertionError, match="bounded regular build input"):
        _fixture_build_context(tmp_path)


@pytest.mark.parametrize("kind", ["fifo", "directory", "oversize"])
@pytest.mark.parametrize("name", [".dockerignore", "uv.lock"])
def test_fixture_build_input_type_and_size_refuse_before_unbounded_read(tmp_path, kind, name):
    _synthetic_build_tree(tmp_path)
    path = tmp_path / name
    path.unlink()
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        with path.open("wb") as output:
            output.truncate((_MAX_IGNORE_BYTES if name == ".dockerignore" else _MAX_BUILD_FILE_BYTES) + 1)
    with pytest.raises(AssertionError, match="bounded regular build input"):
        _fixture_build_context(tmp_path)


def test_fixture_build_context_aggregate_limit_fails_closed(tmp_path, monkeypatch):
    _synthetic_build_tree(tmp_path)
    monkeypatch.setitem(_fixture_build_context.__globals__, "_MAX_BUILD_CONTEXT_BYTES", 2048)
    with pytest.raises(AssertionError, match="context exceeds"):
        _fixture_build_context(tmp_path)
