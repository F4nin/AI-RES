"""Versioned policy configuration (ADR-017): strict parsing, pinned checksum, deny-by-default.

The configuration lives in the repository next to its SHA-256 (`policy_config.sha256`); both change in the same reviewed PR. A missing/invalid
file, a checksum mismatch, a duplicate or unknown key, an unknown role or a missing version all raise PolicyConfigError and the engine starts in
DENY-ALL mode (it never falls back to something permissive). The role->action matrix is WORKING (IAM v1.5 §4: "starting vocabulary, not the final
matrix") and is limited to the actions introduced by the stages implemented so far.
"""
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from typing import Any

ORG_ROLES = frozenset({"ORGANIZATION_OWNER", "ORGANIZATION_ADMIN", "AUDITOR"})
PROJECT_ROLES = frozenset({"PROJECT_ADMIN", "ANALYST", "REVIEWER_APPROVER", "READ_ONLY_VIEWER", "AUDITOR"})  # mirrors the iam.roles seed (migration 0002)
_VERSION = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\.[0-9]+\Z")
_ACTION = re.compile(r"\A[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+\Z")
_RESOURCE = re.compile(r"\A[A-Z][A-Z0-9_]*\Z")
_TOP_KEYS = {"schemaVersion", "version", "status", "privilegedRoles", "actions"}
_ACTION_KEYS = {"resourceType", "allow", "requiresMfa", "humanOnly", "approvalRequired", "auditAllow"}
_ALLOW_KEYS = {"self", "orgRoles", "projectRoles"}


class PolicyConfigError(Exception):
    """The policy configuration cannot be trusted. The message names the problem, never contents of unrelated files."""


@dataclass(frozen=True, slots=True)
class ActionRule:
    action: str
    resource_type: str
    self_allowed: bool
    org_roles: frozenset[str]
    project_roles: frozenset[str]
    requires_mfa: bool
    human_only: bool
    approval_required: bool
    audit_allow: bool


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    version: str
    status: str
    privileged_roles: frozenset[str]
    actions: Mapping[str, ActionRule]
    sha256: str


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PolicyConfigError(f"duplicate key {key!r}")
        out[key] = value
    return out


def _roles(value: Any, allowed: frozenset[str], where: str) -> frozenset[str]:
    if not isinstance(value, list) or not value or any(not isinstance(r, str) for r in value) or len(set(value)) != len(value):
        raise PolicyConfigError(f"{where}: must be a non-empty list of unique role codes")
    unknown = set(value) - allowed
    if unknown:
        raise PolicyConfigError(f"{where}: role not valid at this level: {sorted(unknown)}")
    return frozenset(value)


def _flag(obj: Mapping[str, Any], key: str, where: str, default: bool) -> bool:
    value = obj.get(key, default)
    if not isinstance(value, bool):
        raise PolicyConfigError(f"{where}.{key}: must be boolean")
    return value


def parse_policy_config(raw: bytes, expected_sha256: str) -> PolicyConfig:
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected_sha256.strip().lower()):
        raise PolicyConfigError("checksum mismatch")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyConfigError("not valid JSON") from exc
    if not isinstance(data, dict) or set(data) != _TOP_KEYS:
        raise PolicyConfigError(f"top-level keys must be exactly {sorted(_TOP_KEYS)}")
    if data["schemaVersion"] != 1:
        raise PolicyConfigError("unsupported schemaVersion")  # unknown major version: fail closed
    version = data["version"]
    if not isinstance(version, str) or not _VERSION.match(version):
        raise PolicyConfigError("version must look like YYYY-MM-DD.N")
    if data["status"] not in ("WORKING", "BASELINED"):
        raise PolicyConfigError("status must be WORKING or BASELINED")
    privileged = _roles(data["privilegedRoles"], ORG_ROLES | PROJECT_ROLES, "privilegedRoles")
    actions_raw = data["actions"]
    if not isinstance(actions_raw, dict) or not actions_raw:
        raise PolicyConfigError("actions must be a non-empty object")
    actions: dict[str, ActionRule] = {}
    for name, rule in actions_raw.items():
        where = f"actions.{name}"
        if not _ACTION.match(name):
            raise PolicyConfigError(f"{where}: invalid action id")
        if not isinstance(rule, dict) or not set(rule) <= _ACTION_KEYS or not {"resourceType", "allow"} <= set(rule):
            raise PolicyConfigError(f"{where}: unknown or missing keys")
        rtype = rule["resourceType"]
        if not isinstance(rtype, str) or not _RESOURCE.match(rtype):
            raise PolicyConfigError(f"{where}.resourceType: invalid")
        allow = rule["allow"]
        if not isinstance(allow, dict) or not allow or not set(allow) <= _ALLOW_KEYS:
            raise PolicyConfigError(f"{where}.allow: must grant something and use only {sorted(_ALLOW_KEYS)}")
        actions[name] = ActionRule(
            action=name, resource_type=rtype, self_allowed=_flag(allow, "self", f"{where}.allow", False),
            org_roles=_roles(allow["orgRoles"], ORG_ROLES, f"{where}.allow.orgRoles") if "orgRoles" in allow else frozenset(),
            project_roles=_roles(allow["projectRoles"], PROJECT_ROLES, f"{where}.allow.projectRoles") if "projectRoles" in allow else frozenset(),
            requires_mfa=_flag(rule, "requiresMfa", where, False), human_only=_flag(rule, "humanOnly", where, False),
            approval_required=_flag(rule, "approvalRequired", where, False), audit_allow=_flag(rule, "auditAllow", where, True))
    return PolicyConfig(version, data["status"], privileged, actions, actual)


def load_packaged_policy() -> PolicyConfig:
    pkg = resources.files("ai_res.policy")
    try:
        return parse_policy_config(pkg.joinpath("policy_config.json").read_bytes(), pkg.joinpath("policy_config.sha256").read_text(encoding="ascii"))
    except OSError as exc:
        raise PolicyConfigError("policy configuration or its checksum is missing") from exc
