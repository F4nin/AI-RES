# ruff: noqa: E501, S608 -- SQL identifiers come only from the frozen enum mapping
"""Exact-version metadata and append-only context storage; caller owns the UoW."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import canonical_json
from ai_res.modules.context.manifest import ContextManifest
from ai_res.modules.context.types import ContextItemKind
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError

_VERSION_TABLES = {
    ContextItemKind.REQUIREMENT_VERSION: ("requirements.requirement_versions", "requirement_id"),
    ContextItemKind.SOURCE_VERSION: ("sources.source_versions", "source_id"),
    ContextItemKind.ARTIFACT_VERSION: ("artifacts.artifact_versions", "artifact_id"),
}


def not_found() -> ProblemError:
    return ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")


@dataclass(frozen=True, slots=True)
class ContextPackageSnapshot:
    package_id: UUID
    version_id: UUID
    version_number: int
    manifest: ContextManifest

    @property
    def content_hash(self) -> str:
        return self.manifest.content_hash


class ContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save(self, manifest: ContextManifest, actor_id: UUID, *, package_id: UUID | None, expected_version: int | None) -> ContextPackageSnapshot:
        org, project = manifest.organization_id, manifest.project_id
        version_id = new_id()
        if package_id is None:
            if expected_version is not None:
                raise ValueError("expected_version requires package_id")
            package_id, number = new_id(), 1
            await self._s.execute(text("INSERT INTO context.context_packages (id, organization_id, project_id, name, current_version_id, last_version_number, created_by) "
                                       "VALUES (:i,:o,:p,'Explicit context',:v,1,:a)"),
                                  {"i": package_id, "o": org, "p": project, "v": version_id, "a": actor_id})
        else:
            if type(expected_version) is not int or expected_version < 1:
                raise ValueError("existing package requires a positive expected_version")
            row = (await self._s.execute(text("SELECT last_version_number FROM context.context_packages WHERE id=:i AND organization_id=:o AND project_id=:p FOR UPDATE"),
                                               {"i": package_id, "o": org, "p": project})).first()
            if row is None:
                raise not_found()
            if row[0] != expected_version:
                raise ProblemError(ErrorCode.VERSION_CONFLICT, "The resource was modified; reload and retry.")
            number = int(row[0]) + 1
            await self._s.execute(text("UPDATE context.context_packages SET last_version_number=:n,current_version_id=:v,row_version=row_version+1 WHERE id=:i"),
                                  {"n": number, "v": version_id, "i": package_id})
        await self._s.execute(text("INSERT INTO context.context_package_versions (id, organization_id, project_id, context_package_id, version_number, item_count, "
                                   "content_digest, builder_manifest, created_by) VALUES (:i,:o,:p,:pkg,:n,:c,:d,CAST(:m AS jsonb),:a)"),
                              {"i": version_id, "o": org, "p": project, "pkg": package_id, "n": number, "c": len(manifest.items),
                               "d": bytes.fromhex(manifest.content_hash), "m": canonical_json(manifest.to_dict()), "a": actor_id})
        for item in manifest.items:
            column = _VERSION_TABLES[item.ref.kind][1].replace("_id", "_version_id")
            await self._s.execute(text(f"INSERT INTO context.context_package_items (id, organization_id, project_id, context_package_version_id, item_kind, {column}, inclusion_role) "
                                       "VALUES (:i,:o,:p,:v,:k,:r,'PRIMARY')"),  # noqa: S608 -- frozen column allowlist
                                  {"i": new_id(), "o": org, "p": project, "v": version_id, "k": item.ref.kind.value, "r": item.ref.version_id})
        return ContextPackageSnapshot(package_id, version_id, number, manifest)

    async def load(self, org: UUID, project: UUID, version_id: UUID) -> ContextPackageSnapshot:
        row = (await self._s.execute(text("SELECT context_package_id,version_number,content_digest,builder_manifest FROM context.context_package_versions "
                                           "WHERE id=:i AND organization_id=:o AND project_id=:p"), {"i": version_id, "o": org, "p": project})).mappings().first()
        if row is None:
            raise not_found()
        if row["builder_manifest"] is None:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Context manifest unavailable; rebuild the package.")
        try:
            manifest = ContextManifest.from_dict(row["builder_manifest"])
            if manifest.organization_id != org or manifest.project_id != project or bytes.fromhex(manifest.content_hash) != bytes(row["content_digest"]):
                raise ValueError("manifest integrity mismatch")
            actual = (await self._s.execute(text("SELECT item_kind,source_version_id,requirement_version_id,artifact_version_id,rule_version_id,inclusion_role,locator,provenance "
                                                 "FROM context.context_package_items WHERE context_package_version_id=:v"), {"v": version_id})).mappings().all()
            expected = {(x.ref.kind.value, x.ref.version_id) for x in manifest.items}
            actual_refs = {(r["item_kind"], r["source_version_id"] or r["requirement_version_id"] or r["artifact_version_id"]) for r in actual}
            if len(actual) != len(expected) or actual_refs != expected or any((r["item_kind"], r["source_version_id"] or r["requirement_version_id"] or r["artifact_version_id"]) not in expected
                                                   or r["rule_version_id"] is not None or r["inclusion_role"] != "PRIMARY" or r["locator"] is not None or r["provenance"] != {} for r in actual):
                raise ValueError("manifest items mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise ProblemError(ErrorCode.STATE_TRANSITION_NOT_ALLOWED, "Context integrity check failed.") from exc
        return ContextPackageSnapshot(row["context_package_id"], version_id, int(row["version_number"]), manifest)
