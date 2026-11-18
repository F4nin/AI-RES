"""Explicit development launch of the existing guarded candidate composition.

`probe` remains dry-run unless --execute is supplied. `control` serves only the
private TLS candidate app, using the existing host gate before every claim.
This command creates no account, descriptor, credential, profile or approval and
does not launch containers. Trusted setup supplies all protected files/runtime.
"""
import argparse
import asyncio
import ipaddress
import os
import ssl
import sys
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import NoReturn

import uvicorn

from ai_res.api.poc_admission_api import create_poc_admission_app
from ai_res.api.serve_candidate import serving_tls
from ai_res.cli import flash_candidate
from ai_res.cli.candidate_composition import candidate_control_host, candidate_runner_host
from ai_res.modules.iam.service_tokens import verifier_from_settings
from ai_res.modules.model_registry.candidate_host import DockerCandidateObserver
from ai_res.modules.model_registry.candidate_runner import CandidateRunDenied, CandidateRunManifest, CandidateRunner
from ai_res.platform.config import Settings, load_settings

_ROOT = Path(__file__).resolve().parents[4]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default includes supplied arguments, which may contain
        # misrouted credentials. The operator boundary emits fixed text only.
        raise CandidateRunDenied("HOST_UNCONFIGURED")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="ai_res.cli.candidate_launch", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe", help="one synthetic case; dry-run by default")
    probe.add_argument("--case", required=True, choices=("TEXT", "JSON", "TOOL", "SSE", "CANCEL", "TIMEOUT"))
    probe.add_argument("--execute", action="store_true")
    probe.add_argument("--evidence-file", type=Path)
    probe.add_argument("--virtual-key-file", type=Path)
    probe.add_argument("--timeout-seconds", type=float, default=10.0)
    control = commands.add_parser("control", help="private TLS guarded claim/accounting app")
    control.add_argument("--tls-cert-file", type=Path, required=True)
    control.add_argument("--tls-key-file", type=Path, required=True)
    control.add_argument("--bind-address", default="127.0.0.1")
    control.add_argument("--port", type=int, default=8443)
    for command in (probe, control):
        command.add_argument("--host-config", type=Path, required=command is control)
        command.add_argument("--docker-executable", type=Path, default=Path("/usr/local/bin/docker"))
        command.add_argument("--docker-socket", type=Path, default=Path("/var/run/docker.sock"))
    return parser


def _private_listener(address: str, port: int) -> None:
    try:
        ip = ipaddress.ip_address(address)
        valid = (ip.is_loopback or ip.is_private and not ip.is_reserved) and not (ip.is_unspecified or ip.is_multicast or ip.is_link_local)
    except ValueError:
        valid = False
    if not valid or not 1 <= port <= 65535:
        raise CandidateRunDenied("HOST_UNCONFIGURED")


async def serve_control(args: argparse.Namespace, settings: Settings, observer: DockerCandidateObserver) -> None:
    """Keep existing guarded resources alive exactly while the TLS server runs."""
    _private_listener(args.bind_address, args.port)
    certificate, key = serving_tls({"AI_RES_CANDIDATE_TLS_CERT_FILE": str(args.tls_cert_file),
                                    "AI_RES_CANDIDATE_TLS_KEY_FILE": str(args.tls_key_file)})
    verifier = verifier_from_settings(settings)
    async with candidate_control_host(args.host_config, _ROOT, settings, docker_observer=observer) as service:
        app = create_poc_admission_app(service, verifier, enabled=True)
        config = uvicorn.Config(app, host=args.bind_address, port=args.port, ssl_certfile=str(certificate), ssl_keyfile=str(key),
                                ssl_version=ssl.PROTOCOL_TLS_SERVER, access_log=False, log_config=None, log_level="critical",
                                server_header=False, proxy_headers=False)
        await uvicorn.Server(config).serve()


def _probe_args(args: argparse.Namespace) -> list[str]:
    result = ["--case", args.case, "--timeout-seconds", str(args.timeout_seconds)]
    if args.execute:
        result.append("--execute")
    if args.evidence_file is not None:
        result.extend(("--evidence-file", str(args.evidence_file)))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "probe" and not args.execute:
            return flash_candidate.main(_probe_args(args))
        if args.command == "control":
            _private_listener(args.bind_address, args.port)
        elif args.host_config is None or args.virtual_key_file is None or args.evidence_file is None:
            raise CandidateRunDenied("HOST_UNCONFIGURED")
        settings = load_settings(os.environ)
        observer = DockerCandidateObserver(executable=args.docker_executable, socket_path=args.docker_socket)
        if args.command == "control":
            asyncio.run(serve_control(args, settings, observer))
            return 0

        def host_factory(source: flash_candidate.CandidateSourceBinding,
                         evidence: Path) -> AbstractAsyncContextManager[tuple[CandidateRunner, CandidateRunManifest]]:
            # flash_candidate.main still validates actual source/manifest before
            # running. The existing context owns all resources and gate checks.
            return candidate_runner_host(args.host_config, _ROOT, evidence, settings, args.virtual_key_file, docker_observer=observer)

        return flash_candidate.main(_probe_args(args), host_factory=host_factory)
    except CandidateRunDenied:
        print("candidate launch refused", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except SystemExit as error:
        if error.code == 0:
            return 0
        print("candidate launch failed; details withheld", file=sys.stderr)
        return 1
    except Exception:
        print("candidate launch failed; details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
