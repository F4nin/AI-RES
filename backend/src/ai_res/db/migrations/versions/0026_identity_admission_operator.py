"""G156 isolated identity decisions; no profile activation, login or binding seed.

Revision ID: c97e3bf386f1
Revises: b86d2af275e0

Only the separately provisioned NOLOGIN group receives EXECUTE. SQL is a narrow
trusted-operator boundary, not a replacement for application Policy/human intent
or evidence provenance. All existing migrations and profile lifecycle stay intact.
"""
# ruff: noqa: E501 -- fixed, reviewed DDL; no interpolated caller SQL
from collections.abc import Sequence

from alembic import op

revision: str = "c97e3bf386f1"
down_revision: str | None = "b86d2af275e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SNAPSHOT_SIGNATURE = "platform.owner_identity_snapshot(uuid,uuid,uuid,uuid,uuid)"
APPLY_SIGNATURE = "platform.apply_owner_identity_decision(uuid,uuid,uuid,uuid,uuid,jsonb,text,text,text)"

DDL = """
CREATE TABLE platform.model_admission_operators (
  database_login name NOT NULL,
  profile_id uuid NOT NULL CONSTRAINT fk_mao_profile REFERENCES platform.model_profiles(id) ON DELETE RESTRICT,
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT pk_model_admission_operators PRIMARY KEY(database_login,profile_id),
  CONSTRAINT fk_mao_subject FOREIGN KEY(organization_id,user_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT);
CREATE INDEX ix_mao_subject ON platform.model_admission_operators(organization_id,user_id);
CREATE INDEX ix_mao_profile ON platform.model_admission_operators(profile_id);

CREATE TABLE platform.model_admission_decisions (
  decision_id uuid CONSTRAINT pk_model_admission_decisions PRIMARY KEY,
  profile_id uuid NOT NULL CONSTRAINT fk_mad_profile REFERENCES platform.model_profiles(id) ON DELETE RESTRICT,
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  session_id uuid NOT NULL,
  database_login name NOT NULL DEFAULT session_user,
  action text NOT NULL CONSTRAINT ck_mad_action CHECK(action IN ('ACCEPT_IDENTITY','BLOCK')),
  generation integer NOT NULL CONSTRAINT ck_mad_generation CHECK(generation>0),
  command_sha256 text NOT NULL CONSTRAINT ck_mad_command CHECK(command_sha256 ~ '^[0-9a-f]{64}$'),
  review_sha256 text NOT NULL CONSTRAINT ck_mad_review CHECK(review_sha256 ~ '^[0-9a-f]{64}$'),
  profile_sha256 text NOT NULL CONSTRAINT ck_mad_profile CHECK(profile_sha256 ~ '^[0-9a-f]{64}$'),
  expectation_sha256 text NOT NULL CONSTRAINT ck_mad_expectation CHECK(expectation_sha256 ~ '^[0-9a-f]{64}$'),
  observation_sha256 text NOT NULL CONSTRAINT ck_mad_observation CHECK(observation_sha256 ~ '^[0-9a-f]{64}$'),
  policy_version text NOT NULL CONSTRAINT ck_mad_policy CHECK(policy_version ~ '^[A-Za-z0-9_.:-]{1,128}$'),
  reason_code text NOT NULL CONSTRAINT ck_mad_reason CHECK(reason_code IN ('HUMAN_IDENTITY_ACCEPTED','HUMAN_BLOCKED')),
  correlation_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_mad_subject FOREIGN KEY(organization_id,user_id) REFERENCES iam.users(organization_id,id) ON DELETE RESTRICT,
  CONSTRAINT fk_mad_generation FOREIGN KEY(profile_id,generation) REFERENCES platform.model_admission_versions(profile_id,generation) ON DELETE RESTRICT,
  CONSTRAINT ck_mad_action_reason CHECK((action='ACCEPT_IDENTITY' AND reason_code='HUMAN_IDENTITY_ACCEPTED') OR (action='BLOCK' AND reason_code='HUMAN_BLOCKED')));
CREATE INDEX ix_mad_profile ON platform.model_admission_decisions(profile_id,generation);
CREATE INDEX ix_mad_subject ON platform.model_admission_decisions(organization_id,user_id);

CREATE FUNCTION platform.owner_identity_snapshot(o uuid,u uuid,sid uuid,p uuid,d uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
DECLARE member jsonb; usr jsonb; factors jsonb; mfa text; profile text;
  control text; current_record text; pending jsonb; gen integer; receipt jsonb;
BEGIN
  IF current_setting('transaction_isolation')<>'read committed' OR current_setting('session_replication_role')<>'origin' THEN
    RAISE EXCEPTION 'operator isolation unavailable' USING ERRCODE='check_violation';
  END IF;
  PERFORM 1 FROM platform.model_admission_operators b WHERE b.database_login=session_user AND b.profile_id=p
    AND b.organization_id=o AND b.user_id=u FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'operator unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT jsonb_build_object('role_code',m.role_code,'status',m.status,'row_version',m.row_version) INTO member
    FROM organization.memberships m WHERE m.organization_id=o AND m.user_id=u AND m.status='ACTIVE' FOR SHARE;
  SELECT jsonb_build_object('status',v.status,'row_version',v.row_version) INTO usr
    FROM iam.users v WHERE v.organization_id=o AND v.id=u AND v.status='ACTIVE' FOR SHARE;
  IF member IS NULL OR usr IS NULL THEN RAISE EXCEPTION 'owner unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT coalesce(jsonb_agg(f.id::text ORDER BY f.id),'[]'::jsonb) INTO factors FROM
    (SELECT v.id FROM iam.mfa_factors v WHERE v.organization_id=o AND v.user_id=u AND v.status='ACTIVE' ORDER BY v.id FOR SHARE) f;
  IF factors='[]'::jsonb THEN RAISE EXCEPTION 'MFA unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  SELECT v.mfa_verified_at::text INTO mfa FROM iam.sessions v WHERE v.id=sid AND v.organization_id=o AND v.user_id=u
    AND v.revoked_at IS NULL AND v.idle_expires_at>clock_timestamp() AND v.absolute_expires_at>clock_timestamp() FOR SHARE;
  IF mfa IS NULL THEN RAISE EXCEPTION 'session unavailable' USING ERRCODE='insufficient_privilege'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgrelid='platform.model_profiles'::regclass
    AND t.tgname='trg_model_profiles_lifecycle_fence' AND NOT t.tgisinternal AND t.tgenabled IN ('O','A')
    AND t.tgtype=19 AND t.tgnargs=0 AND t.tgattr=''::pg_catalog.int2vector AND t.tgqual IS NULL
    AND t.tgfoid=pg_catalog.to_regprocedure('platform.fence_model_profile_lifecycle()')) THEN
    RAISE EXCEPTION 'lifecycle fence unavailable' USING ERRCODE='check_violation';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('ai_res.model_profile_lifecycle:' || p::text,0));
  SELECT to_jsonb(v)::text INTO profile FROM platform.model_profiles v WHERE v.id=p AND v.identity_mode='FLASH_OBSERVED'
    AND v.provider='deepseek' AND v.provider_model_id='deepseek-flash' AND v.pinned_model_version IS NULL
    AND v.status IN ('CANDIDATE','APPROVED') AND (v.deprecated_at IS NULL OR v.deprecated_at>clock_timestamp());
  IF profile IS NULL THEN RAISE EXCEPTION 'profile unavailable' USING ERRCODE='check_violation'; END IF;
  SELECT to_jsonb(c)::text,c.current_generation INTO control,gen FROM platform.model_admission_controls c WHERE c.profile_id=p FOR UPDATE;
  gen:=coalesce(gen,0);
  SELECT to_jsonb(v)::text INTO current_record FROM platform.model_admission_versions v WHERE v.profile_id=p AND v.generation=gen;
  IF control IS NOT NULL AND current_record IS NULL THEN RAISE EXCEPTION 'admission unavailable' USING ERRCODE='check_violation'; END IF;
  SELECT coalesce(jsonb_agg(x.snapshot ORDER BY x.call_sequence),'[]'::jsonb) INTO pending FROM
    (SELECT to_jsonb(v)::text AS snapshot,v.call_sequence FROM platform.model_admission_calls v WHERE v.profile_id=p AND v.status='IN_FLIGHT') x;
  SELECT jsonb_build_object('command_sha256',v.command_sha256,'generation',v.generation,'action',v.action) INTO receipt
    FROM platform.model_admission_decisions v WHERE v.decision_id=d AND v.profile_id=p AND v.organization_id=o AND v.user_id=u
    AND v.database_login=session_user AND v.session_id=sid;
  -- Row locks cannot stop time. Recheck AFTER the fence/control waits.
  IF NOT EXISTS(SELECT 1 FROM iam.sessions v WHERE v.id=sid AND v.user_id=u AND v.organization_id=o
    AND v.revoked_at IS NULL AND v.mfa_verified_at IS NOT NULL AND v.idle_expires_at>clock_timestamp() AND v.absolute_expires_at>clock_timestamp())
    OR NOT EXISTS(SELECT 1 FROM platform.model_profiles v WHERE v.id=p AND (v.deprecated_at IS NULL OR v.deprecated_at>clock_timestamp())) THEN
    RAISE EXCEPTION 'owner or profile expired' USING ERRCODE='insufficient_privilege';
  END IF;
  RETURN jsonb_build_object('subject',jsonb_build_object('member',member,'user',usr,'factors',factors,'mfaAt',mfa),
    'profile',profile,'control',control,'current',current_record,'pending',pending,'generation',gen,'receipt',receipt);
END $f$;

CREATE FUNCTION platform.apply_owner_identity_decision(o uuid,u uuid,sid uuid,p uuid,d uuid,reviewed jsonb,cmd_text text,expected_text text,observed_text text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET app.migration_mode='on' AS $f$
DECLARE state jsonb; cmd jsonb; exp jsonb; obs jsonb; r jsonb; cmd_hash text; eh text; oh text; gen integer; act text;
BEGIN
  IF octet_length(cmd_text)>16384 OR octet_length(expected_text)>65536 OR octet_length(observed_text)>65536 THEN
    RAISE EXCEPTION 'decision too large' USING ERRCODE='check_violation';
  END IF;
  state:=platform.owner_identity_snapshot(o,u,sid,p,d);
  IF reviewed IS DISTINCT FROM state THEN RAISE EXCEPTION 'stale decision state' USING ERRCODE='check_violation'; END IF;
  cmd:=cmd_text::jsonb; exp:=expected_text::jsonb; obs:=observed_text::jsonb; r:=cmd->'review'; act:=cmd->>'action';
  cmd_hash:=encode(sha256(convert_to(cmd_text,'UTF8')),'hex');
  eh:=encode(sha256(convert_to(expected_text,'UTF8')),'hex'); oh:=encode(sha256(convert_to(observed_text,'UTF8')),'hex');
  IF (cmd->>'decisionId'=d::text AND (cmd->>'correlationId')::uuid IS NOT NULL AND act IN ('ACCEPT_IDENTITY','BLOCK')
    AND cmd->>'expectationSha256'=eh AND cmd->>'observationSha256'=oh
    AND r->>'expectation_sha256'=eh AND r->>'observation_sha256'=oh
    AND r->>'binding_sha256' ~ '^[0-9a-f]{64}$' AND r->>'profile_sha256' ~ '^[0-9a-f]{64}$'
    AND r->>'policy_version' ~ '^[A-Za-z0-9_.:-]{1,128}$'
    AND exp->>'schemaVersion'='0.2' AND obs->>'schemaVersion'='0.2' AND exp->>'kind'='EXPECTATION' AND obs->>'kind'='OBSERVATION'
    AND exp->>'evidenceSha256'=oh AND exp->'identity'=obs->'identity' AND exp->'managedVersions'=obs->'managedVersions'
    AND exp->'managedVersions'->>'profileId'=p::text
    AND (exp->'managedVersions'->>'profileVersion')::integer=((state->>'profile')::jsonb->>'profile_version')::integer) IS NOT TRUE THEN
    RAISE EXCEPTION 'invalid decision' USING ERRCODE='check_violation';
  END IF;
  IF state->'receipt'<>'null'::jsonb THEN
    IF state->'receipt'->>'command_sha256'<>cmd_hash THEN RAISE EXCEPTION 'decision reused' USING ERRCODE='check_violation'; END IF;
    RETURN state->'receipt';
  END IF;
  gen:=(state->>'generation')::integer;
  IF (exp->>'admissionGeneration')::integer IS DISTINCT FROM gen+1 THEN RAISE EXCEPTION 'stale generation' USING ERRCODE='check_violation'; END IF;
  IF act='ACCEPT_IDENTITY' THEN
    IF state->'pending'<>'[]'::jsonb THEN RAISE EXCEPTION 'unresolved calls' USING ERRCODE='check_violation'; END IF;
    gen:=gen+1;
    INSERT INTO platform.model_admission_versions(profile_id,generation,profile_version,expectation,expectation_sha256)
      VALUES(p,gen,(exp->'managedVersions'->>'profileVersion')::integer,exp,decode(eh,'hex'));
    INSERT INTO platform.model_admission_controls(profile_id,current_generation) VALUES(p,gen)
      ON CONFLICT(profile_id) DO UPDATE SET current_generation=EXCLUDED.current_generation,blocked=false;
  ELSE
    IF gen=0 THEN RAISE EXCEPTION 'no admission to block' USING ERRCODE='check_violation'; END IF;
    UPDATE platform.model_admission_controls SET blocked=true WHERE profile_id=p;
  END IF;
  INSERT INTO platform.model_admission_decisions(decision_id,profile_id,organization_id,user_id,session_id,action,generation,
    command_sha256,review_sha256,profile_sha256,expectation_sha256,observation_sha256,policy_version,reason_code,correlation_id)
    VALUES(d,p,o,u,sid,act,gen,cmd_hash,r->>'binding_sha256',r->>'profile_sha256',eh,oh,r->>'policy_version',
      CASE WHEN act='ACCEPT_IDENTITY' THEN 'HUMAN_IDENTITY_ACCEPTED' ELSE 'HUMAN_BLOCKED' END,(cmd->>'correlationId')::uuid);
  RETURN jsonb_build_object('generation',gen,'action',act,'command_sha256',cmd_hash);
END $f$;
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in ("model_admission_operators", "model_admission_decisions"):
        op.execute(f"ALTER TABLE platform.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE platform.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{table}_owner_migration ON platform.{table} FOR ALL TO ai_res_owner "
                   "USING (coalesce(current_setting('app.migration_mode',true),'')='on') "
                   "WITH CHECK (coalesce(current_setting('app.migration_mode',true),'')='on')")
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON platform.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON platform.{table} "
                   "FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")
    op.execute("GRANT USAGE ON SCHEMA platform TO ai_res_model_admission_operator")
    for signature in (SNAPSHOT_SIGNATURE, APPLY_SIGNATURE):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO ai_res_model_admission_operator")


def downgrade() -> None:
    raise NotImplementedError("Human decisions are append-only; use a reviewed forward-fix or approved restore.")
