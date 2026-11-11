#!/bin/bash
# Renders the stock config template into a tmpfs (root filesystem is read-only) with the DB password read from the Compose secret
# into this process' environment only (never in compose env / `docker inspect`), then starts the server like the stock entrypoint.
set -euo pipefail
umask 077
POSTGRES_PWD="$(cat "$POSTGRES_PWD_FILE")"
export POSTGRES_PWD
unset POSTGRES_PWD_FILE
BIND_ON_IP=0.0.0.0
TEMPORAL_BROADCAST_ADDRESS="$(getent hosts "$(hostname)" | awk '{print $1; exit}')"
[ -n "$TEMPORAL_BROADCAST_ADDRESS" ] || { echo "cannot resolve own address for broadcast" >&2; exit 1; }
export BIND_ON_IP TEMPORAL_BROADCAST_ADDRESS
mkdir -p /run/temporal/config
dockerize -template /etc/temporal/config/config_template.yaml:/run/temporal/config/docker.yaml
exec temporal-server --root /run/temporal --config config --env docker start
