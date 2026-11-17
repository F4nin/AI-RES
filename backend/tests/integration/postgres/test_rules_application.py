# ruff: noqa: E501 -- explicit fixture SQL and commands
"""S18 real PolicyEngine + PostgreSQL acceptance; extra grants exist ONLY here."""
import hashlib
import json
from datetime import timedelta
from importlib import resources

import pytest

from ai_res.application.context import context_resolvers
from ai_res.application.rules import RulesApplicationService
from ai_res.modules.context.service import ContextApplicationService
from ai_res.modules.context.types import ContextItemKind, ContextRef
from ai_res.modules.idempotency.service import IdempotencyKeyRing, IdempotencyService
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceIdentity, ServiceName
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.config import parse_policy_config
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine

from .test_read_api import World

DEFINITION = {"schemaVersion": "1.0", "condition": {"op": "exists", "field": "context_item_count"},
              "effects": [{"kind": "REQUIRE", "target": "QA_CHECK"}]}
ACTIONS = ("propose", "validate", "submit", "approve", "publish", "retire", "suspend", "resume", "exception.approve", "exception.revoke")


@pytest.fixture
def rw(iam_world, tmp_path):
    return World(iam_world, tmp_path)


def fixture_policy(factory):
    data = json.loads(resources.files("ai_res.policy").joinpath("policy_config.json").read_text())
    data["version"] = "2026-11-17.180"
    for action in ACTIONS:
        data["actions"][f"rules.{action}"] = {"resourceType": "RULE", "allow": {"projectRoles": ["PROJECT_ADMIN"]},
                                                "requiresMfa": True, "humanOnly": True, "auditAllow": True}
    raw = json.dumps(data).encode()
    config = parse_policy_config(raw, hashlib.sha256(raw).hexdigest())
    return PolicyEnforcer(PolicyEngine(config, factory), factory, config, timeout_seconds=2)


async def services(rw, *, configured=True, separation=False):
    rw.sql("UPDATE project.project_memberships SET role_code='PROJECT_ADMIN',row_version=row_version+1 WHERE user_id=%s", rw.viewer)
    issued = await rw.services.sessions.create(rw.iam.org_a, rw.viewer, mfa_verified=True)
    actor = (await rw.services.sessions.authenticate(issued.token)).session
    assert actor is not None
    idem = IdempotencyService(IdempotencyKeyRing("k1", {"k1": bytes(range(32))}), timedelta(hours=1))
    context = ContextApplicationService(rw.services.factory, rw.services.enforcer, idem, context_resolvers)
    package = await context.build(actor, rw.ids["p1"], (ContextRef(ContextItemKind.REQUIREMENT_VERSION, rw.ids["reqv1"]),), key="rules-context-001")
    policy = fixture_policy(rw.services.factory) if configured else rw.services.enforcer
    return RulesApplicationService(rw.services.factory, policy, idem, context, separation_required=separation), actor, package


async def publish(service, actor, project, key="qa.check", definition=DEFINITION):
    item = await service.propose(actor, project, rule_key=key, definition=definition, key=f"rules-propose-{key}-001")
    item = await service.submit(actor, project, item.rule.version_id, expected_parent_version=item.parent_version,
                                expected_hash=item.rule.content_hash, key=f"rules-submit-{key}-001")
    item = await service.approve(actor, project, item.rule.version_id, expected_parent_version=item.parent_version,
                                 expected_hash=item.rule.content_hash, valid_from=utc_now(), valid_to=None, key=f"rules-approve-{key}-001")
    return await service.publish(actor, project, item.rule.version_id, expected_parent_version=item.parent_version,
                                  expected_hash=item.rule.content_hash, key=f"rules-publish-{key}-001")


async def test_published_registry_evaluation_replay_and_immutable_history(rw):
    service, actor, package = await services(rw)
    empty = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-eval-empty1")
    assert empty.result.status.value == "insufficient_data"
    rule = await publish(service, actor, rw.ids["p1"])
    evaluated = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-eval-pass01")
    assert evaluated.result.obligations == ("QA_CHECK",)
    assert evaluated.result.status.value == "pass_with_obligations"
    assert evaluated == await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-eval-pass01")
    assert evaluated.result == await service.replay(actor, rw.ids["p1"], evaluated.id)
    await service.retire(actor, rw.ids["p1"], rule.rule.version_id, expected_parent_version=rule.parent_version,
                         expected_hash=rule.rule.content_hash, key="rules-retire-001")
    assert (await service.retrieve(actor, rw.ids["p1"], evaluated.id)) == evaluated
    assert (await service.replay(actor, rw.ids["p1"], evaluated.id)) == evaluated.result
    assert rw.sql_one("SELECT count(*) FROM governance.rule_evaluations") == 2


