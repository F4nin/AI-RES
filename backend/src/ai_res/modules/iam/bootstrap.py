# ruff: noqa: E501  -- one SQL statement per string keeps each query reviewable
"""One-time bootstrap of the first administrator (Auth v1.1 §3.1, AUTH-004, security.md "Bootstrap и первый admin").

* No default credentials exist anywhere: a freshly migrated database has no organization, user or credential.
* The operator must PRESENT the bootstrap secret (prompt, never argv) and it must equal the Compose secret mounted in the container.
* Everything is created in ONE transaction that ends with the singleton claim row (`platform.bootstrap_state`); a second run, with any secret,
  fails on its primary key. After the first success the bootstrap path is permanently closed.
* The new account is ORGANIZATION_OWNER, a privileged role: it must enrol TOTP before any privileged action (Policy Engine, slice 6).
"""
import hashlib
import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.iam.auth import normalise_email
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy, PasswordPolicyError
from ai_res.platform.clock import utc_now
from ai_res.platform.ids import new_id
from ai_res.platform.ports import AuditOutcome, AuditRecord


class BootstrapError(Exception):
    """Refusal with a stable `code`; the message never contains the secret, the password or the e-mail."""

    def __init__(self, code: str) -> None:
        super().__init__(f"bootstrap refused: {code}")
        self.code = code


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    organization_id: UUID
    user_id: UUID


async def bootstrap_first_admin(factory: async_sessionmaker[AsyncSession], hasher: PasswordHasherService, policy: PasswordPolicy, *, expected_secret: bytes, presented_secret: bytes,
                                organization_name: str, admin_email: str, admin_name: str, password: str, request_id: str | None = None,
                                clock: Callable[[], datetime] = utc_now) -> BootstrapResult:
    if not expected_secret or not presented_secret or not hmac.compare_digest(presented_secret, expected_secret):
        raise BootstrapError("invalid_secret")
    email = normalise_email(admin_email)
    if email is None or "@" not in email:
        raise BootstrapError("invalid_email")
    if not 1 <= len(organization_name.strip()) <= 200 or not 1 <= len(admin_name.strip()) <= 200:
        raise BootstrapError("invalid_name")
    try:
        policy.check(password)
    except PasswordPolicyError as exc:
        raise BootstrapError(f"weak_password_{exc.reason}") from None
    org, user = new_id(), new_id()
    try:
        async with UnitOfWork(factory) as uow:
            await uow.with_tenant(org)  # the new organization's own id: RLS accepts the INSERT of exactly that organization
            s = uow.session
            await s.execute(text("INSERT INTO organization.organizations (id, name) VALUES (:o, :n)"), {"o": org, "n": organization_name.strip()})
            await s.execute(text("INSERT INTO iam.users (id, organization_id, email, email_normalized, display_name) VALUES (:u, :o, :e, :en, :d)"),
                            {"u": user, "o": org, "e": admin_email.strip(), "en": email, "d": admin_name.strip()})
            await s.execute(text("INSERT INTO iam.credentials (id, organization_id, user_id, kind, password_hash) VALUES (:i, :o, :u, 'PASSWORD', :h)"),
                            {"i": new_id(), "o": org, "u": user, "h": hasher.hash(password)})
            await s.execute(text("INSERT INTO organization.memberships (id, organization_id, user_id, role_code) VALUES (:i, :o, :u, 'ORGANIZATION_OWNER')"), {"i": new_id(), "o": org, "u": user})
            await s.execute(text("INSERT INTO platform.bootstrap_state (organization_id, secret_digest) VALUES (:o, :d)"),
                            {"o": org, "d": hashlib.sha256(presented_secret).digest()})  # the claim: a second bootstrap dies here on the primary key
            await SqlAuditWriter(s).write(AuditRecord(action="AUTH_ACCOUNT_INVITED", outcome=AuditOutcome.SUCCEEDED, resource_type="USER", resource_id=str(user), actor_type="SYSTEM",
                                                      organization_id=str(org), request_id=request_id, reason_code="bootstrap_first_administrator",
                                                      details={"role": "ORGANIZATION_OWNER"}), occurred_at=clock())
    except IntegrityError as exc:
        if "pk_bootstrap_state" in str(exc.orig):
            raise BootstrapError("already_bootstrapped") from None
        raise
    return BootstrapResult(org, user)
