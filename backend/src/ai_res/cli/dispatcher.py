"""`python -m ai_res.cli.dispatcher` - the Outbox dispatcher process under the `ai_res_outbox_dispatcher` identity (closes G-98 for the start route).

Routes: `orchestration.operation-start` -> TemporalStartPublisher. The dispatcher claims ONLY the destinations it has routes for (ADR-089), so events of other
destinations stay PENDING for their future consumers instead of being quarantined as NO_CONSUMER. Credentials: DB password file and nothing else; Temporal
frontend address on the internal network. Exit: 0 after a graceful stop, 1 on configuration/connection errors."""
import asyncio
import contextlib
import logging
import os
import signal
import socket
import sys
from collections.abc import Mapping

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import create_session_factory
from ai_res.modules.events.contract import EventContract
from ai_res.modules.events.dispatcher import Dispatcher, DispatcherConfig, InternalFanoutPublisher
from ai_res.modules.events.temporal_start import TemporalCancelPublisher, TemporalStartPublisher
from ai_res.orchestration.client import OperationCanceller, OperationStarter, connect
from ai_res.orchestration.contracts import CANCEL_DESTINATION, START_DESTINATION
from ai_res.platform.config import ConfigError, load_settings
from ai_res.platform.redaction import configure_logging

log = logging.getLogger("ai_res.dispatcher")


async def _run(env: Mapping[str, str]) -> None:
    settings = load_settings(env)
    configure_logging(settings.log_level)
    if settings.asyncapi_contract_file is None:
        raise ConfigError("asyncapi_contract_file is required (the dispatcher validates every event against the contract)")
    contract = EventContract.from_file(settings.asyncapi_contract_file)
    client = await connect(settings)
    starter, canceller = TemporalStartPublisher(OperationStarter(client)), TemporalCancelPublisher(OperationCanceller(client))
    publisher = InternalFanoutPublisher({START_DESTINATION: [starter.publish], CANCEL_DESTINATION: [canceller.publish]})
    engine = create_runtime_engine(settings)
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    try:
        config = DispatcherConfig(owner=f"{socket.gethostname()}-{os.getpid()}", destinations=(START_DESTINATION, CANCEL_DESTINATION))
        await Dispatcher(create_session_factory(engine), publisher, contract, config).run_forever(stop)
    finally:
        await engine.dispose()


def main(env: Mapping[str, str] | None = None) -> int:
    try:
        asyncio.run(_run(os.environ if env is None else env))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
