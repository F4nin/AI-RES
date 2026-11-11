# ruff: noqa: E501  -- SQL statements stay on one line per clause for review
"""Source / Upload / SourceVersion persistence (ADR-057).

Upload lifecycle: PENDING -> UPLOADED -> VERIFIED | REJECTED | EXPIRED. VERIFIED is reachable only when the checksum and size observed AFTER the upload equal the
declared ones (database CHECK). A SourceVersion is created only from a VERIFIED upload of the same source (database guard) and is idempotent: finalizing the same
upload twice, or ingesting identical content, returns the existing version instead of creating a duplicate.
"""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_res.db.cas import bind_value, cas_update
from ai_res.platform.clock import utc_now
from ai_res.platform.concurrency import StateConflict
from ai_res.platform.ids import new_id
from ai_res.platform.problems import ErrorCode, ProblemError

UPLOAD_UPDATABLE = {"status": None, "actual_size_bytes": None, "verified_sha256": None, "finalized_at": None, "rejection_code": None}


@dataclass(frozen=True)
class NewUpload:
    organization_id: UUID
    project_id: UUID
    source_id: UUID
    object_key: str
    declared_media_type: str
    declared_size_bytes: int
    declared_sha256: bytes
    expires_at: datetime  # UTC; the lifetime itself is WORKING configuration, decided by the caller
    created_by: UUID | None = None


@dataclass(frozen=True)
class FinalizedVersion:
    id: UUID
    created: bool
    is_current: bool


@dataclass(frozen=True)
class UploadRow:
    id: UUID
    source_id: UUID
    status: str
    row_version: int


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create_source(self, org: UUID, prj: UUID, kind: str, title: str, created_by: UUID | None = None) -> UUID:
        sid = new_id()
        await self._s.execute(text("INSERT INTO sources.sources (id, organization_id, project_id, source_kind, title, created_by) VALUES (:id, :o, :p, :k, :t, :by)"),
                              {"id": sid, "o": org, "p": prj, "k": kind, "t": title, "by": created_by})
        return sid

    async def register_upload(self, new: NewUpload) -> UploadRow:
        uid = new_id()
        await self._s.execute(text(
            "INSERT INTO sources.uploads (id, organization_id, project_id, source_id, object_key, declared_media_type, declared_size_bytes, declared_sha256, expires_at, created_by) "
            "VALUES (:id, :o, :p, :s, :k, :mt, :sz, :sha, :exp, :by)"),
            {"id": uid, "o": new.organization_id, "p": new.project_id, "s": new.source_id, "k": new.object_key, "mt": new.declared_media_type, "sz": new.declared_size_bytes,
             "sha": new.declared_sha256, "exp": new.expires_at, "by": new.created_by})
        return UploadRow(uid, new.source_id, "PENDING", 1)

    async def mark_uploaded(self, upload: UploadRow) -> UploadRow:
        version = await cas_update(self._s, "sources.uploads", upload.id, upload.row_version, {"status": "UPLOADED"}, UPLOAD_UPDATABLE)
        return UploadRow(upload.id, upload.source_id, "UPLOADED", version)

    async def verify_upload(self, upload: UploadRow, observed_size: int, observed_sha256: bytes) -> UploadRow:
        """Compares what the object store reports with what was declared. A late upload is EXPIRED and a mismatch is REJECTED with its own code (never processed)."""
        declared = (await self._s.execute(text("SELECT declared_size_bytes, declared_sha256, expires_at, status FROM sources.uploads WHERE id = :id"), {"id": upload.id})).first()
        if declared is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        if declared[3] != "UPLOADED":
            raise StateConflict  # verification is only meaningful after the object arrived
        if utc_now() > declared[2]:
            changes: dict[str, object] = {"status": "EXPIRED"}
        elif int(declared[0]) != observed_size:
            changes = {"status": "REJECTED", "rejection_code": "SIZE_MISMATCH"}
        elif bytes(declared[1]) != observed_sha256:
            changes = {"status": "REJECTED", "rejection_code": "CHECKSUM_MISMATCH"}
        else:
            changes = {"status": "VERIFIED", "actual_size_bytes": observed_size, "verified_sha256": observed_sha256, "finalized_at": utc_now()}
        version = await cas_update(self._s, "sources.uploads", upload.id, upload.row_version, changes, UPLOAD_UPDATABLE)
        return UploadRow(upload.id, upload.source_id, str(changes["status"]), version)

    async def finalize_version(self, org: UUID, prj: UUID, upload: UploadRow, *, received_at: datetime, provenance: dict[str, object], created_by: UUID | None = None) -> "FinalizedVersion":
        """Idempotent: the source row is locked FIRST (serialises finalizers of one source), then the same upload or the same content returns the existing version.
        Identical content that is not the current version is NOT re-activated here: `is_current` tells the caller (reverting to old content is a decision, G-72)."""
        row = (await self._s.execute(text("SELECT source_id, status FROM sources.uploads WHERE id = :id"), {"id": upload.id})).first()  # the DTO is not trusted for ids or state
        if row is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        source_id = row[0]
        locked = (await self._s.execute(text("SELECT current_version_id FROM sources.sources WHERE id = :id FOR UPDATE"), {"id": source_id})).first()
        if locked is None:
            raise ProblemError(ErrorCode.RESOURCE_NOT_FOUND, "Resource not found.")
        if row[1] != "VERIFIED":
            raise StateConflict
        existing = (await self._s.execute(text(
            "SELECT v.id FROM sources.source_versions v JOIN sources.uploads u ON u.source_id = v.source_id WHERE u.id = :u AND (v.upload_id = u.id OR v.checksum_sha256 = u.verified_sha256) LIMIT 1"),
            {"u": upload.id})).first()
        if existing is not None:
            return FinalizedVersion(existing[0], False, existing[0] == locked[0])
        vid = new_id()  # the pointer moves with the counter in one UPDATE; the FK to the version is deferred to COMMIT
        number = int((await self._s.execute(text("UPDATE sources.sources SET last_version_number = last_version_number + 1, current_version_id = :v, row_version = row_version + 1 WHERE id = :id RETURNING last_version_number"),
                                            {"id": source_id, "v": vid})).one()[0])
        await self._s.execute(text(
            "INSERT INTO sources.source_versions (id, organization_id, project_id, source_id, version_number, upload_id, media_type, size_bytes, checksum_sha256, object_key, provenance, received_at, created_by) "
            "SELECT :id, :o, :p, u.source_id, :n, u.id, u.declared_media_type, u.actual_size_bytes, u.verified_sha256, u.object_key, CAST(:pv AS jsonb), :rcv, :by FROM sources.uploads u WHERE u.id = :u"),
            {"id": vid, "o": org, "p": prj, "n": number, "pv": bind_value(provenance, "jsonb"), "rcv": received_at, "by": created_by, "u": upload.id})
        return FinalizedVersion(vid, True, True)
