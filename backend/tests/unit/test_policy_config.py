"""ADR-017: versioned, checksummed, strictly parsed policy configuration; anything untrustworthy is an error (the engine then denies everything)."""
import hashlib
import json
from typing import Any

import pytest

from ai_res.policy.config import PolicyConfigError, load_packaged_policy, parse_policy_config


def good() -> dict[str, Any]:
    return {"schemaVersion": 1, "version": "2026-11-11.1", "status": "WORKING", "privilegedRoles": ["ORGANIZATION_OWNER"],
            "actions": {"iam.self.read": {"resourceType": "USER", "allow": {"self": True}}}}


def parse(obj: Any = None, raw: bytes | None = None, sha: str | None = None) -> Any:
    data = raw if raw is not None else json.dumps(good() if obj is None else obj).encode()
    return parse_policy_config(data, hashlib.sha256(data).hexdigest() if sha is None else sha)


def test_packaged_configuration_matches_its_pinned_checksum_and_is_marked_working() -> None:
    cfg = load_packaged_policy()
    assert cfg.version and cfg.status == "WORKING" and cfg.actions and cfg.privileged_roles >= {"ORGANIZATION_OWNER", "ORGANIZATION_ADMIN", "PROJECT_ADMIN"}


def test_checksum_mismatch_is_rejected() -> None:
    with pytest.raises(PolicyConfigError, match="checksum"):
        parse(sha="0" * 64)
    with pytest.raises(PolicyConfigError, match="checksum"):
        parse(sha="")


def test_valid_configuration_parses() -> None:
    cfg = parse()
    assert cfg.version == "2026-11-11.1" and cfg.actions["iam.self.read"].self_allowed is True and cfg.actions["iam.self.read"].audit_allow is True


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("version"),
    lambda d: d.update(version="latest"),
    lambda d: d.update(version=""),
    lambda d: d.update(schemaVersion=2),
    lambda d: d.update(status="APPROVED"),
    lambda d: d.update(extra=1),
    lambda d: d.update(actions={}),
    lambda d: d["actions"].update({"BadAction": {"resourceType": "USER", "allow": {"self": True}}}),
    lambda d: d["actions"]["iam.self.read"].update(unknownKey=True),
    lambda d: d["actions"]["iam.self.read"].update(resourceType="user"),
    lambda d: d["actions"]["iam.self.read"].update(allow={}),
    lambda d: d["actions"]["iam.self.read"].update(allow={"orgRoles": ["NOT_A_ROLE"]}),
    lambda d: d["actions"]["iam.self.read"].update(allow={"orgRoles": ["PROJECT_ADMIN"]}),  # project-level role at organization level
    lambda d: d["actions"]["iam.self.read"].update(allow={"projectRoles": ["ORGANIZATION_OWNER"]}),
    lambda d: d["actions"]["iam.self.read"].update(allow={"orgRoles": ["ORGANIZATION_OWNER", "ORGANIZATION_OWNER"]}),
    lambda d: d["actions"]["iam.self.read"].update(allow={"self": "yes"}),
    lambda d: d["actions"]["iam.self.read"].update(requiresMfa="no"),
    lambda d: d.update(privilegedRoles=[]),
])
def test_invalid_shapes_are_rejected(mutate: Any) -> None:
    d = good()
    mutate(d)
    with pytest.raises(PolicyConfigError):
        parse(d)


def test_duplicate_keys_and_garbage_are_rejected() -> None:
    with pytest.raises(PolicyConfigError, match="duplicate"):
        parse(raw=b'{"schemaVersion":1,"schemaVersion":1}')
    for raw in (b"", b"not json", b"[]", b"\xff\xfe"):
        with pytest.raises(PolicyConfigError):
            parse(raw=raw)
