"""A pass keeps each project's cursor and gives every configured scope a turn."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.parametrize("post_ack", [False, True])
async def test_scheduler_retries_one_project_without_delaying_another(monkeypatch, tmp_path: Path, post_ack):
    from ai_res.application import reconcile_scheduler as module
    from ai_res.application.reconcile_operations import BoundStartPage

    org, first, second, cursor = (uuid4() for _ in range(4))
    config = module.BoundStartSchedule(
        scopes=(module.ReconciliationScope(organization_id=org, project_id=first),
                module.ReconciliationScope(organization_id=org, project_id=second)),
        page_size=2, interval_seconds=1, page_timeout_seconds=4, rpc_timeout_seconds=1,
        server_name="temporal.internal", ca_file=tmp_path / "ca", certificate_file=tmp_path / "cert", private_key_file=tmp_path / "key",
        admitted_operation_types=("MANAGER_MESSAGE", "PLAN_EXECUTION") if post_ack else ("MANAGER_MESSAGE",),
        include_post_ack=post_ack,
    )
    page = AsyncMock(side_effect=[BoundStartPage(2, 0, cursor), BoundStartPage(1, 1, None), TimeoutError(),
                                  BoundStartPage(0, 0, None), BoundStartPage(1, 0, None), BoundStartPage(0, 0, None),
                                  BoundStartPage(0, 0, None), BoundStartPage(0, 0, None)])
    monkeypatch.setattr(module, "reconcile_bound_start_page", page)
    scheduler = module.BoundStartScheduler(AsyncMock(), AsyncMock(), config)
    for _ in range(4):
        await scheduler.run_once()

    calls = [call.kwargs for call in page.await_args_list]
    assert [call["project_id"] for call in calls] == [first, second] * 4
    assert [call["after"] for call in calls] == [None, None, cursor, None, cursor, None, None, None]
    assert all(call["organization_id"] == org and call["page_size"] == 2 for call in calls)
    admitted = {"MANAGER_MESSAGE", "PLAN_EXECUTION"} if post_ack else {"MANAGER_MESSAGE"}
    assert all(call["admitted_types"] == admitted and call["include_post_ack"] is post_ack for call in calls)


@pytest.mark.parametrize("mode", ["missing-address", "malformed", "duplicate-scopes", "duplicate-key", "unknown-field", "insufficient-budget"])
def test_reconciliation_config_rejects_unusable_or_ambiguous_settings(tmp_path: Path, mode: str):
    from ai_res.application.reconcile_scheduler import load_bound_start_schedule
    from ai_res.platform.config import ConfigError, Settings

    path = tmp_path / "reconcile.json"
    config = {
        "scopes": [{"organization_id": str(uuid4()), "project_id": str(uuid4())}], "page_size": 2,
        "interval_seconds": 1, "page_timeout_seconds": 4, "rpc_timeout_seconds": 1, "server_name": "temporal.internal",
        "ca_file": str(tmp_path / "ca"), "certificate_file": str(tmp_path / "cert"), "private_key_file": str(tmp_path / "key"),
        "admitted_operation_types": ["MANAGER_MESSAGE"],
    }
    if mode == "duplicate-scopes":
        config["scopes"] *= 2
    if mode == "unknown-field":
        config["allow_all_projects"] = True
    if mode == "insufficient-budget":
        config["page_timeout_seconds"] = 1
    if mode == "duplicate-key":
        from ai_res.application.reconcile_scheduler import BoundStartSchedule

        valid_json = json.dumps(config)
        needle = '"admitted_operation_types": ["MANAGER_MESSAGE"]'
        assert needle in valid_json
        BoundStartSchedule.model_validate_json(valid_json)  # control: this schedule is valid without the repeated key
        path.write_text(valid_json.replace(needle, needle + ', "admitted_operation_types": ["PLAN_EXECUTION"]'))
    else:
        path.write_text("{" if mode == "malformed" else json.dumps(config))
    settings = Settings(reconciliation_config_file=path, temporal_address=None if mode == "missing-address" else "127.0.0.1:7233")
    with pytest.raises(ConfigError, match="reconciliation"):
        load_bound_start_schedule(settings)


@pytest.mark.parametrize(("admitted", "post_ack", "expected"), [
    (None, True, {"MANAGER_MESSAGE"}),
    (("PLAN_EXECUTION",), False, {"PLAN_EXECUTION"}),
    (("MANAGER_MESSAGE",), True, {"MANAGER_MESSAGE"}),
])
def test_post_ack_flag_never_changes_admitted_operation_types(tmp_path: Path, admitted, post_ack, expected):
    from ai_res.application.reconcile_scheduler import BoundStartSchedule, BoundStartScheduler, ReconciliationScope

    kwargs = {} if admitted is None else {"admitted_operation_types": admitted}
    config = BoundStartSchedule(
        scopes=(ReconciliationScope(organization_id=uuid4(), project_id=uuid4()),), page_size=1,
        interval_seconds=1, page_timeout_seconds=4, rpc_timeout_seconds=1, server_name="temporal.internal",
        ca_file=tmp_path / "ca", certificate_file=tmp_path / "cert", private_key_file=tmp_path / "key",
        include_post_ack=post_ack, **kwargs,
    )
    scheduler = BoundStartScheduler(AsyncMock(), AsyncMock(), config)
    assert scheduler._admitted_types == expected


@pytest.mark.parametrize("operation_types", [[], ["MANAGER_MESSAGE", "MANAGER_MESSAGE"], ["UNKNOWN"], ["TASK_EXECUTION"]])
def test_reconciliation_config_requires_explicit_admitted_types(tmp_path: Path, operation_types: list[str]):
    from ai_res.application.reconcile_scheduler import load_bound_start_schedule
    from ai_res.platform.config import ConfigError, Settings

    path = tmp_path / "reconcile.json"
    path.write_text(json.dumps({
        "scopes": [{"organization_id": str(uuid4()), "project_id": str(uuid4())}],
        "admitted_operation_types": operation_types, "page_size": 1, "interval_seconds": 1,
        "page_timeout_seconds": 4, "rpc_timeout_seconds": 1, "server_name": "temporal.internal",
        "ca_file": str(tmp_path / "ca"), "certificate_file": str(tmp_path / "cert"),
        "private_key_file": str(tmp_path / "key"),
    }))
    with pytest.raises(ConfigError, match="reconciliation"):
        load_bound_start_schedule(Settings(reconciliation_config_file=path, temporal_address="127.0.0.1:7233"))


async def test_reconciliation_retries_initial_connection_and_awaits_cancellation(monkeypatch, tmp_path: Path):
    from opentelemetry import trace

    from ai_res.application import reconcile_scheduler as module
    from ai_res.platform.config import load_settings

    ca, cert, private = (tmp_path / name for name in ("ca", "cert", "key"))
    for path in (ca, cert, private):
        path.write_bytes(path.name.encode())
    schedule = module.BoundStartSchedule(
        scopes=(module.ReconciliationScope(organization_id=uuid4(), project_id=uuid4()),),
        page_size=1, interval_seconds=0.001, page_timeout_seconds=2, rpc_timeout_seconds=1,
        server_name="temporal.internal", ca_file=ca, certificate_file=cert, private_key_file=private,
    )
    config = tmp_path / "schedule.json"
    config.write_text(schedule.model_dump_json())
    settings = load_settings({"AI_RES_RECONCILIATION_CONFIG_FILE": str(config), "AI_RES_TEMPORAL_ADDRESS": "127.0.0.1:7233"})
    connected = AsyncMock(side_effect=[RuntimeError("connection failed"), object()])
    monkeypatch.setattr(module, "connect", connected)
    started, stopped = asyncio.Event(), asyncio.Event()

    async def run_forever(self):
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    monkeypatch.setattr(module.BoundStartScheduler, "run_forever", run_forever)
    async with module.start_bound_reconciliation(settings, AsyncMock(), trace.get_tracer(__name__)), asyncio.timeout(1):
        await started.wait()
    assert connected.await_count == 2
    assert stopped.is_set()
    tls = connected.await_args.kwargs["tls"]
    assert (tls.domain, tls.server_root_ca_cert, tls.client_cert, tls.client_private_key) == ("temporal.internal", b"ca", b"cert", b"key")


async def test_bound_observer_treats_an_unknown_temporal_status_as_scope_mismatch():
    from datetime import timedelta
    from types import SimpleNamespace

    from temporalio.api.common.v1 import WorkflowExecution, WorkflowType
    from temporalio.api.workflow.v1 import WorkflowExecutionInfo
    from temporalio.api.workflowservice.v1 import DescribeWorkflowExecutionResponse

    from ai_res.application.observe_operations import BoundExecutionObservationRequest, TemporalExecutionObserver
    from ai_res.modules.operations.reconciliation import ExecutionState
    from ai_res.orchestration.contracts import MANAGER_INTAKE_WORKFLOW, MANAGER_TASK_QUEUE, workflow_id_for

    binding = BoundExecutionObservationRequest(uuid4(), uuid4(), MANAGER_INTAKE_WORKFLOW, uuid4(), "test")
    execution = WorkflowExecution(workflow_id=workflow_id_for(binding.operation_id), run_id=str(binding.workflow_run_id))
    describe = AsyncMock(return_value=DescribeWorkflowExecutionResponse(workflow_execution_info=WorkflowExecutionInfo(
        execution=execution, type=WorkflowType(name=binding.workflow_type), task_queue=MANAGER_TASK_QUEUE, status=999,
    )))
    client = SimpleNamespace(namespace=binding.namespace, workflow_service=SimpleNamespace(describe_workflow_execution=describe))
    result = await TemporalExecutionObserver(client, deadline=timedelta(seconds=1)).observe(binding)
    assert result.state is ExecutionState.SCOPE_MISMATCH
    describe.assert_awaited_once()
    assert describe.await_args.args[0].execution == execution
    assert describe.await_args.kwargs == {"retry": False, "timeout": timedelta(seconds=1)}