async def test_draft_does_not_apply_and_suspend_resume_preserve_approval(rw):
    service, actor, package = await services(rw)
    draft = await service.propose(actor, rw.ids["p1"], rule_key="draft.qa", definition=DEFINITION, key="rules-onlydraft01")
    result = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-drafteval1")
    assert result.result.applied == () and result.result.obligations == ()
    assert draft.rule.status.value == "DRAFT"
    rule = await publish(service, actor, rw.ids["p1"])
    suspended = await service.suspend(actor, rw.ids["p1"], rule.rule.version_id, expected_parent_version=rule.parent_version,
                                       expected_hash=rule.rule.content_hash, key="rules-suspend-01")
    assert (await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-suspend-ev1")).result.obligations == ()
    await service.resume(actor, rw.ids["p1"], rule.rule.version_id, expected_parent_version=suspended.parent_version,
                         expected_hash=rule.rule.content_hash, key="rules-resume-001")
    assert (await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-resumed-e1")).result.obligations == ("QA_CHECK",)


async def test_packaged_unknown_management_action_denies_without_rule(rw):
    service, actor, _ = await services(rw, configured=False)
    with pytest.raises(ProblemError) as caught:
        await service.propose(actor, rw.ids["p1"], rule_key="forbidden", definition=DEFINITION, key="rules-prod-deny1")
    assert caught.value.code in {ErrorCode.ACCESS_DENIED, ErrorCode.RESOURCE_NOT_FOUND}
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 0


async def test_unconfigured_separation_policy_cannot_activate(rw):
    service, actor, _ = await services(rw, separation=None)
    draft = await service.propose(actor, rw.ids["p1"], rule_key="no.authority", definition=DEFINITION, key="rules-noauthor-1")
    submitted = await service.submit(actor, rw.ids["p1"], draft.rule.version_id, expected_parent_version=draft.parent_version,
                                     expected_hash=draft.rule.content_hash, key="rules-noauthor-2")
    with pytest.raises(ProblemError):
        await service.approve(actor, rw.ids["p1"], submitted.rule.version_id, expected_parent_version=submitted.parent_version,
                              expected_hash=submitted.rule.content_hash, valid_from=utc_now(), valid_to=None, key="rules-noauthor-3")
    assert rw.sql_one("SELECT count(*) FROM governance.rule_versions WHERE status='APPROVED'") == 0


async def test_manager_identity_cannot_human_approve(rw):
    service, _, _ = await services(rw)
    manager = ServiceIdentity(name=ServiceName.MANAGER_RUNTIME, audience=ServiceName.API, expires_at=utc_now()+timedelta(minutes=1))
    with pytest.raises(ProblemError) as caught:
        await service.propose(manager, rw.ids["p1"], rule_key="manager", definition=DEFINITION, key="rules-manager001")
    assert caught.value.code == ErrorCode.AUTHENTICATION_REQUIRED


async def test_cross_project_read_and_revoked_actor_cannot_replay(rw):
    service, actor, package = await services(rw)
    result = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-read-eval1")
    with pytest.raises(ProblemError) as caught:
        await service.retrieve(actor, rw.ids["p2"], result.id)
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND
    rw.sql("UPDATE project.project_memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", rw.viewer)
    with pytest.raises(ProblemError):
        await service.replay(actor, rw.ids["p1"], result.id)


async def test_validation_report_persists_without_publishing(rw):
    service, actor, _ = await services(rw)
    item = await service.propose(actor, rw.ids["p1"], rule_key="validate.qa", definition=DEFINITION, key="rules-validation-1")
    validated = await service.validate(actor, rw.ids["p1"], item.rule.version_id, expected_parent_version=item.parent_version,
                                       expected_hash=item.rule.content_hash, key="rules-validation-2")
    assert validated.validation_id is not None
    assert validated.rule.status.value == "DRAFT" and validated.parent_version == item.parent_version
    report = await service.validation_report(actor, rw.ids["p1"], validated.validation_id)
    assert report.valid and report.proposal_content_hash == item.rule.content_hash
    with pytest.raises(ProblemError):
        await service.validation_report(actor, rw.ids["p2"], validated.validation_id)


async def test_human_exact_exception_revocation_and_historical_replay(rw):
    from uuid import uuid4

    service, actor, package = await services(rw)
    target = await publish(service, actor, rw.ids["p1"])
    # System permission is installed by the test platform owner, never runtime.
    parent, version = uuid4(), uuid4()
    rw.sql("INSERT INTO governance.rules (id,level,rule_key,title) VALUES (%s,'SYSTEM','platform.exception','Exception policy')", parent)
    rw.sql("INSERT INTO governance.rule_versions (id,rule_id,level,version_number,condition,action,author_type) "
           "VALUES (%s,%s,'SYSTEM',1,%s::jsonb,%s::jsonb,'USER')",
           version, parent, json.dumps(DEFINITION["condition"]), json.dumps({"schemaVersion":"1.0","effects":[{"kind":"ALLOW_EXCEPTION","target":"qa.check"}]}))
    rw.sql("UPDATE governance.rule_versions SET status='PROPOSED' WHERE id=%s", version)
    rw.sql("UPDATE governance.rule_versions SET status='APPROVED',approver_user_id=%s,approved_at=now()-interval '1 hour',valid_from=now()-interval '1 hour' WHERE id=%s", actor.user_id, version)
    exception = await service.approve_exception(actor, rw.ids["p1"], package.version_id, target.rule.version_id,
        expected_hash=target.rule.content_hash, effect_hash=target.rule.effects[0].content_hash, permission_version_id=version,
        valid_to=utc_now()+timedelta(hours=1), reason_code="RISK_ACCEPTED", risk_refs=(rw.ids["reqv1"],),
        compensation_refs=(rw.ids["reqv1"],), key="rules-exception-1")
    result = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-exception-e1")
    assert result.result.status.value == "pass" and len(result.result.waived) == 1
    assert result.result.waived[0].exception_id == exception.id
    revoked = await service.revoke_exception(actor, rw.ids["p1"], exception.id, key="rules-exception-r1")
    assert revoked.revoked_at is not None
    assert (await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-exception-e2")).result.obligations == ("QA_CHECK",)
    assert await service.replay(actor, rw.ids["p1"], result.id) == result.result


async def test_audit_failure_rolls_back_rule_and_receipt(rw, monkeypatch):
    from ai_res.modules.audit.writer import SqlAuditWriter

    service, actor, _ = await services(rw)
    original = SqlAuditWriter.write

    async def fail_rule_audit(self, record):
        if record.action == "RULE_PROPOSE":
            raise RuntimeError("audit unavailable")
        return await original(self, record)

    monkeypatch.setattr(SqlAuditWriter, "write", fail_rule_audit)
    with pytest.raises(RuntimeError):
        await service.propose(actor, rw.ids["p1"], rule_key="audit.rollback", definition=DEFINITION, key="audit-rollback-01")
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 0
    assert rw.sql_one("SELECT count(*) FROM governance.rule_versions") == 0
    assert rw.sql_one("SELECT count(*) FROM audit.audit_events WHERE action='RULES_OPERATION_FAILED'") == 1


async def test_policy_outage_cannot_create_rule(rw):
    service, actor, _ = await services(rw)

    class Unavailable:
        async def decide(self, request):
            raise RuntimeError("policy unavailable")

    service._policy = PolicyEnforcer(Unavailable(), rw.services.factory, None, timeout_seconds=1)
    with pytest.raises(ProblemError) as caught:
        await service.propose(actor, rw.ids["p1"], rule_key="policy.outage", definition=DEFINITION, key="policy-outage-01")
    assert caught.value.code == ErrorCode.POLICY_ENGINE_UNAVAILABLE
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 0


async def test_context_access_is_rechecked_after_initial_load(rw, monkeypatch):
    service, actor, package = await services(rw)
    original = service._context.retrieve

    async def revoke_after_load(*args, **kwargs):
        result = await original(*args, **kwargs)
        rw.sql("UPDATE project.project_memberships SET status='REVOKED',row_version=row_version+1 WHERE user_id=%s", rw.viewer)
        return result

    monkeypatch.setattr(service._context, "retrieve", revoke_after_load)
    with pytest.raises(ProblemError) as caught:
        await service.evaluate(actor, rw.ids["p1"], package.version_id, key="context-reauthorize1")
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert rw.sql_one("SELECT count(*) FROM governance.rule_evaluations") == 0


async def test_existing_org_parent_cannot_use_project_grants(rw):
    from uuid import uuid4

    service, actor, _ = await services(rw)
    parent = uuid4()
    rw.sql("INSERT INTO governance.rules (id,level,organization_id,rule_key,title) VALUES (%s,'ORGANIZATION',%s,'org.existing','Policy')", parent, actor.organization_id)
    with pytest.raises(ProblemError) as caught:
        await service.propose(actor, rw.ids["p1"], rule_key="org.existing", definition=DEFINITION, rule_id=parent,
                              expected_parent_version=1, key="existing-org-deny01")
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert rw.sql_one("SELECT count(*) FROM governance.rule_versions") == 0


async def test_rules_trace_correlation_metrics_and_audit_exclude_source_content(rw, monkeypatch):
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    import ai_res.application.rules as instrumented

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("s18-test")
    reader = InMemoryMetricReader()
    meters = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(instrumented, "_tracer", tracer)
    monkeypatch.setattr(instrumented, "_counter", meters.get_meter("s18-test").create_counter("ai_res.rules.operations"))
    service, actor, package = await services(rw)
    try:
        with tracer.start_as_current_span("parent") as parent:
            result = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="rules-telemetry-01")
        child = next(span for span in exporter.get_finished_spans() if span.name == "rules.evaluate")
        assert child.parent.span_id == parent.context.span_id and child.context.trace_id == parent.context.trace_id
        assert not child.events and not child.attributes
        points = [point for rm in reader.get_metrics_data().resource_metrics for sm in rm.scope_metrics for metric in sm.metrics for point in metric.data.data_points]
        assert points and all(dict(point.attributes) == {"operation": "evaluate", "outcome": "insufficient_data"} for point in points)
        audit = rw.sql_one("SELECT details::text FROM audit.audit_events WHERE action='RULES_EVALUATED'")
        assert str(package.version_id) in audit and 'engineVersion' in audit
        assert 'The system shall' not in audit and 'The system shall' not in result.input_json
        assert set(json.loads(audit)) == {"engineVersion", "contextVersionRef", "resultCode", "rulesetHash"}
    finally:
        provider.shutdown()
        meters.shutdown()


async def test_project_grant_cannot_read_org_validation_report(rw):
    from ai_res.application.rules import FACT_SCHEMA
    from ai_res.db.session import UnitOfWork
    from ai_res.modules.rules.registry import RuleRegistry
    from ai_res.modules.rules.repository import RulesRepository
    from ai_res.modules.rules.validation import validate_rule

    service, actor, _ = await services(rw)
    async with UnitOfWork(rw.services.factory) as uow:
        await uow.with_tenant(actor.organization_id)
        repo = RulesRepository(uow.session)
        parent = await repo.create_rule(actor.organization_id, None, rule_key="org.validation", title="Policy", level="ORGANIZATION", created_by=actor.user_id)
        row = await repo.create_version(parent, 1, condition=DEFINITION["condition"], action={"schemaVersion":"1.0","effects":DEFINITION["effects"]}, author_id=actor.user_id)
        rule = RuleRegistry(uow.session, FACT_SCHEMA).snapshot_from_row(row)
        report = validate_rule(rule, FACT_SCHEMA, ())
        report_id = await repo.save_validation(organization_id=actor.organization_id, project_id=None, proposal_version_id=rule.version_id,
            proposal_hash=rule.content_hash, basis_hash=report.basis_fingerprint, basis={"schema":FACT_SCHEMA.to_dict(),"rules":[]},
            result=report.to_dict(), actor_id=actor.user_id, at=utc_now())
    with pytest.raises(ProblemError) as caught:
        await service.validation_report(actor, rw.ids["p1"], report_id)
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND
