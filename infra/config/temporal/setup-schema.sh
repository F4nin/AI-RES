#!/bin/sh
# One-shot, idempotent Temporal schema setup/update via temporal-sql-tool (ADR-028; no auto-setup). Databases/roles come from
# postgres-provision. The password stays in this process only; the connection uses TLS with host verification.
set -eu
SQL_PASSWORD="$(cat /run/secrets/temporal_db_password)"
export SQL_PASSWORD
SCHEMA_ROOT=/etc/temporal/schema/postgresql/v12
for pair in temporal_db:temporal temporal_visibility_db:visibility; do
  name="${pair%%:*}"; kind="${pair##*:}"
  tool() { temporal-sql-tool --plugin postgres12 --ep postgres -p 5432 -u temporal --db "$name" --tls --tls-ca-file /run/secrets/postgres_tls_ca_cert --tls-server-name postgres "$@"; }
  # `setup-schema` fails when the schema_version table already exists (re-run): accept only that case, surface everything else.
  if ! out="$(tool setup-schema -v 0.0 2>&1)"; then
    case "$out" in *"already exists"*) echo "$name: schema_version present" ;; *) echo "$out" >&2; echo "setup-schema failed for $name" >&2; exit 1 ;; esac
  fi
  tool update-schema -d "$SCHEMA_ROOT/$kind/versioned"
done
echo "temporal schema is current"
