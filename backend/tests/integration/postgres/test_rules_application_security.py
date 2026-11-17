# ruff: noqa: E501 -- explicit SQL and command arguments keep negative cases reviewable
"""S18 real PolicyEngine/PostgreSQL security, concurrency and scheduled publication."""
import asyncio
from datetime import timedelta

import pytest

from ai_res.application.rules import RulesApplicationService
from ai_res.modules.rules.types import RuleLevel
from ai_res.platform.clock import utc_now
from ai_res.platform.problems import ErrorCode, ProblemError

from .test_rules_application import DEFINITION, publish, services
from .test_rules_application import rw as _rw_fixture

pytestmark = pytest.mark.postgres
rw = _rw_fixture


async def test_exact_rule_hash_and_parent_cas_reject_without_partial_transition(rw):
    service, actor, _ = await services(rw)
    item = await service.propose(actor, rw.ids["p1"], rule_key="exact.binding", definition=DEFINITION, key="exact-binding-propose1")
    for wrong_hash, expected_parent, key in (("00" * 32, item.parent_version, "exact-binding-badhash1"),
                                             (item.rule.content_hash, item.parent_version + 1, "exact-binding-badcas01")):
        with pytest.raises(ProblemError) as caught:
            await service.submit(actor, rw.ids["p1"], item.rule.version_id, expected_hash=wrong_hash,
                                 expected_parent_version=expected_parent, key=key)
        assert caught.value.code == ErrorCode.VERSION_CONFLICT
    assert rw.sql_one("SELECT status FROM governance.rule_versions WHERE id=%s", item.rule.version_id) == "DRAFT"
    assert rw.sql_one("SELECT row_version FROM governance.rules WHERE id=%s", item.rule.rule_id) == item.parent_version
    assert rw.sql_one("SELECT count(*) FROM governance.rule_validation_reports") == 0
    submitted = await service.submit(actor, rw.ids["p1"], item.rule.version_id, expected_hash=item.rule.content_hash,
                                     expected_parent_version=item.parent_version, key="exact-binding-submit1")
    assert submitted.rule.status.value == "PROPOSED"


async def test_configured_author_separation_blocks_self_approval(rw):
    service, actor, _ = await services(rw, separation=True)
    draft = await service.propose(actor, rw.ids["p1"], rule_key="separate.author", definition=DEFINITION, key="separation-propose01")
    submitted = await service.submit(actor, rw.ids["p1"], draft.rule.version_id, expected_hash=draft.rule.content_hash,
                                     expected_parent_version=draft.parent_version, key="separation-submit001")
    with pytest.raises(ProblemError) as caught:
        await service.approve(actor, rw.ids["p1"], submitted.rule.version_id, expected_hash=submitted.rule.content_hash,
                              expected_parent_version=submitted.parent_version, valid_from=utc_now(), valid_to=None, key="separation-approve01")
    assert caught.value.code == ErrorCode.ACCESS_DENIED
    assert rw.sql_one("SELECT status FROM governance.rule_versions WHERE id=%s", submitted.rule.version_id) == "PROPOSED"
    assert rw.sql_one("SELECT approver_user_id FROM governance.rule_versions WHERE id=%s", submitted.rule.version_id) is None


@pytest.mark.parametrize("change", ["expired", "revoked", "mfa_removed"])
async def test_current_session_and_mfa_override_stale_authenticated_actor(rw, change):
    service, actor, _ = await services(rw)
    assert actor.mfa_verified_at is not None
    if change == "expired":
        rw.sql("UPDATE iam.sessions SET idle_expires_at=clock_timestamp()-interval '1 second',row_version=row_version+1 WHERE id=%s", actor.session_id)
    elif change == "revoked":
        rw.sql("UPDATE iam.sessions SET revoked_at=clock_timestamp(),revoked_reason='LOGOUT',row_version=row_version+1 WHERE id=%s", actor.session_id)
    else:
        rw.sql("UPDATE iam.sessions SET mfa_verified_at=NULL,row_version=row_version+1 WHERE id=%s", actor.session_id)
    with pytest.raises(ProblemError) as caught:
        await service.propose(actor, rw.ids["p1"], rule_key="stale.identity", definition=DEFINITION, key="stale-session-propose1")
    if change in {"expired", "revoked"}:
        assert caught.value.code == ErrorCode.AUTHENTICATION_REQUIRED
    else:
        assert caught.value.code in {ErrorCode.ACCESS_DENIED, ErrorCode.RESOURCE_NOT_FOUND}
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 0


async def test_project_management_grants_do_not_authorize_organization_rules(rw):
    service, actor, _ = await services(rw)
    for project, key in ((None, "org-rule-project-grant1"), (rw.ids["p1"], "org-rule-scope-mixup1")):
        with pytest.raises(ProblemError) as caught:
            await service.propose(actor, project, rule_key="organization.policy", definition=DEFINITION, key=key, level=RuleLevel.ORGANIZATION)
        assert caught.value.code in {ErrorCode.ACCESS_DENIED, ErrorCode.RESOURCE_NOT_FOUND}
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 0


