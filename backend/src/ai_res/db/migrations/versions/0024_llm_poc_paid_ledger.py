"""G156 preparation: one bounded technical paid ledger, no live account/authority.

Revision ID: a75c0eb164d9
Revises: f64b9da053c8

No account, tariff, provider key, model profile or approval is seeded. The only
authorization scope is the existing combined Flash technical-admission budget;
runtime cannot create another wallet or alter cap/plan/tariffs. Reservations and
settlements are immutable money facts. UNKNOWN consumes the full reservation.
No product budget, relay, credential or host-authorization wiring is introduced.
"""
# ruff: noqa: E501, S608 -- fixed reviewed DDL/table literals only
from collections.abc import Sequence

from alembic import op

revision: str = "a75c0eb164d9"
down_revision: str | None = "f64b9da053c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACCOUNT = "account_id=NULLIF(current_setting('app.llm_poc_budget_id',true),'')::uuid"
GATE = "coalesce(current_setting('app.migration_mode', true), '') = 'on'"

DDL = """
CREATE TABLE platform.llm_poc_budget_accounts (
  id uuid CONSTRAINT pk_llm_poc_budget_accounts PRIMARY KEY,
  authorization_key text NOT NULL CONSTRAINT uq_lpba_authorization UNIQUE
    CONSTRAINT ck_lpba_authorization CHECK (authorization_key='FLASH_TECHNICAL_ADMISSION_2026_11_17'),
  currency text NOT NULL CONSTRAINT ck_lpba_currency CHECK (currency='USD'),
  max_cost numeric NOT NULL CONSTRAINT ck_lpba_cap CHECK (max_cost>0 AND max_cost<=10),
  original_spend numeric NOT NULL CONSTRAINT ck_lpba_original CHECK (original_spend>=0 AND original_spend<=max_cost),
  max_attempts integer NOT NULL CONSTRAINT ck_lpba_attempts CHECK (max_attempts BETWEEN 1 AND 8),
  input_bound bigint NOT NULL CONSTRAINT ck_lpba_input CHECK (input_bound=2000000),
  output_bound integer NOT NULL CONSTRAINT ck_lpba_output CHECK (output_bound=256),
  body_bound integer NOT NULL CONSTRAINT ck_lpba_body CHECK (body_bound=4096),
  provider text NOT NULL CONSTRAINT ck_lpba_provider CHECK (provider='deepseek'),
  model_id text NOT NULL CONSTRAINT ck_lpba_model CHECK (model_id='deepseek-flash'),
  http_method text NOT NULL CONSTRAINT ck_lpba_method CHECK (http_method='POST'),
  upstream_host text NOT NULL CONSTRAINT ck_lpba_host CHECK (upstream_host='api.deepseek.com'),
  upstream_path text NOT NULL CONSTRAINT ck_lpba_path CHECK (upstream_path='/chat/completions'),
  plan_sha256 bytea NOT NULL CONSTRAINT ck_lpba_plan CHECK (octet_length(plan_sha256)=32),
  tariff_sha256 bytea NOT NULL CONSTRAINT ck_lpba_tariff CHECK (octet_length(tariff_sha256)=32),
  input_per_million numeric NOT NULL CONSTRAINT ck_lpba_input_rate CHECK (input_per_million>=0 AND input_per_million<'Infinity'::numeric),
  output_per_million numeric NOT NULL CONSTRAINT ck_lpba_output_rate CHECK (output_per_million>=0 AND output_per_million<'Infinity'::numeric),
  attempt_sequence integer NOT NULL DEFAULT 0 CONSTRAINT ck_lpba_sequence CHECK (attempt_sequence BETWEEN 0 AND max_attempts),
  blocked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ck_lpba_reservable CHECK ((input_bound*input_per_million+output_bound*output_per_million)/1000000>0
    AND (input_bound*input_per_million+output_bound*output_per_million)/1000000<=max_cost));

CREATE TABLE platform.llm_poc_attempts (
  id uuid CONSTRAINT pk_llm_poc_attempts PRIMARY KEY,
  account_id uuid NOT NULL CONSTRAINT fk_lpa_account REFERENCES platform.llm_poc_budget_accounts(id) ON DELETE RESTRICT,
  sequence integer NOT NULL CONSTRAINT ck_lpa_sequence CHECK (sequence BETWEEN 1 AND 8),
  request_ref text NOT NULL CONSTRAINT ck_lpa_request CHECK (request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$' AND request_ref !~ '[[:space:]]'),
  case_ref text NOT NULL CONSTRAINT ck_lpa_case CHECK (case_ref IN ('TEXT','JSON','TOOL','SSE','CANCEL','TIMEOUT','RECHECK')),
  body_sha256 bytea NOT NULL CONSTRAINT ck_lpa_body_hash CHECK (octet_length(body_sha256)=32),
  payload_bytes integer NOT NULL CONSTRAINT ck_lpa_bytes CHECK (payload_bytes BETWEEN 1 AND 4096),
  stream boolean NOT NULL,
  max_output_tokens integer NOT NULL CONSTRAINT ck_lpa_output CHECK (max_output_tokens BETWEEN 1 AND 256),
  plan_sha256 bytea NOT NULL CONSTRAINT ck_lpa_plan CHECK (octet_length(plan_sha256)=32),
  tariff_sha256 bytea NOT NULL CONSTRAINT ck_lpa_tariff CHECK (octet_length(tariff_sha256)=32),
  reserved_cost numeric NOT NULL CONSTRAINT ck_lpa_cost CHECK (reserved_cost>0 AND reserved_cost<'Infinity'::numeric),
  state text NOT NULL DEFAULT 'RESERVED' CONSTRAINT ck_lpa_state CHECK (state IN ('RESERVED','CLAIMED','SETTLED')),
  claimed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT uq_lpa_scope_id UNIQUE (account_id,id),
  CONSTRAINT uq_lpa_sequence UNIQUE (account_id,sequence),
  CONSTRAINT uq_lpa_request UNIQUE (account_id,request_ref),
  CONSTRAINT uq_lpa_body UNIQUE (account_id,body_sha256),
  CONSTRAINT ck_lpa_claim_time CHECK ((state='RESERVED' AND claimed_at IS NULL) OR (state IN ('CLAIMED','SETTLED') AND claimed_at IS NOT NULL)));
CREATE UNIQUE INDEX ix_lpa_single_flight ON platform.llm_poc_attempts(account_id) WHERE state IN ('RESERVED','CLAIMED');

CREATE TABLE platform.llm_poc_settlements (
  id uuid CONSTRAINT pk_llm_poc_settlements PRIMARY KEY,
  account_id uuid NOT NULL,
  attempt_id uuid NOT NULL CONSTRAINT uq_lps_attempt UNIQUE,
  outcome text NOT NULL CONSTRAINT ck_lps_outcome CHECK (outcome IN ('KNOWN','UNKNOWN','OVERRUN','INVALID_USAGE')),
  reason_code text NOT NULL CONSTRAINT ck_lps_reason CHECK (reason_code IN ('USAGE','TIMEOUT','CANCEL','NETWORK','PROVIDER_ERROR','UNTRUSTED_RESPONSE','INVALID_USAGE')),
  input_tokens bigint NULL CONSTRAINT ck_lps_input CHECK (input_tokens>=0),
  output_tokens bigint NULL CONSTRAINT ck_lps_output CHECK (output_tokens>=0),
  provider_request_ref text NULL CONSTRAINT ck_lps_provider_ref CHECK (provider_request_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
    AND provider_request_ref !~ '[[:space:]]'),
  proof_sha256 bytea NOT NULL CONSTRAINT ck_lps_proof CHECK (octet_length(proof_sha256)=32),
  charged_cost numeric NOT NULL CONSTRAINT ck_lps_charge CHECK (charged_cost>=0 AND charged_cost<'Infinity'::numeric),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_lps_attempt FOREIGN KEY (account_id,attempt_id) REFERENCES platform.llm_poc_attempts(account_id,id) ON DELETE RESTRICT,
  CONSTRAINT ck_lps_shape CHECK (((outcome IN ('KNOWN','OVERRUN') AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
      AND provider_request_ref IS NOT NULL AND reason_code='USAGE')
    OR (outcome='UNKNOWN' AND input_tokens IS NULL AND output_tokens IS NULL AND provider_request_ref IS NULL
      AND reason_code IN ('TIMEOUT','CANCEL','NETWORK','PROVIDER_ERROR','UNTRUSTED_RESPONSE'))
    OR (outcome='INVALID_USAGE' AND input_tokens IS NULL AND output_tokens IS NULL AND provider_request_ref IS NULL AND reason_code='INVALID_USAGE')) IS TRUE));
CREATE INDEX ix_lps_attempt_scope ON platform.llm_poc_settlements(account_id,attempt_id);

CREATE TABLE platform.llm_poc_budget_audit (
  id uuid CONSTRAINT pk_llm_poc_budget_audit PRIMARY KEY,
  account_id uuid NOT NULL CONSTRAINT fk_lpau_account REFERENCES platform.llm_poc_budget_accounts(id) ON DELETE RESTRICT,
  attempt_id uuid NULL,
  action text NOT NULL CONSTRAINT ck_lpau_action CHECK (action IN ('RESERVE','CLAIM','SETTLE','DENY','BLOCK')),
  reason_code text NOT NULL CONSTRAINT ck_lpau_reason CHECK (reason_code IN ('RESERVED','CLAIMED','KNOWN','UNKNOWN','OVERRUN','INVALID_USAGE',
    'ACCOUNT_BLOCKED','BUDGET_EXHAUSTED','ATTEMPTS_EXHAUSTED','PENDING','BINDING_MISMATCH','REQUEST_REUSED','BODY_REUSED','CLAIM_REPLAY','SETTLEMENT_CONFLICT','INVALID_STATE')),
  writer_role text NOT NULL DEFAULT current_user,
  occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fk_lpau_attempt FOREIGN KEY (account_id,attempt_id) REFERENCES platform.llm_poc_attempts(account_id,id) ON DELETE RESTRICT);
CREATE INDEX ix_lpau_attempt_scope ON platform.llm_poc_budget_audit(account_id,attempt_id);

CREATE FUNCTION platform.guard_llm_poc_account() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF (to_jsonb(NEW)-'attempt_sequence'-'blocked') IS DISTINCT FROM (to_jsonb(OLD)-'attempt_sequence'-'blocked')
     OR NEW.attempt_sequence NOT IN (OLD.attempt_sequence,OLD.attempt_sequence+1) OR (OLD.blocked AND NOT NEW.blocked) THEN
    RAISE EXCEPTION 'technical budget cannot be reset, enlarged or unblocked' USING ERRCODE='integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_lpba_guard BEFORE UPDATE ON platform.llm_poc_budget_accounts FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_account();

CREATE FUNCTION platform.guard_llm_poc_attempt() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE account platform.llm_poc_budget_accounts%ROWTYPE; used_cost numeric;
BEGIN
  SELECT * INTO account FROM platform.llm_poc_budget_accounts WHERE id=NEW.account_id FOR UPDATE;
  IF account.id IS NULL THEN
    RAISE EXCEPTION 'technical budget unavailable' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF TG_OP='INSERT' THEN
    IF account.blocked OR NEW.sequence<>account.attempt_sequence OR NEW.state<>'RESERVED' OR NEW.claimed_at IS NOT NULL THEN
      RAISE EXCEPTION 'invalid technical reservation' USING ERRCODE='integrity_constraint_violation';
    END IF;
    SELECT account.original_spend+coalesce(sum(coalesce(s.charged_cost,a.reserved_cost)),0) INTO used_cost
      FROM platform.llm_poc_attempts a LEFT JOIN platform.llm_poc_settlements s ON s.account_id=a.account_id AND s.attempt_id=a.id
      WHERE a.account_id=NEW.account_id;
    NEW.reserved_cost := (account.input_bound*account.input_per_million+account.output_bound*account.output_per_million)/1000000;
    NEW.plan_sha256 := account.plan_sha256;
    NEW.tariff_sha256 := account.tariff_sha256;
    IF used_cost+NEW.reserved_cost>account.max_cost OR NEW.sequence>account.max_attempts THEN
      RAISE EXCEPTION 'technical budget exhausted' USING ERRCODE='integrity_constraint_violation';
    END IF;
  ELSE
    IF (to_jsonb(NEW)-'state'-'claimed_at') IS DISTINCT FROM (to_jsonb(OLD)-'state'-'claimed_at') THEN
      RAISE EXCEPTION 'technical request binding is immutable' USING ERRCODE='integrity_constraint_violation';
    END IF;
    IF OLD.state='RESERVED' AND NEW.state='CLAIMED' AND NOT account.blocked THEN
      NEW.claimed_at := clock_timestamp();
    ELSIF OLD.state='CLAIMED' AND NEW.state='SETTLED' AND NEW.claimed_at IS NOT DISTINCT FROM OLD.claimed_at
      AND EXISTS (SELECT 1 FROM platform.llm_poc_settlements WHERE account_id=NEW.account_id AND attempt_id=NEW.id) THEN
      NULL;
    ELSE
      RAISE EXCEPTION 'technical dispatch claim cannot be replayed' USING ERRCODE='integrity_constraint_violation';
    END IF;
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_lpa_guard BEFORE INSERT OR UPDATE ON platform.llm_poc_attempts FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_attempt();

CREATE FUNCTION platform.guard_llm_poc_settlement() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE account platform.llm_poc_budget_accounts%ROWTYPE; attempt platform.llm_poc_attempts%ROWTYPE;
BEGIN
  SELECT * INTO account FROM platform.llm_poc_budget_accounts WHERE id=NEW.account_id FOR UPDATE;
  SELECT * INTO attempt FROM platform.llm_poc_attempts WHERE account_id=NEW.account_id AND id=NEW.attempt_id;
  IF account.id IS NULL OR attempt.id IS NULL OR attempt.state<>'CLAIMED' THEN
    RAISE EXCEPTION 'technical settlement requires an unresolved dispatch claim' USING ERRCODE='integrity_constraint_violation';
  END IF;
  IF NEW.outcome IN ('KNOWN','OVERRUN') THEN
    IF NEW.input_tokens IS NULL OR NEW.output_tokens IS NULL OR NEW.input_tokens<0 OR NEW.output_tokens<0 THEN
      RAISE EXCEPTION 'invalid technical usage' USING ERRCODE='integrity_constraint_violation';
    END IF;
    NEW.charged_cost := (NEW.input_tokens*account.input_per_million+NEW.output_tokens*account.output_per_million)/1000000;
    NEW.outcome := CASE WHEN NEW.input_tokens>account.input_bound OR NEW.output_tokens>attempt.max_output_tokens THEN 'OVERRUN' ELSE 'KNOWN' END;
  ELSE
    NEW.charged_cost := attempt.reserved_cost;
  END IF;
  IF NEW.outcome IN ('OVERRUN','INVALID_USAGE') THEN
    UPDATE platform.llm_poc_budget_accounts SET blocked=true WHERE id=NEW.account_id;
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_lps_guard BEFORE INSERT ON platform.llm_poc_settlements FOR EACH ROW EXECUTE FUNCTION platform.guard_llm_poc_settlement();
CREATE FUNCTION platform.finish_llm_poc_settlement() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  UPDATE platform.llm_poc_attempts SET state='SETTLED' WHERE account_id=NEW.account_id AND id=NEW.attempt_id;
  RETURN NEW;
END $f$;
CREATE TRIGGER trg_lps_finish AFTER INSERT ON platform.llm_poc_settlements FOR EACH ROW EXECUTE FUNCTION platform.finish_llm_poc_settlement();
"""


