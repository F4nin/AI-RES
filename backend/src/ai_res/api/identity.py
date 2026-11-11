"""Identity HTTP surface (overlay contracts/openapi/extensions/identity_auth.yaml + canonical getCurrentUser). Thin: parsing, cookie/CSRF/Origin
enforcement and DTO mapping; every decision is made in the services (modules/iam, policy). Handlers never trust client-supplied identity."""
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ai_res.api.client_ip import parse_trusted_proxies, resolve_client_ip
from ai_res.api.request_security import build_session_cookie, check_state_change_origin, clear_session_cookie_args, constant_time_equal
from ai_res.db.engine import create_runtime_engine
from ai_res.db.session import UnitOfWork, create_session_factory
from ai_res.modules.iam.auth import AuthService
from ai_res.modules.iam.mfa import MfaService
from ai_res.modules.iam.passwords import PasswordHasherService, PasswordPolicy, load_denylist
from ai_res.modules.iam.profile import read_current_user
from ai_res.modules.iam.secretbox import load_secret_box
from ai_res.modules.iam.sessions import AuthenticatedSession, IssuedSession, SessionService
from ai_res.modules.iam.throttle import LoginThrottle, ThrottlePolicy
from ai_res.platform.config import Settings
from ai_res.platform.correlation import current_request_id
from ai_res.platform.ports import PolicyRequest
from ai_res.platform.problems import ErrorCode, ProblemError
from ai_res.policy.config import load_packaged_policy
from ai_res.policy.enforcer import PolicyEnforcer
from ai_res.policy.engine import PolicyEngine


@dataclass(slots=True)
class IdentityServices:
    settings: Settings
    factory: Any
    sessions: SessionService
    auth: AuthService
    mfa: MfaService
    enforcer: PolicyEnforcer
    trusted_proxies: tuple[Any, ...]


def build_identity_services(settings: Settings, factory: Any | None = None) -> IdentityServices:
    """Composition root for the identity services. `factory` is injectable for tests; production builds the runtime engine (least-privilege `ai_res_api`)."""
    factory = factory or create_session_factory(create_runtime_engine(settings))
    sessions = SessionService(factory, idle=timedelta(seconds=settings.session_idle_seconds), absolute=timedelta(seconds=settings.session_absolute_seconds),
                              touch_interval=timedelta(seconds=settings.session_touch_interval_seconds))
    hasher = PasswordHasherService(time_cost=settings.argon2_time_cost, memory_kib=settings.argon2_memory_kib, parallelism=settings.argon2_parallelism)
    policy = PasswordPolicy(load_denylist(settings.password_denylist_file), settings.password_min_length)
    throttle = LoginThrottle(ThrottlePolicy(
        settings.login_account_ip_threshold, settings.login_ip_threshold, settings.login_account_threshold, settings.login_global_threshold,
        timedelta(seconds=settings.login_delay_base_seconds), timedelta(seconds=settings.login_delay_max_seconds),
        timedelta(seconds=settings.login_window_seconds), enforce_ip_global=settings.login_enforce_ip_global))
    mfa = MfaService(factory, sessions, load_secret_box(settings), throttle, issuer=settings.mfa_issuer, window=settings.mfa_window_steps)
    config = load_packaged_policy()
    enforcer = PolicyEnforcer(PolicyEngine(config, factory), factory, config, timeout_seconds=settings.policy_timeout_seconds)
    return IdentityServices(settings, factory, sessions, AuthService(factory, sessions, hasher, policy, throttle), mfa, enforcer,
                            parse_trusted_proxies(settings.trusted_proxy_cidrs))


class _Body(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=False, extra="forbid", str_strip_whitespace=False)


class LoginBody(_Body):
    organization_id: UUID | None = None
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class ReauthBody(_Body):
    current_password: str = Field(min_length=1, max_length=1024, repr=False)


class ChangePasswordBody(_Body):
    current_password: str = Field(min_length=1, max_length=1024, repr=False)
    new_password: str = Field(min_length=1, max_length=1024, repr=False)


class MfaCodeBody(_Body):
    code: str = Field(min_length=6, max_length=64, repr=False)


def _unauthenticated() -> ProblemError:
    return ProblemError(ErrorCode.AUTHENTICATION_REQUIRED, "Authentication required.")