async def test_same_idempotency_key_cannot_change_definition_or_create_second_rule(rw):
    service, actor, _ = await services(rw)
    item = await service.propose(actor, rw.ids["p1"], rule_key="idem.exact", definition=DEFINITION, key="rule-idempotency-key1")
    replay = await service.propose(actor, rw.ids["p1"], rule_key="idem.exact", definition=DEFINITION, key="rule-idempotency-key1")
    assert replay == item
    changed = {**DEFINITION, "effects": [{"kind": "REQUIRE", "target": "OTHER_CHECK"}]}
    with pytest.raises(ProblemError) as caught:
        await service.propose(actor, rw.ids["p1"], rule_key="idem.exact", definition=changed, key="rule-idempotency-key1")
    assert caught.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert rw.sql_one("SELECT count(*) FROM governance.rules") == 1
    assert rw.sql_one("SELECT count(*) FROM governance.rule_versions") == 1


async def test_concurrent_proposals_with_one_parent_cas_have_one_winner_and_no_gap(rw):
    service, actor, _ = await services(rw)
    first = await service.propose(actor, rw.ids["p1"], rule_key="concurrent.version", definition=DEFINITION, key="concurrent-version001")
    results = await asyncio.wait_for(asyncio.gather(*(
        service.propose(actor, rw.ids["p1"], rule_key="concurrent.version", definition=DEFINITION, key=f"concurrent-version-{number}",
                        rule_id=first.rule.rule_id, expected_parent_version=first.parent_version)
        for number in (2, 3)), return_exceptions=True), timeout=20)
    succeeded = [result for result in results if not isinstance(result, BaseException)]
    errors = [result for result in results if isinstance(result, BaseException)]
    assert len(succeeded) == 1 and len(errors) == 1
    assert isinstance(errors[0], ProblemError) and errors[0].code == ErrorCode.VERSION_CONFLICT
    assert rw.sql_one("SELECT array_agg(version_number ORDER BY version_number) FROM governance.rule_versions WHERE rule_id=%s", first.rule.rule_id) == [1, 2]
    assert rw.sql_one("SELECT last_version_number FROM governance.rules WHERE id=%s", first.rule.rule_id) == 2


async def test_scheduled_approval_preserves_previous_publication_until_due(rw):
    service, actor, package = await services(rw)
    previous = await publish(service, actor, rw.ids["p1"], key="scheduled.swap")
    replacement = {**DEFINITION, "effects": [{"kind": "REQUIRE", "target": "NEW_CHECK"}]}
    draft = await service.propose(actor, rw.ids["p1"], rule_key="scheduled.swap", definition=replacement, key="scheduled-nextdraft1",
                                  rule_id=previous.rule.rule_id, expected_parent_version=previous.parent_version)
    submitted = await service.submit(actor, rw.ids["p1"], draft.rule.version_id, expected_hash=draft.rule.content_hash,
                                     expected_parent_version=draft.parent_version, key="scheduled-nextsubmit")
    due = utc_now() + timedelta(hours=1)
    scheduled = await service.approve(actor, rw.ids["p1"], submitted.rule.version_id, expected_hash=submitted.rule.content_hash,
                                      expected_parent_version=submitted.parent_version, valid_from=due, valid_to=None, key="scheduled-nextapprove")
    assert scheduled.rule.status.value == "PROPOSED"
    assert rw.sql_one("SELECT status FROM governance.rule_versions WHERE id=%s", previous.rule.version_id) == "APPROVED"
    before = await service.evaluate(actor, rw.ids["p1"], package.version_id, key="scheduled-eval-before")
    assert before.result.obligations == ("QA_CHECK",)
    with pytest.raises(ProblemError) as caught:
        await service.publish(actor, rw.ids["p1"], scheduled.rule.version_id, expected_hash=scheduled.rule.content_hash,
                              expected_parent_version=scheduled.parent_version, key="scheduled-tooearly1")
    assert caught.value.code == ErrorCode.STATE_TRANSITION_NOT_ALLOWED
    assert rw.sql_one("SELECT status FROM governance.rule_versions WHERE id=%s", previous.rule.version_id) == "APPROVED"
    future = RulesApplicationService(service._factory, service._policy, service._idem, service._context,
                                     separation_required=False, clock=lambda: due + timedelta(seconds=1))
    published = await future.publish(actor, rw.ids["p1"], scheduled.rule.version_id, expected_hash=scheduled.rule.content_hash,
                                     expected_parent_version=scheduled.parent_version, key="scheduled-publish-due")
    assert published.rule.status.value == "APPROVED"
    assert rw.sql_one("SELECT status FROM governance.rule_versions WHERE id=%s", previous.rule.version_id) == "RETIRED"
    assert (await future.evaluate(actor, rw.ids["p1"], package.version_id, key="scheduled-eval-after1")).result.obligations == ("NEW_CHECK",)