def upgrade() -> None:
    op.execute(DDL)
    for table in ("llm_poc_budget_accounts", "llm_poc_attempts", "llm_poc_settlements", "llm_poc_budget_audit"):
        qualified = f"platform.{table}"
        scope = "id=NULLIF(current_setting('app.llm_poc_budget_id',true),'')::uuid" if table == "llm_poc_budget_accounts" else ACCOUNT
        op.execute(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY p_{table}_owner_migration ON {qualified} FOR ALL TO ai_res_owner USING ({GATE}) WITH CHECK ({GATE})")
        op.execute(f"CREATE POLICY p_{table}_read ON {qualified} FOR SELECT TO ai_res_api_group USING ({scope})")
        op.execute(f"GRANT SELECT ON {qualified} TO ai_res_api_group")
        if table == "llm_poc_budget_accounts":
            op.execute(f"CREATE POLICY p_{table}_update ON {qualified} FOR UPDATE TO ai_res_api_group USING ({scope}) WITH CHECK ({scope})")
            op.execute(f"GRANT UPDATE(attempt_sequence,blocked) ON {qualified} TO ai_res_api_group")
        else:
            op.execute(f"CREATE POLICY p_{table}_insert ON {qualified} FOR INSERT TO ai_res_api_group WITH CHECK ({scope})")
            if table == "llm_poc_attempts":
                op.execute(f"GRANT INSERT(id,account_id,sequence,request_ref,case_ref,body_sha256,payload_bytes,stream,max_output_tokens) ON {qualified} TO ai_res_api_group")
                op.execute(f"CREATE POLICY p_{table}_update ON {qualified} FOR UPDATE TO ai_res_api_group USING ({scope}) WITH CHECK ({scope})")
                op.execute(f"GRANT UPDATE(state) ON {qualified} TO ai_res_api_group")
            elif table == "llm_poc_settlements":
                op.execute(f"GRANT INSERT(id,account_id,attempt_id,outcome,reason_code,input_tokens,output_tokens,provider_request_ref,proof_sha256) ON {qualified} TO ai_res_api_group")
            else:
                op.execute(f"GRANT INSERT(id,account_id,attempt_id,action,reason_code) ON {qualified} TO ai_res_api_group")
        command = "UPDATE OR DELETE" if table in ("llm_poc_settlements", "llm_poc_budget_audit") else "DELETE"
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE {command} ON {qualified} FOR EACH ROW EXECUTE FUNCTION platform.reject_modification()")
        op.execute(f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON {qualified} FOR EACH STATEMENT EXECUTE FUNCTION platform.reject_modification()")


def downgrade() -> None:
    raise NotImplementedError("Technical spend/evidence cannot be reset; use a forward-fix or an explicitly approved restore.")
