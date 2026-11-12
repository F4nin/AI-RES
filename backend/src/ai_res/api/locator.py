"""Finds the project that owns a by-id object among the projects the caller may READ (S08 ADR-075), shared by the GET and write routers.

Project-scoped tables are protected by RLS keyed on (organization, project), so a by-id request first has to learn the object's project. It probes only
projects the caller can read, one short transaction each, in the caller's own tenant context: a missing id, an id in a project the caller cannot read and an
id in another organization are indistinguishable (`None`).
"""
import logging
from typing import Any
from uuid import UUID

from ai_res.api.identity import IdentityServices
from ai_res.db.session import UnitOfWork
from ai_res.modules.iam.sessions import AuthenticatedSession
from ai_res.modules.readmodel.queries import ReadQueries
from ai_res.platform.problems import ErrorCode, ProblemError

_log = logging.getLogger("ai_res.api.locator")
PAGE = 100  # OAS maximum page size


class ObjectLocator:
    def __init__(self, services: IdentityServices, *, plain: list[str], priv: list[str], org_roles: list[str]) -> None:
        self._services, self._plain, self._priv, self._org_roles = services, plain, priv, org_roles

    @classmethod
    def from_policy(cls, services: IdentityServices) -> "ObjectLocator":
        """Visibility filter derived from the `project.read` rule (the same grant the read router asserts for every read action)."""
        config = services.enforcer.config
        if config is None or "project.read" not in config.actions:
            raise RuntimeError("policy configuration lacks project.read; refusing to expose by-id lookups")
        rule = config.actions["project.read"]
        return cls(services, plain=sorted(rule.project_roles - config.privileged_roles), priv=sorted(rule.project_roles & config.privileged_roles),
                   org_roles=sorted(rule.org_roles))

    async def readable_projects(self, s: AuthenticatedSession) -> list[UUID]:
        out: list[UUID] = []
        after: list[Any] | None = None
        cap = self._services.settings.read_lookup_max_projects
        while True:
            async with UnitOfWork(self._services.factory) as uow:
                await uow.with_tenant(s.organization_id)
                page = await ReadQueries(uow.session).visible_projects(
                    s.organization_id, s.user_id, plain_roles=self._plain, privileged_roles=self._priv, org_roles=self._org_roles,
                    mfa_verified=s.mfa_verified_at is not None, limit=PAGE, after=after)
            out += [r["id"] for r in page.items]
            if len(out) > cap:
                _log.warning("by-id lookup refused: caller can read more than %d projects", cap)  # WORKING cap; ADR-075 / G-87
                raise ProblemError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Lookup is unavailable for this account; use the project-scoped listing.")
            if not page.has_more:
                return out
            after = [page.items[-1]["created_at"].isoformat(), str(page.items[-1]["id"])]

    async def locate(self, s: AuthenticatedSession, table: str, object_id: UUID) -> UUID | None:
        for project_id in await self.readable_projects(s):
            async with UnitOfWork(self._services.factory) as uow:
                await uow.with_tenant(s.organization_id, project_id)
                if await ReadQueries(uow.session).exists_in_project(table, object_id, project_id):
                    return project_id
        return None
