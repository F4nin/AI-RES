"""G156: durable metadata-only admission guard foundation, no profile enablement.

Revision ID: c93e6a7d20b1
Revises: b621f4d8a905

No real model/profile/admission/approval is seeded. Existing immutable pin contracts
are untouched. Generations/active-generation changes are owner-only; this is not
a human approval API. Runtime can reserve calls, finalize them, and set a sticky
block, but cannot approve, clear a block, delete evidence or alter request binding.
"""
# ruff: noqa: E501, S608 -- reviewed frozen DDL literals only
from collections.abc import Sequence

from alembic import op

revision: str = "c93e6a7d20b1"
down_revision: str | None = "b621f4d8a905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROFILE = "profile_id=NULLIF(current_setting('app.model_profile_id',true),'')::uuid"
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"

DDL = """
CREATE TABLE platform.model_admission_versions (
  profile_id uuid NOT NULL CONSTRAINT fk_mav_profile REFERENCES platform.model_profiles(id) ON DELETE RESTRICT,
  generation integer NOT NULL CONSTRAINT ck_mav_generation CHECK (generation>0),
  profile_version integer NOT NULL CONSTRAINT ck_mav_profile_version CHECK (profile_version>0),
  expectation jsonb NOT NULL CONSTRAINT ck_mav_expectation CHECK (jsonb_typeof(expectation)='object'),
  expectation_sha256 bytea NOT NULL CONSTRAINT ck_mav_hash CHECK (octet_length(expectation_sha256)=32),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT pk_model_admission_versions PRIMARY KEY (profile_id,generation),
  CONSTRAINT uq_mav_binding UNIQUE (profile_id,generation,expectation_sha256));

CREATE TABLE platform.model_admission_controls (
  profile_id uuid CONSTRAINT pk_model_admission_controls PRIMARY KEY,
  current_generation integer NOT NULL,
  blocked boolean NOT NULL DEFAULT false,
  call_sequence bigint NOT NULL DEFAULT 0 CONSTRAINT ck_mac_sequence CHECK (call_sequence>=0),
  CONSTRAINT fk_mac_generation FOREIGN KEY (profile_id,current_generation)
    REFERENCES platform.model_admission_versions(profile_id,generation) ON DELETE RESTRICT);

CREATE TABLE platform.model_admission_calls (
  id uuid CONSTRAINT pk_model_admission_calls PRIMARY KEY,
  profile_id uuid NOT NULL,
  generation integer NOT NULL,
  call_sequence bigint NOT NULL CONSTRAINT ck_mcall_sequence CHECK (call_sequence>0),
  request_ref text NOT NULL CONSTRAINT ck_mcall_ref CHECK (request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' AND request_ref !~ '[[:space:]]'),
  expected_sha256 bytea NOT NULL CONSTRAINT ck_mcall_expected CHECK (octet_length(expected_sha256)=32),
  status text NOT NULL DEFAULT 'IN_FLIGHT' CONSTRAINT ck_mcall_status CHECK (status IN ('IN_FLIGHT','VALIDATED','BLOCKED')),
  observed_sha256 bytea NULL CONSTRAINT ck_mcall_observed CHECK (observed_sha256 IS NULL OR octet_length(observed_sha256)=32),
  finalized_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_mcall_scope_id UNIQUE (profile_id,id),
  CONSTRAINT uq_mcall_sequence UNIQUE (profile_id,call_sequence),
  CONSTRAINT uq_mcall_request UNIQUE (profile_id,request_ref),
  CONSTRAINT fk_mcall_generation FOREIGN KEY (profile_id,generation,expected_sha256)
    REFERENCES platform.model_admission_versions(profile_id,generation,expectation_sha256) ON DELETE RESTRICT,
  CONSTRAINT ck_mcall_final CHECK ((status='IN_FLIGHT' AND finalized_at IS NULL AND observed_sha256 IS NULL)
    OR (status='VALIDATED' AND finalized_at IS NOT NULL AND observed_sha256 IS NOT NULL)
    OR (status='BLOCKED' AND finalized_at IS NOT NULL)));
CREATE UNIQUE INDEX ix_mcall_single_flight ON platform.model_admission_calls(profile_id) WHERE status='IN_FLIGHT';

CREATE TABLE platform.model_admission_audit (
  id uuid CONSTRAINT pk_model_admission_audit PRIMARY KEY,
  profile_id uuid NOT NULL,
  call_id uuid NOT NULL,
  event_type text NOT NULL CONSTRAINT ck_maa_type CHECK (event_type IN ('BEGIN','VALIDATED','BLOCKED')),
  reason_code text NOT NULL CONSTRAINT ck_maa_reason CHECK (reason_code IN ('RESERVED','MATCH','IDENTITY_MISMATCH','MALFORMED_OBSERVATION')),
  writer_role text NOT NULL DEFAULT current_user CONSTRAINT ck_maa_writer CHECK (writer_role=current_user),
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_maa_call_event UNIQUE (call_id,event_type),
  CONSTRAINT fk_maa_call FOREIGN KEY (profile_id,call_id)
    REFERENCES platform.model_admission_calls(profile_id,id) ON DELETE RESTRICT,
  CONSTRAINT ck_maa_event_reason CHECK ((event_type='BEGIN' AND reason_code='RESERVED')
    OR (event_type='VALIDATED' AND reason_code='MATCH')
    OR (event_type='BLOCKED' AND reason_code IN ('IDENTITY_MISMATCH','MALFORMED_OBSERVATION'))));
CREATE INDEX ix_maa_call_scope ON platform.model_admission_audit(profile_id,call_id);

CREATE FUNCTION platform.guard_model_admission_control() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF NEW.profile_id IS DISTINCT FROM OLD.profile_id THEN
    RAISE EXCEPTION 'admission profile binding is immutable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF current_user='ai_res_owner' THEN
    IF NEW.current_generation IS DISTINCT FROM OLD.current_generation AND NEW.current_generation<=OLD.current_generation THEN
      RAISE EXCEPTION 'admission generation must advance' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSE
    IF NEW.current_generation IS DISTINCT FROM OLD.current_generation OR (OLD.blocked AND NOT NEW.blocked) THEN
      RAISE EXCEPTION 'runtime cannot approve or clear an admission block' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  IF NEW.call_sequence NOT IN (OLD.call_sequence,OLD.call_sequence+1) THEN
    RAISE EXCEPTION 'admission sequence must advance once' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_mac_guard BEFORE UPDATE ON platform.model_admission_controls
  FOR EACH ROW EXECUTE FUNCTION platform.guard_model_admission_control();

CREATE FUNCTION platform.guard_model_admission_call() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF TG_OP='INSERT' THEN
    IF NEW.status<>'IN_FLIGHT' OR NEW.finalized_at IS NOT NULL OR NEW.observed_sha256 IS NOT NULL THEN
      RAISE EXCEPTION 'admission call starts unresolved' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSIF OLD.status<>'IN_FLIGHT' OR NEW.status NOT IN ('VALIDATED','BLOCKED')
     OR (to_jsonb(NEW)-'status'-'observed_sha256'-'finalized_at') IS DISTINCT FROM
        (to_jsonb(OLD)-'status'-'observed_sha256'-'finalized_at') THEN
    RAISE EXCEPTION 'admission call binding and terminal evidence are immutable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_mcall_guard BEFORE INSERT OR UPDATE ON platform.model_admission_calls
  FOR EACH ROW EXECUTE FUNCTION platform.guard_model_admission_call();
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in ("model_admission_versions", "model_admission_controls", "model_admission_calls", "model_admission_audit"):
        qualified = f"platform.{table}"
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{table}_owner_migration ON {qualified} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
        op.execute(f"CREATE POLICY p_{table}_read ON {qualified} FOR SELECT TO ai_res_api_group USING ({PROFILE})")
        op.execute(f"GRANT SELECT ON {qualified} TO ai_res_api_group")
        if table != "model_admission_versions":
            command = "UPDATE" if table == "model_admission_controls" else "INSERT"
            using = f"USING ({PROFILE}) " if command == "UPDATE" else ""
            op.execute(f"CREATE POLICY p_{table}_write ON {qualified} FOR {command} TO ai_res_api_group {using}WITH CHECK ({PROFILE})")
        if table == "model_admission_calls":
            op.execute(f"CREATE POLICY p_{table}_finalize ON {qualified} FOR UPDATE TO ai_res_api_group USING ({PROFILE}) WITH CHECK ({PROFILE})")
            op.execute(f"GRANT INSERT(id,profile_id,generation,call_sequence,request_ref,expected_sha256) ON {qualified} TO ai_res_api_group")
            op.execute(f"GRANT UPDATE(status,observed_sha256,finalized_at) ON {qualified} TO ai_res_api_group")
        elif table == "model_admission_controls":
            op.execute(f"GRANT UPDATE(blocked,call_sequence) ON {qualified} TO ai_res_api_group")
        elif table == "model_admission_audit":
            op.execute(f"GRANT INSERT(id,profile_id,call_id,event_type,reason_code) ON {qualified} TO ai_res_api_group")
        if table in ("model_admission_versions", "model_admission_audit"):
            op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {qualified} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        else:
            op.execute(f"CREATE TRIGGER trg_{table}_no_delete BEFORE DELETE ON {qualified} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {qualified} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def downgrade() -> None:
    raise NotImplementedError("Admission evidence is append-only; forward-fix or restore with explicit approval.")