def _iso(value: Any) -> str:
    return str(value.isoformat()).replace("+00:00", "Z")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def register_identity(app: FastAPI, services: IdentityServices) -> None:
    settings = services.settings
    router = APIRouter(prefix="/api/v1")

    def client_ip(request: Request) -> str:
        peer = request.client.host if request.client else None
        return resolve_client_ip(peer, request.headers.get("x-forwarded-for"), services.trusted_proxies)

    def origin_guard(request: Request) -> None:
        """Every unsafe request (login included: login-CSRF) must come from an allowlisted origin. CORS itself stays deny-by-default."""
        check_state_change_origin(request.method, origin=request.headers.get("origin"), referer=request.headers.get("referer"),
                                  allowed=settings.allowed_origins)

    async def load_session(request: Request) -> AuthenticatedSession:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            raise _unauthenticated()
        result = await services.sessions.authenticate(token)
        if result.session is None:
            raise _unauthenticated()  # one answer for malformed/unknown/revoked/expired/disabled (reason is not disclosed)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            presented = request.headers.get(settings.csrf_header_name, "")
            if not constant_time_equal(presented, result.session.csrf_token):
                raise ProblemError(ErrorCode.ACCESS_DENIED, "CSRF validation failed.", errors=[{"field": settings.csrf_header_name, "reason": "csrf_invalid"}])
        return result.session

    async def pending_ok_session(request: Request) -> AuthenticatedSession:
        """Only the second-factor endpoints, logout and csrf accept a session that has not presented its second factor yet."""
        return await load_session(request)

    async def current_session(request: Request) -> AuthenticatedSession:
        session = await load_session(request)
        if session.second_factor_pending:
            raise ProblemError(ErrorCode.ACCESS_DENIED, "Second factor required.", errors=[{"field": "session", "reason": "mfa_required"}])
        return session

    Guard = Annotated[None, Depends(origin_guard)]
    Session = Annotated[AuthenticatedSession, Depends(current_session)]
    PendingOkSession = Annotated[AuthenticatedSession, Depends(pending_ok_session)]

    def set_cookie(response: Response, issued: IssuedSession) -> None:
        response.set_cookie(**build_session_cookie(settings, issued.token))
        _no_store(response)

    @router.post("/auth/login")
    async def login(body: LoginBody, request: Request, response: Response, _: Guard) -> dict[str, Any]:
        org = body.organization_id or settings.default_organization_id
        if org is None:
            raise ProblemError(ErrorCode.VALIDATION_ERROR, "organizationId is required.", errors=[{"field": "organizationId", "reason": "required"}])
        previous = None
        if (cookie := request.cookies.get(settings.session_cookie_name)):
            previous = (await services.sessions.authenticate(cookie)).session  # a stale cookie is simply not replaced
        result = await services.auth.login(organization_id=org, email=body.email, password=body.password, client_ip=client_ip(request),
                                           request_id=current_request_id(), replace=previous)
        s = result.session
        set_cookie(response, s)
        return {"userId": str(s.user_id), "organizationId": str(s.organization_id), "mfaRequired": result.mfa_required, "csrfToken": s.csrf_token,
                "idleExpiresAt": _iso(s.idle_expires_at), "absoluteExpiresAt": _iso(s.absolute_expires_at)}

    @router.post("/auth/logout", status_code=204)
    async def logout(session: PendingOkSession, response: Response, _: Guard) -> Response:
        await services.auth.logout(session, request_id=current_request_id())
        out = Response(status_code=204, headers={"Cache-Control": "no-store"})
        out.delete_cookie(**clear_session_cookie_args(settings))
        return out

    @router.get("/auth/csrf")
    async def csrf(session: PendingOkSession, response: Response) -> dict[str, str]:
        _no_store(response)
        csrf = session.csrf_token
        return {"csrfToken": csrf}

    @router.post("/auth/password", status_code=204)
    async def change_password(body: ChangePasswordBody, session: Session, request: Request, _: Guard) -> Response:
        await services.auth.change_password(session, current_password=body.current_password, new_password=body.new_password, client_ip=client_ip(request),
                                            request_id=current_request_id())
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    @router.post("/auth/mfa/enrollment", status_code=201)
    async def mfa_begin(body: ReauthBody, session: Session, request: Request, response: Response, _: Guard) -> dict[str, str]:
        await services.auth.reauthenticate(session, password=body.current_password, purpose="mfa_enrollment", client_ip=client_ip(request),
                                           request_id=current_request_id())
        enrollment = await services.mfa.begin_enrollment(session, request_id=current_request_id())
        _no_store(response)
        return {"secret": enrollment.secret, "otpauthUri": enrollment.otpauth_uri}

    @router.post("/auth/mfa/enrollment/confirm")
    async def mfa_confirm(body: MfaCodeBody, session: Session, request: Request, response: Response, _: Guard) -> dict[str, Any]:
        confirmed = await services.mfa.confirm_enrollment(session, body.code, client_ip=client_ip(request), request_id=current_request_id())
        set_cookie(response, confirmed.session)
        return {"csrfToken": confirmed.session.csrf_token, "recoveryCodes": confirmed.recovery_codes}

    @router.post("/auth/mfa/verify")
    async def mfa_verify(body: MfaCodeBody, session: PendingOkSession, request: Request, response: Response, _: Guard) -> dict[str, str]:
        issued = await services.mfa.verify(session, body.code, client_ip=client_ip(request), request_id=current_request_id())
        set_cookie(response, issued)
        csrf = issued.csrf_token
        return {"csrfToken": csrf}

    @router.get("/me")
    async def me(session: Session, response: Response) -> dict[str, Any]:
        async with UnitOfWork(services.factory) as uow:
            await uow.with_tenant(session.organization_id)
            await services.enforcer.authorize(PolicyRequest(
                actor_id=str(session.user_id), action="iam.self.read", resource_type="USER", resource_id=str(session.user_id),
                organization_id=str(session.organization_id), attributes={"mfa_verified": session.mfa_verified_at is not None}), session=uow.session)
            view = await read_current_user(uow.session, session.organization_id, session.user_id)
        if view is None:
            raise _unauthenticated()
        _no_store(response)
        return {"id": str(view.id), "displayName": view.display_name, "organizations": [{"organizationId": str(i), "name": n} for i, n in view.organizations]}

    app.include_router(router)
    app.state.identity = services
