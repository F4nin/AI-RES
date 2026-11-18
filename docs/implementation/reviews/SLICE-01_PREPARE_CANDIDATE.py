"""One reviewed local maintenance operation; rollback by default, never approve.

Run only through the existing migrate service (TLS, migrator credentials).
The fixed profile is restricted to the owner's agreed Flash/INTERNAL/cn scope.
Capacity/output/timeout are conservative local caps, not provider capability claims.
No inference, identity acceptance, MFA/session creation, schema or role changes.
"""
import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from uuid import UUID

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.llm.registry import CostRates, Egress, ModelProfile, ProfileIdentityMode, ProfileStatus, RetryClass
from ai_res.llm.types import Capability
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.model_registry.profile_approval import profile_snapshot_hash
from ai_res.modules.model_registry.repository import load_model_registry
from ai_res.platform.config import load_settings
from ai_res.platform.ports import AuditOutcome, AuditRecord
from sqlalchemy import text

PROFILE_ID = UUID("01a1ef1f-5182-70f8-8dda-603e33876b8b")
ORGANIZATION_ID = UUID("01a1eef2-08a5-737a-8304-65ed7b5b0538")
OWNER_ID = UUID("01a1eef2-08a5-737a-8304-65eec13a0507")
CORRELATION_ID = "01a1ef1f-5182-70f8-8dda-603e33876b8c"
KEY = "deepseek-flash-slice01"


class PreviewComplete(Exception):
    """Force the whole configuration and audit transaction to roll back."""


async def prepare(*, apply: bool) -> dict:
    stage = "SETTINGS"
    settings = load_settings(os.environ)
    if settings.db_user != "ai_res_migrator" or settings.db_sslmode != "verify-full":
        raise ValueError("maintenance identity/TLS required")
    engine = create_runtime_engine(settings)
    summary = {}
    try:
        try:
            async with UnitOfWork(create_session_factory(engine)) as uow:
                s = uow.session
                stage = "OWNER_CONTEXT"
                await s.execute(text("SET LOCAL ROLE ai_res_owner"))
                # Existing owner-maintenance RLS policy, as in migration env.py;
                # never change roles/policies or use this mode in Runtime.
                await s.execute(text("SELECT set_config('app.migration_mode','on',true)"))
                # Exact server-inspected bootstrap identity, revalidated here.
                await uow.with_tenant(ORGANIZATION_ID)
                stage = "OWNER_REVALIDATION"
                owner = (await s.execute(text(
                    "SELECT u.organization_id,u.id FROM iam.users u JOIN organization.memberships m "
                    "ON m.organization_id=u.organization_id AND m.user_id=u.id "
                    "WHERE u.organization_id=:o AND u.id=:u "
                    "AND u.email_normalized='admin@ai-res.local' AND u.status='ACTIVE' "
                    "AND m.status='ACTIVE' AND m.role_code='ORGANIZATION_OWNER' FOR SHARE OF u,m"),
                    {"o": ORGANIZATION_ID, "u": OWNER_ID})).one()
                if (await s.execute(text("SELECT count(*) FROM platform.model_profiles"))).scalar_one() != 0:
                    raise ValueError("first profile already configured; never replace or replay implicitly")
                stage = "CANDIDATE_VALIDATION"
                profile = ModelProfile(
                    id=PROFILE_ID, profile_key=KEY, profile_version=1,
                    identity_mode=ProfileIdentityMode.FLASH_OBSERVED,
                    provider="deepseek", provider_model_id="deepseek-flash", pinned_model_version=None,
                    capabilities=frozenset({Capability.CHAT}), context_window_tokens=8192,
                    max_output_tokens=2048, data_classifications=frozenset({"INTERNAL"}),
                    allowed_regions=frozenset({"cn"}), egress=Egress.EXTERNAL,
                    cost_rates=CostRates(currency="USD", input_per_million=Decimal("0.30"),
                                         output_per_million=Decimal("1.20")),
                    timeout_seconds=30, retry_class=RetryClass.NONE, status=ProfileStatus.CANDIDATE)
                stage = "CANDIDATE_INSERT"
                await s.execute(text(
                    "INSERT INTO platform.model_profiles (id,profile_key,profile_version,identity_mode,provider,"
                    "provider_model_id,pinned_model_version,capabilities,context_window_tokens,max_output_tokens,"
                    "data_classifications,allowed_regions,egress,cost_currency,cost_input_per_million,"
                    "cost_output_per_million,timeout_seconds,retry_class) VALUES "
                    "(:id,:key,1,'FLASH_OBSERVED','deepseek','deepseek-flash',NULL,ARRAY['CHAT'],8192,2048,"
                    "ARRAY['INTERNAL'],ARRAY['cn'],'EXTERNAL','USD',0.30,1.20,30,'NONE')"),
                    {"id": PROFILE_ID, "key": KEY})
                registry = await load_model_registry(s)
                stage = "CANDIDATE_ROUNDTRIP"
                if registry.get(PROFILE_ID) != profile:
                    raise ValueError("stored profile differs from validated candidate")
                stage = "OWNER_BINDING"
                await s.execute(text(
                    "INSERT INTO platform.model_admission_operators (database_login,profile_id,organization_id,user_id) "
                    "VALUES ('ai_res_migrator',:p,:o,:u)"),
                    {"p": PROFILE_ID, "o": owner.organization_id, "u": owner.id})
                snapshot = (await s.execute(text(
                    "SELECT to_jsonb(p)::text FROM platform.model_profiles p WHERE id=:p"),
                    {"p": PROFILE_ID})).scalar_one()
                digest = profile_snapshot_hash(snapshot)
                stage = "AUDIT"
                await SqlAuditWriter(s).write(AuditRecord(
                    action="MODEL_PROFILE_CANDIDATE_PREPARED", outcome=AuditOutcome.SUCCEEDED,
                    actor_type="SYSTEM", resource_type="MODEL_PROFILE", resource_id=str(PROFILE_ID),
                    organization_id=str(owner.organization_id), request_id=CORRELATION_ID,
                    reason_code="OPERATOR_CONFIGURATION", details={"profileSha256": digest,
                        "scope": "SLICE-01", "status": "CANDIDATE", "region": "cn"}))
                summary = {"operation": "APPLIED" if apply else "ROLLED_BACK_PREVIEW",
                    "profileId": str(PROFILE_ID), "organizationId": str(owner.organization_id),
                    "ownerUserId": str(owner.id), "ownerLogin": "ai_res_migrator",
                    "profileSha256": digest, "profileSnapshot": snapshot,
                    "correlationId": CORRELATION_ID, "providerCalls": 0, "modelApproved": False}
                if not apply:
                    raise PreviewComplete()
        except PreviewComplete:
            pass
    except Exception as error:
        # Fixed stage + exception class only; never SQL parameters or credentials.
        print(json.dumps({"stage": stage, "errorType": type(error).__name__}), file=sys.stderr)
        raise
    finally:
        await engine.dispose()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    try:
        print(json.dumps(asyncio.run(prepare(apply=parser.parse_args().apply)), sort_keys=True))
    except Exception:
        print("Candidate configuration refused; transaction rolled back; details withheld.", file=sys.stderr)
        raise SystemExit(2) from None
