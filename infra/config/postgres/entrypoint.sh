#!/bin/bash
# Replaces the stock docker-entrypoint: the stock script exports POSTGRES_PASSWORD (even with *_FILE) into the server's process
# environment. Here the superuser password goes straight from the Compose secret to `initdb --pwfile` and never into an env var.
# TLS + SCRAM-SHA-256 only (DOC-015 add. 1.6); network access restricted per database/role by pg_hba.conf, rewritten on every start.
# Provisioning of databases/roles is a separate one-shot job (postgres-provision). ai_res_backup has no line on purpose: it is rejected until the backup stage (S32) defines its access.
set -euo pipefail
umask 077
: "${PGDATA:=/var/lib/postgresql/data}"
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  initdb -D "$PGDATA" --username=postgres --pwfile=/run/secrets/postgres_superuser_password \
    --auth-local=scram-sha-256 --auth-host=scram-sha-256 --encoding=UTF8
fi
# Postgres refuses a key that is group/world-accessible or owned by another user: copy the secret to tmpfs with the right mode.
install -m 0600 /run/secrets/postgres_tls_server_key /run/pgtls/server.key
install -m 0644 /run/secrets/postgres_tls_server_cert /run/pgtls/server.crt
cat > "$PGDATA/pg_hba.conf.new" <<'HBA'
# managed by infra/config/postgres/entrypoint.sh (S03) - rewritten on every start
local   all                                      all                      scram-sha-256
hostssl temporal_db,temporal_visibility_db       temporal                 all   scram-sha-256
hostssl ai_res_db                                ai_res_checkpointer      all   scram-sha-256
hostssl ai_res_db                                ai_res_migrator,ai_res_api,ai_res_outbox_dispatcher,ai_res_event_consumer,ai_res_auditor   all   scram-sha-256
hostssl all                                      postgres                 all   scram-sha-256
host    all                                      all                      all   reject
HBA
mv "$PGDATA/pg_hba.conf.new" "$PGDATA/pg_hba.conf"   # atomic replace: never a half-written access policy
exec postgres -c listen_addresses='*' -c password_encryption=scram-sha-256 -c unix_socket_directories=/var/run/postgresql \
  -c ssl=on -c ssl_cert_file=/run/pgtls/server.crt -c ssl_key_file=/run/pgtls/server.key -c ssl_min_protocol_version=TLSv1.2
