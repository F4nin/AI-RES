"""Disposable auth-control fixture. The Temporal subprocess receives metadata-only access."""
import hmac
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_hex
from threading import Event, Thread

import psycopg
from testcontainers.community.postgres import PostgresContainer

_BINDING = ("spiffe://temporal-auth-poc/manager", "auth-poc", "auth-poc-manager", "workflow")
_REPO = Path(__file__).resolve().parents[2]


@contextmanager
def receipt_fixture(root: Path) -> Iterator[tuple[Event, str]]:
    compose = (_REPO / "infra" / "compose.yaml").read_text()
    pin = re.search(r"image:\s*(postgres:16[^\s]+@sha256:[0-9a-f]{64})", compose)
    if not pin:
        raise RuntimeError("pinned postgres image not found")
    key = token_hex(32)
    database_password = token_hex(24)
    available = Event()
    available.set()
    postgres = PostgresContainer(pin.group(1), username="postgres", password=database_password, dbname="receipt_poc", driver=None)
    postgres.ports["5432"] = ("127.0.0.1", None)  # Docker SDK port binding (host IP, ephemeral port)
    with postgres as pg:
        container = pg.get_wrapped_container()
        container.reload()
        bindings = container.attrs["NetworkSettings"]["Ports"].get("5432/tcp") or []
        if len(bindings) != 1 or bindings[0]["HostIp"] != "127.0.0.1":
            raise RuntimeError("disposable PostgreSQL must publish only to loopback")
        dsn = f"host=127.0.0.1 port={pg.get_exposed_port(5432)} user=postgres dbname=receipt_poc password={database_password} connect_timeout=2"
        with psycopg.connect(dsn) as connection:
            connection.execute("""
                CREATE TABLE receipt (
                    digest bytea PRIMARY KEY CHECK (octet_length(digest) = 32),
                    principal text NOT NULL, namespace text NOT NULL, queue text NOT NULL, kind text NOT NULL
                )
            """)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                return

            def do_POST(self) -> None:
                if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key):
                    self.send_empty(403)
                    return
                if self.path not in {"/register", "/check"} or not available.is_set():
                    self.send_empty(503)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 2048:
                        raise ValueError("invalid receipt fixture length")
                    payload = json.loads(self.rfile.read(length))
                    digest = bytes.fromhex(payload["digest"])
                    binding = tuple(payload[name] for name in ("principal", "namespace", "queue", "kind"))
                    if len(digest) != 32 or binding != _BINDING:
                        raise ValueError("invalid receipt binding")
                    with psycopg.connect(dsn) as connection:
                        if self.path == "/register":
                            connection.execute("INSERT INTO receipt VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (digest, *binding))
                        row = connection.execute("SELECT principal, namespace, queue, kind FROM receipt WHERE digest = %s", [digest]).fetchone()
                except (ValueError, TypeError, KeyError, psycopg.Error):
                    self.send_empty(503)
                    return
                self.send_empty(204 if row == binding else 403)

            def send_empty(self, status: int) -> None:
                self.send_response(status)
                self.end_headers()

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            (root / "receipt-key").write_text(key)
            (root / "receipt-address").write_text(f"127.0.0.1:{server.server_port}")
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield available, dsn
            finally:
                server.shutdown()
                thread.join()
