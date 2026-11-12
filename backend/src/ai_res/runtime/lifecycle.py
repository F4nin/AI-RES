"""Shared process lifecycle: structured redacting logging, SIGTERM/SIGINT -> graceful stop, fail-fast on configuration errors."""
import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections.abc import Callable, Coroutine, Mapping

from temporalio.worker import Worker

from ai_res.platform.config import ConfigError, Settings, load_settings
from ai_res.platform.export import install_telemetry
from ai_res.platform.redaction import configure_logging

log = logging.getLogger("ai_res.runtime")


async def run_worker_until_stopped(worker: Worker) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    log.info("worker starting", extra={"task_queue": worker.task_queue})
    run = asyncio.ensure_future(worker.run())
    waiter = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({run, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if run.done() and not stop.is_set():  # the poller died on its own: a process that only waits for a signal would look alive and do nothing
            run.result()
            raise RuntimeError("worker stopped unexpectedly")
    finally:
        waiter.cancel()
        if not run.done():
            await worker.shutdown()
            await run
    log.info("worker stopped")


def main_of(run: Callable[[Settings], Coroutine[None, None, None]], env: Mapping[str, str] | None = None, *, service: str = "ai-res-runtime") -> int:
    telemetry = None
    try:
        settings = load_settings(os.environ if env is None else env)
        configure_logging(settings.log_level)
        telemetry = install_telemetry(settings, service)  # fail-open: never raises because of the Collector
        asyncio.run(run(settings))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    finally:
        if telemetry is not None:
            telemetry.shutdown()
    return 0
