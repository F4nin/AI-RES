"""Read/composition tests only; actual PostgreSQL semantics have their own suite."""
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from ai_res.llm.admission import ObservedAdmissionCall
from ai_res.llm.errors import ModelProfileNotApproved
from ai_res.llm.observed_identity import ManagedVersions
from ai_res.llm.registry import ProfileIdentityMode
from ai_res.modules.model_registry.admission import AdmissionDenied, AdmissionTicket, AdmissionUnavailable
from ai_res.modules.model_registry.gateway_admission import ModelRegistryAdmission
from ai_res.modules.model_registry.repository import RegistryLoadError, load_model_registry

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def row(**changes):
    return SimpleNamespace(**(dict(
        id=UUID(int=110), profile_key="observed-fixture", profile_version=1, identity_mode="FLASH_OBSERVED",
        provider="deepseek", provider_model_id="deepseek-flash", pinned_model_version=None,
        capabilities=["CHAT", "STRUCTURED_OUTPUT", "TOOL_CALLING", "STREAMING"], context_window_tokens=4096, max_output_tokens=1024,
        data_classifications=["PUBLIC"], allowed_regions=["test"], egress="EXTERNAL", cost_currency=None, cost_input_per_million=None,
        cost_output_per_million=None, rate_limit_rpm=None, rate_limit_tpm=None, timeout_seconds=5, retry_class="NONE",
        fallback_group=None, evaluation_manifest_ref="synthetic-evaluation", status="APPROVED", approved_at=NOW, deprecated_at=None) | changes))


class Session:
    def __init__(self, *rows):
        self.rows = rows

    async def execute(self, statement):
        return self

    def all(self):
        return self.rows


async def test_loader_honestly_loads_approved_observed_and_preserves_immutable_rows():
    observed = row()
    immutable = row(id=UUID(int=120), profile_key="immutable-fixture", identity_mode="IMMUTABLE",
                    provider="fixture", provider_model_id="snapshot", pinned_model_version="snapshot")
    registry = await load_model_registry(Session(observed, immutable))
    p = registry.resolve(observed.id, NOW)
    assert p.identity_mode is ProfileIdentityMode.FLASH_OBSERVED and p.pinned_model_version is None
    assert registry.resolve(immutable.id, NOW).pinned_model_version == "snapshot"


@pytest.mark.parametrize("changes", [dict(provider_model_id="deepseek-v4-pro"), dict(pinned_model_version="alias"),
                                     dict(identity_mode="UNKNOWN"), dict(retry_class="BOUNDED"), dict(fallback_group="fallback")])
async def test_active_invalid_observed_row_fails_whole_registry_load(changes):
    with pytest.raises(RegistryLoadError):
        await load_model_registry(Session(row(**changes)))


async def test_candidate_and_deprecated_metadata_never_become_usable():
    candidate = row(status="CANDIDATE", approved_at=None)
    retired = row(id=UUID(int=120), profile_key="retired", status="RETIRED")
    registry = await load_model_registry(Session(candidate, retired))
    for p in registry.all():
        with pytest.raises(ModelProfileNotApproved):
            registry.resolve(p.id, NOW)


class Guard:
    def __init__(self, *, begin_error=None, finalize_error=None):
        self.calls = []
        self.begin_error, self.finalize_error = begin_error, finalize_error

    async def begin(self, profile_id, versions, *, request_ref):
        self.calls.append((profile_id, versions, request_ref))
        if self.begin_error:
            raise self.begin_error
        return AdmissionTicket(UUID(int=3), profile_id, versions.profile_version, 1, 1, request_ref, "d" * 64)

    async def finalize(self, ticket, observation):
        self.calls.append((ticket, observation))
        if self.finalize_error:
            raise self.finalize_error


async def fixture():
    p = (await load_model_registry(Session(row()))).resolve(UUID(int=110), NOW)
    request = SimpleNamespace(request_id="request-1", model_profile_id=p.id)
    versions = ManagedVersions("a" * 40, p.id, 1, "b" * 64, "c" * 64, None)
    return p, request, versions


@pytest.mark.parametrize("authorized", [False, None, 1])
async def test_authorizer_must_explicitly_allow_before_any_guard_mutation(authorized):
    p, request, versions = await fixture()
    guard = Guard()

    async def authorize(actual_profile, actual_request):
        assert actual_profile is p and actual_request is request
        return authorized

    adapter = ModelRegistryAdmission(guard, authorize=authorize, managed_versions=lambda p, r: versions)
    with pytest.raises(ModelProfileNotApproved):
        await adapter.begin(p, request)
    assert guard.calls == []


