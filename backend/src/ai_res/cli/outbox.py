"""`python -m ai_res.cli.outbox status | replay --event-id UUID [--event-id UUID …] --confirm`

Operator tool for the Outbox, run under the `ai_res_outbox_dispatcher` identity (docs/runbooks/outbox.md). `status` prints counts, the age of the
oldest undelivered row and the growth alerts - never ids or content. `replay` puts explicitly named QUARANTINED events back into delivery (there is no
replay-all) and needs `--confirm`; who may approve a replay is WORKING (Event Model v1.4 §18) and not decided here.
Exit codes: 0 ok · 2 refused (missing confirmation, or some named event was not quarantined) · 3 `status` found growth alerts
· 1 configuration/connection error.
"""
import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence
from uuid import UUID

from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.events.alerts import GrowthThresholds, evaluate_outbox
from ai_res.modules.events.metrics import EventMetrics
from ai_res.modules.events.outbox_repository import OutboxRepository
from ai_res.platform.config import ConfigError, load_settings


async def _run(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    engine = create_runtime_engine(load_settings(env))
    try:
        async with UnitOfWork(create_session_factory(engine)) as uow:
            repo = OutboxRepository(uow.session)
            if args.command == "status":
                s = await repo.stats()
                print(f"pending={s.pending}\nin_flight={s.in_flight}\nquarantined={s.quarantined}\npublished={s.published}\n"
                      f"oldest_undelivered_age_seconds={s.oldest_undelivered_age_seconds:.0f}")
                alerts = evaluate_outbox(s, GrowthThresholds())
                for alert in alerts:
                    print(f"alert={alert}")
                return 3 if alerts else 0  # a wrapper (cron, monitoring) can see the alert state
            if not args.confirm:
                print("replay refused: --confirm is required", file=sys.stderr)
                return 2
            wanted = len(set(args.event_id))
            replayed = await repo.replay(args.event_id)
            print(f"replayed={replayed}\nnot_replayed={max(wanted - replayed, 0)}")  # event ids that were not quarantined are counted, never silently ignored
            EventMetrics().count("replayed") if replayed else None
            return 0 if replayed >= wanted else 2
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai_res.cli.outbox", description="Outbox status and controlled replay.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    replay = sub.add_parser("replay")
    replay.add_argument("--event-id", type=UUID, action="append", required=True)
    replay.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args, os.environ if env is None else env))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - a traceback could carry SQL parameters; print the class only
        print(f"outbox command failed: {type(exc).__name__} (details withheld; see the service logs)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
