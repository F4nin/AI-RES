#!/bin/sh
# Dedicated candidate build only. No inherited proxy/provider/config overrides.
set +x
set +a
set -eu
umask 077
fail() { printf '%s\n' 'Candidate bootstrap refused' >&2; exit 1; }
[ "$#" -eq 0 ] || fail
[ -d /app/data ] && [ ! -L /app/data ] || fail
[ -z "$(ls -A /app/data)" ] || fail
/usr/bin/env -i PATH=/usr/bin:/bin /bin/sh /poc/start-bifrost.sh --render-only
exec /usr/bin/env -i PATH=/usr/bin:/bin /app/main -app-dir /app/data -host 0.0.0.0 -port 8080 -log-level warn -log-style json
