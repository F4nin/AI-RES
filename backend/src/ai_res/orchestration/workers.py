"""Worker composition for the two task queues (Spec Inc. 7). Manager Runtime hosts the workflow and the Manager Activities on `ai-res-manager`;
Worker Runtime only REGISTERS on `ai-res-workers` (no WorkerRun execution before S23)."""
from temporalio.client import Client
from temporalio.worker import Worker

from ai_res.orchestration.activities import ManagerActivities, WorkerActivities
from ai_res.orchestration.contracts import MANAGER_TASK_QUEUE, WORKER_TASK_QUEUE
from ai_res.orchestration.platform_port import OperationPlatform
from ai_res.orchestration.workflows import OperationWorkflow


def manager_worker(client: Client, platform: OperationPlatform) -> Worker:
    acts = ManagerActivities(platform)
    return Worker(client, task_queue=MANAGER_TASK_QUEUE, workflows=[OperationWorkflow],
                  activities=[acts.acknowledge_operation_start, acts.record_operation_failure, acts.confirm_operation_cancellation])


def worker_runtime_worker(client: Client) -> Worker:
    return Worker(client, task_queue=WORKER_TASK_QUEUE, activities=[WorkerActivities().execute_worker_run])