async def test_adapter_preserves_exact_receipt_and_never_opens_a_provider_transaction():
    p, request, versions = await fixture()
    guard = Guard()

    async def authorize(p, r):
        return True

    adapter = ModelRegistryAdmission(guard, authorize=authorize, managed_versions=lambda p, r: versions)
    call = await adapter.begin(p, request)
    assert call.managed_versions == versions and guard.calls == [(p.id, versions, request.request_id)]
    await adapter.finalize(call, b"")
    assert guard.calls[-1] == (call.ticket.ticket, b"")


@pytest.mark.parametrize("phase,error", [("begin", AdmissionDenied()), ("begin", AdmissionUnavailable()),
                                        ("finalize", AdmissionDenied()), ("finalize", AdmissionUnavailable())])
async def test_durable_guard_refusal_and_outage_cannot_publish_or_dispatch(phase, error):
    p, request, versions = await fixture()
    guard = Guard(begin_error=error if phase == "begin" else None, finalize_error=error if phase == "finalize" else None)

    async def authorize(p, r):
        return True

    adapter = ModelRegistryAdmission(guard, authorize=authorize, managed_versions=lambda p, r: versions)
    with pytest.raises(ModelProfileNotApproved) as caught:
        call = await adapter.begin(p, request)
        await adapter.finalize(call, b"")
    assert caught.value.possibly_billed is (phase == "finalize")


async def test_foreign_managed_versions_and_forged_ticket_refuse():
    p, request, versions = await fixture()
    guard = Guard()

    async def authorize(p, r):
        return True

    adapter = ModelRegistryAdmission(guard, authorize=authorize, managed_versions=lambda p, r:
                                     ManagedVersions("a" * 40, UUID(int=999), 1, "b" * 64, "c" * 64, None))
    with pytest.raises(ModelProfileNotApproved):
        await adapter.begin(p, request)
    with pytest.raises(ModelProfileNotApproved):
        await adapter.finalize(ObservedAdmissionCall(versions, object()), b"")
    assert guard.calls == []


@pytest.mark.parametrize("change", ["revoke", "policy-outage", "versions", "versions-outage"])
async def test_final_authorization_and_versions_are_revalidated_before_accepting_output(change):
    p, request, versions = await fixture()
    guard = Guard()
    final = False
    authorizations = []

    async def authorize(actual_profile, actual_request):
        assert actual_profile is p and actual_request is request
        authorizations.append(final)
        if final and change == "policy-outage":
            raise RuntimeError("synthetic-private-policy-error")
        return not (final and change == "revoke")

    def resolve(actual_profile, actual_request):
        assert actual_profile is p and actual_request is request
        if final and change == "versions-outage":
            raise RuntimeError("synthetic-private-config-error")
        return replace(versions, config_sha256="e" * 64) if final and change == "versions" else versions

    adapter = ModelRegistryAdmission(guard, authorize=authorize, managed_versions=resolve)
    call = await adapter.begin(p, request)
    final = True
    with pytest.raises(ModelProfileNotApproved) as caught:
        await adapter.finalize(call, b"")
    assert caught.value.possibly_billed and "synthetic-private" not in str(caught.value)
    assert authorizations == [False, True] and len(guard.calls) == 1


@pytest.mark.parametrize("change", ["revoke", "policy-outage", "versions"])
async def test_authority_changes_during_durable_finalize_cannot_publish_output(change):
    p, request, versions = await fixture()
    final = False

    class WaitingGuard(Guard):
        async def finalize(self, ticket, observation):
            nonlocal final
            await super().finalize(ticket, observation)
            final = True  # revoke while the DB transaction was waiting

    async def authorize(actual_profile, actual_request):
        assert actual_profile is p and actual_request is request
        if final and change == "policy-outage":
            raise RuntimeError("synthetic-private-policy-error")
        return not (final and change == "revoke")

    def resolve(actual_profile, actual_request):
        return replace(versions, config_sha256="e" * 64) if final and change == "versions" else versions

    adapter = ModelRegistryAdmission(WaitingGuard(), authorize=authorize, managed_versions=resolve)
    call = await adapter.begin(p, request)
    with pytest.raises(ModelProfileNotApproved) as caught:
        await adapter.finalize(call, b"")
    assert caught.value.possibly_billed and "synthetic-private" not in str(caught.value)
