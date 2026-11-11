#!/bin/sh
# Release gate for persistence (Blueprint §10): runs preflight/postflight/grants/RLS audits and FAILS (exit 1) on any violation row or any psql error.
# Connection comes from the standard libpq environment (PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSFILE/PGPASSWORD, PGSSLMODE, ...).
# Usage: audit.sh [preflight|post]   (default: post = postflight + grants_audit + rls_coverage)
set -eu
dir=$(cd "$(dirname "$0")" && pwd)
case "${1:-post}" in
  preflight) files="preflight.sql" ;;
  post) files="postflight.sql grants_audit.sql rls_coverage.sql" ;;
  *) echo "usage: $0 [preflight|post]" >&2; exit 2 ;;
esac
status=0
for f in $files; do
  [ -s "$dir/$f" ] || { echo "audit file $f is missing or empty" >&2; exit 2; }
  out=$(psql -v ON_ERROR_STOP=1 -tA -f "$dir/$f") || { echo "audit $f failed to run" >&2; exit 2; }
  if [ -n "$out" ]; then echo "VIOLATIONS in $f:"; echo "$out"; status=1; fi
done
[ "$status" -eq 0 ] && echo "persistence audit: no violations"
exit "$status"
