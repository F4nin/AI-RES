"""`python -m ai_res.runtime.worker` - Worker Runtime: registers on task queue `ai-res-workers`. WorkerRun execution is NOT available before S23 (the only
registered Activity refuses). No database credentials, no Platform API credentials: nothing to call yet."""
from ai_res.orchestration.client import connect
from ai_res.orchestration.workers import worker_runtime_worker
from ai_res.platform.config import Settings
from ai_res.runtime.lifecycle import main_of, run_worker_until_stopped


async def run(settings: Settings) -> None:
    await run_worker_until_stopped(worker_runtime_worker(await connect(settings)))


def main() -> int:
    return main_of(run, service="ai-res-worker-runtime")


if __name__ == "__main__":
    raise SystemExit(main())
