"""Backend-owned delivery of trusted, leased assigned Outbox rows."""
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.service import TLSConfig

from ai_res.application.reconcile_operations import (
    bind_verified_initial_run,
    has_confirmed_start,
    has_settled_cancellation,
    prepare_assigned_start,
)
from ai_res.modules.events import delivery
from ai_res.modules.events.outbox_repository import OutboxRow, validate_assigned_namespace
from ai_res.modules.events.temporal_start import AssignedTemporalCancelPublisher, AssignedTemporalStartPublisher
from ai_res.orchestration.client import AssignedOperationCanceller, AssignedOperationStarter
from ai_res.orchestration.contracts import CANCEL_DESTINATION, START_DESTINATION, AssignedCancellation, AssignedWorkflowInput
from ai_res.platform.config import ConfigError


def _direct_mtls(client: Client) -> TLSConfig:
    config = client.service_client.config
    tls = config.tls
    if (not isinstance(tls, TLSConfig) or not tls.server_root_ca_cert or not tls.domain
            or not tls.client_cert or not tls.client_private_key or config.http_connect_proxy_config is not None):
        raise ConfigError("assigned delivery requires direct Temporal mTLS with an explicit CA and server name")
    if config.api_key is not None or any(name.lower() == "authorization" for name in config.rpc_metadata):
        raise ConfigError("assigned Temporal clients accept only mTLS authentication")
    return tls


class AssignedDeliveryBackend:
    """Owns admission and binding. Run references come from the protected Start RPC."""

    def __init__(
        self, factory: async_sessionmaker[AsyncSession], *,
        start_client: Client, cancel_client: Client, cancel_deadline: timedelta,
    ) -> None:
        start_tls, cancel_tls = _direct_mtls(start_client), _direct_mtls(cancel_client)
        if (start_client.namespace != cancel_client.namespace
                or start_client.service_client.config.target_host != cancel_client.service_client.config.target_host
                or (start_tls.server_root_ca_cert, start_tls.domain, start_tls.verification_server_name)
                != (cancel_tls.server_root_ca_cert, cancel_tls.domain, cancel_tls.verification_server_name)):
            raise ConfigError("Start and Cancel must target the same protected Temporal namespace")
        if start_tls.client_cert == cancel_tls.client_cert or start_tls.client_private_key == cancel_tls.client_private_key:
            raise ConfigError("Start and Cancel require separate Temporal identities")
        validate_assigned_namespace(start_client.namespace)
        self._factory = factory
        self._namespace = start_client.namespace
        self._start = AssignedTemporalStartPublisher(
            AssignedOperationStarter(start_client), self._bind_start, self._confirmed_start, self._prepare_start,
        )
        self._cancel = AssignedTemporalCancelPublisher(AssignedOperationCanceller(cancel_client, deadline=cancel_deadline), self._settled_cancel)

    @property
    def namespace(self) -> str:
        return self._namespace

    async def publish(self, row: OutboxRow) -> None:
        """Dispatch a row obtained by the trusted Outbox claim path."""
        if row.dispatch_namespace != self._namespace:
            raise delivery.PermanentDeliveryError(delivery.ENVELOPE_MISMATCH)
        if row.destination == START_DESTINATION:
            await self._start.publish(row)
        elif row.destination == CANCEL_DESTINATION:
            await self._cancel.publish(row)
        else:
            raise delivery.PermanentDeliveryError(delivery.NO_CONSUMER)

    async def _prepare_start(self, request: AssignedWorkflowInput, operation_type: str) -> bool:
        return await prepare_assigned_start(self._factory, request, operation_type=operation_type, namespace=self._namespace)

    async def _bind_start(self, request: AssignedWorkflowInput, operation_type: str, run_id: UUID) -> bool:
        return await bind_verified_initial_run(
            self._factory, request, operation_type=operation_type, namespace=self._namespace, run_id=run_id,
        )

    async def _confirmed_start(self, request: AssignedWorkflowInput, operation_type: str) -> bool:
        return await has_confirmed_start(self._factory, request, operation_type=operation_type, namespace=self._namespace)

    async def _settled_cancel(self, request: AssignedCancellation) -> bool:
        return await has_settled_cancellation(self._factory, request, namespace=self._namespace)
