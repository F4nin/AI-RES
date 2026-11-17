# ruff: noqa: E501 -- fixed schema-qualified SQL in fixtures
"""Owned metadata readers under the real API role: exact versions, scope and no content export."""
import json
from dataclasses import FrozenInstanceError, fields
from uuid import UUID, uuid4

import pytest

from ai_res.application.context import context_resolvers
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.context.types import ContextItemKind
from ai_res.modules.requirements.repository import RequirementRepository
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.platform.version_metadata import VersionMetadata

pytestmark = pytest.mark.postgres
KINDS = tuple(ContextItemKind)
STATEMENT = "The system shall preserve evidence."


@pytest.fixture
def metadata_world(iam_world):
    scopes = [(iam_world.org_a, uuid4()), (iam_world.org_a, uuid4()), (iam_world.org_b, uuid4())]
    ids = {}
    with iam_world.pg.connect() as c:
        for scope_number, (org, project) in enumerate(scopes):
            c.execute("INSERT INTO project.projects (id,organization_id,name,project_type) VALUES (%s,%s,'p','GREENFIELD')", [project, org])
            with c.transaction():
                rid, rv, sid, sv, aid, av = (uuid4() for _ in range(6))
                c.execute("INSERT INTO requirements.requirements (id,organization_id,project_id,display_number,current_version_id,last_version_number) VALUES (%s,%s,%s,1,%s,1)", [rid, org, project, rv])
                c.execute("INSERT INTO requirements.requirement_versions (id,organization_id,project_id,requirement_id,version_number,requirement_type,statement,rationale,priority,acceptance_criteria,constraints_info,provenance_refs,author_type) "
                          "VALUES (%s,%s,%s,%s,1,'FR',%s,'Reason','HIGH','[\"Given evidence\"]'::jsonb,'[{\"constraint\":\"baseline\"}]'::jsonb,'[]'::jsonb,'IMPORT')", [rv, org, project, rid, STATEMENT])
                c.execute("INSERT INTO sources.sources (id,organization_id,project_id,source_kind,title,current_version_id,last_version_number) VALUES (%s,%s,%s,'GIT_REPOSITORY','s',%s,1)", [sid, org, project, sv])
                c.execute("INSERT INTO sources.source_versions (id,organization_id,project_id,source_id,version_number,media_type,size_bytes,checksum_sha256,external_ref,provenance,received_at) "
                          "VALUES (%s,%s,%s,%s,1,'text/plain',3,%s,%s::jsonb,'{}'::jsonb,now())", [sv, org, project, sid, b'\x12' * 32, json.dumps({"revision": "test-1"})])
                c.execute("INSERT INTO artifacts.artifacts (id,organization_id,project_id,artifact_type,source_of_truth_mode,title,current_version_id,last_version_number) "
                          "VALUES (%s,%s,%s,'OPENAPI','NATIVE_SPEC','a',%s,1)", [aid, org, project, av])
                c.execute("INSERT INTO artifacts.artifact_versions (id,organization_id,project_id,artifact_id,version_number,schema_version,content_ref,content_checksum,provenance,author_type) "
                          "VALUES (%s,%s,%s,%s,1,'1','{}'::jsonb,%s,'{}'::jsonb,'IMPORT')", [av, org, project, aid, b'\x34' * 32])
                ids[scope_number] = {ContextItemKind.REQUIREMENT_VERSION: (rid, rv), ContextItemKind.SOURCE_VERSION: (sid, sv), ContextItemKind.ARTIFACT_VERSION: (aid, av)}
    return iam_world, create_session_factory(iam_world.engine()), scopes, ids


@pytest.mark.parametrize("kind", KINDS)
async def test_owned_readers_export_only_exact_version_metadata(metadata_world, kind):
    _, factory, scopes, ids = metadata_world
    org, project = scopes[0]
    object_id, version_id = ids[0][kind]
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(org, project)
        metadata = await context_resolvers(uow.session)[kind].resolve(version_id, org, project)
    assert isinstance(metadata, VersionMetadata)
    assert metadata.object_id == object_id and metadata.version_number == 1
    assert {f.name for f in fields(metadata)} == {"object_id", "version_number", "content_digest"}
    assert STATEMENT not in repr(metadata)
    if kind is ContextItemKind.SOURCE_VERSION:
        assert metadata.content_digest == "12" * 32
    elif kind is ContextItemKind.ARTIFACT_VERSION:
        assert metadata.content_digest == "34" * 32
    else:
        assert metadata.content_digest == "894fdda5e73260af5b791679495f124efd73955f5714f145428466f7da2d1509"
    with pytest.raises(FrozenInstanceError):
        metadata.object_id = uuid4()


@pytest.mark.parametrize("kind", KINDS)
async def test_foreign_and_unknown_versions_have_identical_not_found(metadata_world, kind):
    _, factory, scopes, ids = metadata_world
    org, project = scopes[0]
    failures = []
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(org, project)
        reader = context_resolvers(uow.session)[kind]
        for version_id in (ids[1][kind][1], ids[2][kind][1], uuid4()):
            with pytest.raises(ProblemError) as caught:
                await reader.resolve(version_id, org, project)
            failures.append((caught.value.code, str(caught.value)))
    assert failures[0] == failures[1] == failures[2]
    assert failures[0][0] == ErrorCode.RESOURCE_NOT_FOUND


@pytest.mark.parametrize("kind", KINDS)
async def test_missing_tenant_context_denies_even_with_correct_explicit_scope(metadata_world, kind):
    _, factory, scopes, ids = metadata_world
    org, project = scopes[0]
    async with UnitOfWork(factory) as uow:
        with pytest.raises(ProblemError) as caught:
            await context_resolvers(uow.session)[kind].resolve(ids[0][kind][1], org, project)
    assert caught.value.code == ErrorCode.RESOURCE_NOT_FOUND


async def test_requirement_lifecycle_changes_do_not_change_semantic_digest(metadata_world):
    iam, factory, scopes, ids = metadata_world
    org, project = scopes[0]
    version_id = ids[0][ContextItemKind.REQUIREMENT_VERSION][1]
    async with UnitOfWork(factory) as uow:
        await uow.with_tenant(org, project)
        reader = context_resolvers(uow.session)[ContextItemKind.REQUIREMENT_VERSION]
        before = await reader.resolve(version_id, org, project)
        await RequirementRepository(uow.session).confirm(version_id, iam.user_a)
        after = await reader.resolve(version_id, org, project)
    assert before == after


@pytest.mark.parametrize("number", [0, -1, True])
def test_version_metadata_rejects_invalid_version_numbers(number):
    with pytest.raises(ValueError):
        VersionMetadata(UUID(int=1), number, "12" * 32)
