"""Outbox-side signed delivery using only the live lease proof."""
import ssl
from asyncio import timeout
from datetime import timedelta
from pathlib import Path

import httpx
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from ai_res.modules.events import delivery
from ai_res.modules.events.delivery_lease import DeliveryLease
from ai_res.modules.events.outbox_repository import OutboxRow
from ai_res.modules.iam.platform_credentials import AssignedDeliveryCredentialIssuer, AssignedDeliveryRequest
from ai_res.platform.config import ConfigError

_TRACE_CONTEXT = TraceContextTextMapPropagator()


class AssignedDeliveryClient:
    def __init__(
        self, url: str, *, ca_file: Path, issuer: AssignedDeliveryCredentialIssuer,
        ttl: timedelta, timeout_seconds: float, owner: str,
    ) -> None:
        try:
            origin = httpx.URL(url)
            if (origin.scheme != "https" or not origin.host or origin.userinfo or origin.query or origin.fragment
                    or origin.path not in ("", "/") or not 0 < timeout_seconds <= 60):
                raise ValueError
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=ca_file)
            context.verify_flags |= ssl.VERIFY_X509_STRICT
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except (ValueError, OSError, httpx.InvalidURL):
            raise ConfigError("assigned delivery requires a private HTTPS origin and CA") from None
        self._client = httpx.AsyncClient(base_url=origin, verify=context, timeout=timeout_seconds, trust_env=False, follow_redirects=False)
        self._issuer, self._ttl, self._timeout, self._owner = issuer, ttl, timeout_seconds, owner

    async def aclose(self) -> None:
        await self._client.aclose()

    async def publish(self, row: OutboxRow) -> None:
        lease = DeliveryLease(row_id=row.id, lease_owner=self._owner, attempt=row.attempt_count, replay_count=row.replay_count)
        request = AssignedDeliveryRequest(lease.model_dump_json(by_alias=True).encode())
        token = self._issuer.issue(request, ttl=self._ttl)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept-Encoding": "identity"}
        _TRACE_CONTEXT.inject(headers)
        try:
            async with timeout(self._timeout), self._client.stream("POST", request.path, content=request.body, headers=headers) as response:
                if response.status_code == 204 and response.headers.get("cache-control") == "no-store":
                    return
                if response.status_code in (413, 422):
                    raise delivery.PermanentDeliveryError(delivery.SCHEMA_REJECTED)
                raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED)
        except (TimeoutError, httpx.HTTPError):
            raise delivery.TransientDeliveryError(delivery.PUBLISH_FAILED) from None
