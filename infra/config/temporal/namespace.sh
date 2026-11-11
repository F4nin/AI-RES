#!/bin/sh
# One-shot, idempotent creation of the `ai-res` namespace (ADR-028). Retention is a WORKING dev default (OD-02), overridable.
set -eu
NS=ai-res
if out="$(temporal operator namespace describe --address temporal:7233 -n "$NS" 2>&1)"; then
  echo "namespace $NS exists"
else
  case "$out" in
    *"not found"*|*"NotFound"*|*"does not exist"*) temporal operator namespace create --address temporal:7233 -n "$NS" --retention "${AI_RES_TEMPORAL_RETENTION:-72h}" ;;
    *) echo "$out" >&2; echo "cannot determine namespace state" >&2; exit 1 ;;
  esac
fi
