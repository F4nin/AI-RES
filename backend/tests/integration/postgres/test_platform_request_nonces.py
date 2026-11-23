"""Verify durable request replay rejection through the narrow database identity."""
from asyncio import gather
from datetime import timedelta
from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege

from ai_res.db.session import create_session_factory
from ai_res.modules.iam.platform_credentials import VerifiedPlatformCredential
from ai_res.modules.iam.platform_nonces import PlatformRequestNonceStore
from ai_res.platform.clock import utc_now
from ai_res.platform.ports import ServiceName

from .conftest import Pg
from .test_repositories import engine_for, world  # noqa: F401

pytestmark = pytest.mark.postgres


async def test_nonce_commits_once_under_competing_db_sessions(migrated: Pg, engine_for):  # noqa: F811
    credential = VerifiedPlatformCredential(ServiceName.MANAGER_RUNTIME, uuid4(), uuid4(), utc_now() + timedelta(seconds=45))
    first = PlatformRequestNonceStore(create_session_factory(engine_for("ai_res_platform_api")))
    second = PlatformRequestNonceStore(create_session_factory(engine_for("ai_res_platform_api")))
    assert sorted(await gather(first.consume(credential), second.consume(credential))) == [False, True]
    restarted = PlatformRequestNonceStore(create_session_factory(engine_for("ai_res_platform_api")))
    assert not await restarted.consume(credential)
    with migrated.connect() as connection:
        assert connection.execute("SELECT count(*) FROM platform.platform_request_nonces WHERE nonce=%s", [credential.nonce]).fetchone() == (1,)


async def test_expired_credential_and_platform_db_privilege_boundary(migrated: Pg, engine_for):  # noqa: F811
    expired = VerifiedPlatformCredential(ServiceName.MANAGER_RUNTIME, uuid4(), uuid4(), utc_now() - timedelta(seconds=1))
    platform = PlatformRequestNonceStore(create_session_factory(engine_for("ai_res_platform_api")))
    assert not await platform.consume(expired)
    with migrated.connect("ai_res_platform_api") as connection:
        assert connection.execute("SELECT pg_has_role(current_user, 'ai_res_api_group', 'MEMBER')").fetchone() == (False,)
        for statement in (
            "SELECT * FROM operations.operations",
            "SELECT * FROM platform.platform_request_nonces",
            "DELETE FROM platform.platform_request_nonces",
            "CREATE TABLE platform.fixture (id int)",
        ):
            with pytest.raises(InsufficientPrivilege):
                connection.execute(statement)
    with migrated.connect("ai_res_api") as public_api, pytest.raises(InsufficientPrivilege):
        public_api.execute(
            "INSERT INTO platform.platform_request_nonces (issuer,nonce,expires_at) VALUES ('MANAGER_RUNTIME',%s,now()+interval '1 min')",
            [uuid4()],
        )
