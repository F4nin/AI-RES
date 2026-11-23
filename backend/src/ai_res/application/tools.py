"""Composition of the S17 tool catalogue with backend-owned PostgreSQL ports."""
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_res.db.session import UnitOfWork
from ai_res.modules.audit.writer import SqlAuditWriter
from ai_res.modules.operations.repository import OperationRepository
from ai_res.modules.projects.repository import ProjectRepository
from ai_res.modules.tasks.repository import TaskRepository
from ai_res.modules.tools.contracts import (
    JsonObject,
    SideEffect,
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolErrorCode,
    ToolKind,
    ToolLimits,
    ToolRef,
    ToolSubject,
)
from ai_res.modules.tools.gateway import ToolGateway
from ai_res.modules.tools.grants import WorkerToolGrant
from ai_res.modules.tools.registry import ToolRegistry
from ai_res.modules.tools.repository import SqlWorkerToolGrants
from ai_res.modules.worker_runs.repository import WorkerRunRepository
from ai_res.policy.tool_authority import WorkerToolPolicy

PROJECT_READ = ToolRef("project.metadata.read", "1.0")
WORKER_ROLES = frozenset({
    "ELICITATION", "RESEARCH", "BUSINESS_ANALYSIS", "REQUIREMENTS", "SYSTEM_ANALYSIS", "API_INTEGRATION",
    "MODELING_DIAGRAM_VALIDATION", "QUALITY_ASSURANCE", "TRACEABILITY_CHANGE",
})


def project_tool_registry(limits: ToolLimits, *, environment: str) -> ToolRegistry:
    return ToolRegistry([ToolDefinition(
        ref=PROJECT_READ, name="Read project metadata", description="Read the current project's name, type and status.",
        owner="project", provider="ai-res", adapter_id=PROJECT_READ.tool_id, contract_version="1.0",
        kind=ToolKind.LOCAL, operation="read", resource_type="PROJECT", stateful=True, side_effect=SideEffect.NONE,
        risk="LOW", required_scope="project.read", worker_types=WORKER_ROLES,
        classifications=frozenset({"INTERNAL"}), environments=frozenset({environment}),
        input_schema='{"type":"object","additionalProperties":false}',
        output_schema="""{
            "type":"object","additionalProperties":false,
            "required":["projectId","name","projectType","status"],
            "properties":{
                "projectId":{"type":"string","format":"uuid"},
                "name":{"type":"string"},
                "projectType":{"type":"string"},
                "status":{"type":"string"}
            }
        }""",
        limits=limits,
    )])


class ProjectMetadataAdapter:
    available = True

    def __init__(self, projects: ProjectRepository) -> None:
        self._projects = projects

    async def execute(self, subject: ToolSubject, call: ToolCall, arguments: JsonObject) -> object:
        if call.target.resource_id != subject.project_id:
            raise ToolError(ToolErrorCode.AUTHORIZATION)
        project = await self._projects.get(subject.project_id)
        if project is None or project.organization_id != subject.organization_id:
            raise ToolError(ToolErrorCode.NOT_FOUND)
        return {"projectId": str(project.id), "name": project.name, "projectType": project.project_type,
                "status": project.status}


class CurrentWorkerToolAuthority:
    def __init__(self, session: AsyncSession, grants: SqlWorkerToolGrants) -> None:
        self._runs = WorkerRunRepository(session)
        self._tasks = TaskRepository(session)
        self._operations = OperationRepository(session)
        self._grants = grants

    async def get(self, subject: ToolSubject, grant_id: UUID) -> WorkerToolGrant | None:
        grant = await self._grants.get(subject, grant_id)
        if grant is None:
            return None
        run = await self._runs.get(subject.run_id)
        if run is None or run.task_id != subject.task_id:
            return None
        task = await self._tasks.get_task(run.task_id)
        if task is None or task.epic_id != subject.epic_id:
            return None
        if not await self._operations.lock_open_for_tool(run.operation_id):
            return None
        if not await self._runs.is_tool_call_active(
            run.id, definition_version_id=subject.worker_definition_version_id, worker_role=subject.worker_type,
        ):
            return None
        return grant


class ProjectToolService:
    """Backend-only service. The caller must establish the authenticated subject before calling."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], *, limits: ToolLimits, environment: str,
        policy_timeout: float, audit_timeout: float,
    ) -> None:
        self._factory = factory
        self._registry = project_tool_registry(limits, environment=environment)
        self._policy_timeout = policy_timeout
        self._audit_timeout = audit_timeout

    async def invoke(self, subject: ToolSubject, call: ToolCall, arguments: object) -> JsonObject:
        failure: ToolError | None = None
        try:
            async with UnitOfWork(self._factory) as uow:
                await uow.with_tenant(subject.organization_id, subject.project_id)
                grants = SqlWorkerToolGrants(uow.session)
                gateway = ToolGateway(
                    self._registry, WorkerToolPolicy(CurrentWorkerToolAuthority(uow.session, grants)), SqlAuditWriter(uow.session), grants.claim_rate,
                    {PROJECT_READ.tool_id: ProjectMetadataAdapter(ProjectRepository(uow.session))},
                    policy_timeout=self._policy_timeout, audit_timeout=self._audit_timeout,
                )
                try:
                    result = await gateway.invoke(subject, call, arguments)
                except ToolError as error:
                    if error.code is ToolErrorCode.UNAVAILABLE:
                        raise
                    failure = error
                    result = {}
        except SQLAlchemyError:
            raise ToolError(ToolErrorCode.UNAVAILABLE) from None
        if failure is not None:
            # Expected rejections are returned after their audit record commits.
            raise failure
        return result
