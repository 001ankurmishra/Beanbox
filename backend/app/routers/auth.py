from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings
from app.dependencies import (
    ACCESS_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    GUEST_COOKIE_NAME,
    LEGACY_AUTH_COOKIE_NAME,
    OAUTH_TX_COOKIE_NAME,
    REFRESH_COOKIE_NAME,
    AuthPrincipal,
    get_app_settings,
    get_guest_session_id,
    get_request_context,
    get_services,
    rate_limit_2fa,
    rate_limit_login,
    rate_limit_refresh,
    rate_limit_reset,
    rate_limit_signup,
    rate_limit_verify_resend,
    require_user,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    Disable2faRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    TotpCodeRequest,
    UpdateProfileRequest,
    Verify2faLoginRequest,
    VerifyEmailRequest,
)
from app.services import Services
from app.services.audit_service import RequestContext
from app.services.auth_service import IssuedSessionTokens, LoginChallengeResult
from app.utils.errors import UnauthorizedError
from app.utils.response import make_error_payload, make_success_response
from app.utils.security import generate_opaque_token, is_secure_cookie

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _attach_csrf_cookie(
    response: Response, settings: Settings, request: Request, token: Optional[str] = None
) -> str:
    csrf_val = token or generate_opaque_token(24)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_val,
        httponly=False,
        samesite="lax",
        secure=is_secure_cookie(settings, request),
        path="/",
        max_age=settings.refresh_token_expires_days * 86400,
    )
    response.headers["X-CSRF-Token"] = csrf_val
    return csrf_val


def _attach_session_cookies(
    response: Response,
    issued: IssuedSessionTokens,
    settings: Settings,
    request: Request,
) -> str:
    secure = is_secure_cookie(settings, request)
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=issued.access_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=settings.access_token_expires_minutes * 60,
    )
    if issued.refresh_token:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=issued.refresh_token,
            httponly=True,
            samesite="lax",
            secure=secure,
            path="/api/auth",
            max_age=settings.refresh_token_expires_days * 86400,
        )
    response.delete_cookie(LEGACY_AUTH_COOKIE_NAME, path="/")
    existing_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    preserve_csrf = (
        existing_csrf
        if not issued.refresh_token and existing_csrf and len(existing_csrf) >= 16
        else None
    )
    return _attach_csrf_cookie(response, settings, request, token=preserve_csrf)


def _clear_auth_cookies(
    response: Response, settings: Settings, request: Request
) -> None:
    secure = is_secure_cookie(settings, request)
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/", samesite="lax", secure=secure)
    response.delete_cookie(
        REFRESH_COOKIE_NAME, path="/api/auth", samesite="lax", secure=secure
    )
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", samesite="lax", secure=secure)
    response.delete_cookie(LEGACY_AUTH_COOKIE_NAME, path="/")
    response.delete_cookie(OAUTH_TX_COOKIE_NAME, path="/api/auth/google")


@router.get("/csrf")
def get_csrf_token(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    existing = request.cookies.get(CSRF_COOKIE_NAME)
    token = existing if existing and len(existing) >= 16 else generate_opaque_token(24)
    resp = make_success_response({"csrfToken": token})
    _attach_csrf_cookie(resp, settings, request, token=token)
    return resp


@router.get("/providers")
def auth_providers(settings: Settings = Depends(get_app_settings)):
    return make_success_response({"googleOAuthEnabled": settings.google_oauth_enabled})


@router.post("/signup", dependencies=[Depends(rate_limit_signup)])
def signup(
    body: SignupRequest,
    request: Request,
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    issued = services.auth_service.signup(
        name=body.name,
        email=str(body.email),
        password=body.password,
        phone=body.phone,
        ctx=ctx,
    )
    resp = make_success_response(
        {
            "user": issued.user,
            "requiresEmailVerification": True,
        },
        status_code=201,
    )
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(guest_session_id, issued.user.id)
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _attach_session_cookies(resp, issued, settings, request)
    return resp


@router.post("/login", dependencies=[Depends(rate_limit_login)])
def login(
    body: LoginRequest,
    request: Request,
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    outcome = services.auth_service.login(
        email=str(body.email),
        password=body.password,
        ctx=ctx,
    )
    if isinstance(outcome, LoginChallengeResult):
        resp = make_success_response(
            {
                "requiresTwoFactor": True,
                "challengeToken": outcome.challenge_token,
                "methods": outcome.methods,
            }
        )
        _attach_csrf_cookie(resp, settings, request)
        return resp

    resp = make_success_response(
        {
            "user": outcome.user,
            "requiresTwoFactor": False,
        }
    )
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(
            guest_session_id, outcome.user.id
        )
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _attach_session_cookies(resp, outcome, settings, request)
    return resp


@router.post("/refresh", dependencies=[Depends(rate_limit_refresh)])
def refresh(
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    try:
        issued = services.auth_service.refresh_session(raw_refresh, ctx=ctx)
    except UnauthorizedError as exc:
        resp = JSONResponse(
            status_code=exc.status_code,
            content=make_error_payload(
                code=exc.code,
                message=exc.message,
                request_id=ctx.request_id,
            ),
        )
        _clear_auth_cookies(resp, settings, request)
        return resp

    resp = make_success_response({"user": issued.user})
    _attach_session_cookies(resp, issued, settings, request)
    return resp


@router.post("/logout")
def logout(
    request: Request,
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if token:
        try:
            claims = services.auth_service.verify_access_token(token)
            session_id = claims.session_id
            user_id = claims.user_id
        except UnauthorizedError:
            pass

    services.auth_service.logout(
        session_id=session_id,
        user_id=user_id,
        raw_refresh_token=request.cookies.get(REFRESH_COOKIE_NAME),
        ctx=ctx,
    )
    resp = make_success_response({"message": "Logged out successfully"})
    _clear_auth_cookies(resp, settings, request)
    return resp


@router.post("/logout-all")
def logout_all(
    request: Request,
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    count = services.auth_service.logout_all(principal.id, ctx=ctx)
    resp = make_success_response(
        {"message": "Logged out from all devices", "revokedSessions": count}
    )
    _clear_auth_cookies(resp, settings, request)
    return resp


@router.get("/me")
def me(
    request: Request,
    principal: AuthPrincipal = Depends(require_user),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    user = services.auth_service.get_me(principal.id)
    resp = make_success_response({"user": user})
    if not request.cookies.get(CSRF_COOKIE_NAME):
        _attach_csrf_cookie(resp, settings, request)
    return resp


@router.patch("/me")
def update_me(
    body: UpdateProfileRequest,
    principal: AuthPrincipal = Depends(require_user),
    services: Services = Depends(get_services),
):
    user = services.auth_service.update_profile(
        principal.id, name=body.name, phone=body.phone
    )
    return make_success_response({"user": user})


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    result = services.auth_service.change_password(
        user_id=principal.id,
        current_session_id=principal.sid,
        current_password=body.current_password,
        new_password=body.new_password,
        ctx=ctx,
    )
    return make_success_response(result)


@router.post("/verify-email", dependencies=[Depends(rate_limit_reset)])
def verify_email(
    body: VerifyEmailRequest,
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    user = services.auth_service.verify_email(body.token, ctx=ctx)
    return make_success_response(
        {"user": user, "message": "Email verified successfully!"}
    )


@router.post("/verify-email/resend", dependencies=[Depends(rate_limit_verify_resend)])
def resend_verification(
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    result = services.auth_service.resend_verification_email(principal.id, ctx=ctx)
    return make_success_response(result)


@router.post("/forgot-password", dependencies=[Depends(rate_limit_reset)])
def forgot_password(
    body: ForgotPasswordRequest,
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    result = services.auth_service.forgot_password(str(body.email), ctx=ctx)
    return make_success_response(result)


@router.post("/reset-password", dependencies=[Depends(rate_limit_reset)])
def reset_password(
    body: ResetPasswordRequest,
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    result = services.auth_service.reset_password(
        body.token, body.new_password, ctx=ctx
    )
    return make_success_response(result)


# ── Sessions Management ───────────────────────────────────────────────────────


@router.get("/sessions")
def list_sessions(
    principal: AuthPrincipal = Depends(require_user),
    services: Services = Depends(get_services),
):
    sessions = services.auth_service.list_sessions(principal.id, principal.sid)
    return make_success_response({"items": sessions})


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    services.auth_service.revoke_session(principal.id, session_id, ctx=ctx)
    return make_success_response({"message": "Session revoked"})


# ── Two-Factor Authentication (TOTP) ──────────────────────────────────────────


@router.get("/2fa/status")
def two_factor_status(
    principal: AuthPrincipal = Depends(require_user),
    services: Services = Depends(get_services),
):
    return make_success_response(services.auth_service.get_2fa_status(principal.id))


@router.post("/2fa/setup")
def two_factor_setup(
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    data = services.auth_service.setup_2fa(principal.id, ctx=ctx)
    return make_success_response(data)


@router.post("/2fa/enable")
def two_factor_enable(
    body: TotpCodeRequest,
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    data = services.auth_service.enable_2fa(principal.id, body.code, ctx=ctx)
    return make_success_response(data)


@router.post("/2fa/verify-login", dependencies=[Depends(rate_limit_2fa)])
def two_factor_verify_login(
    body: Verify2faLoginRequest,
    request: Request,
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    issued = services.auth_service.verify_2fa_login(
        challenge_token=body.challenge_token, code=body.code, ctx=ctx
    )
    resp = make_success_response({"user": issued.user, "requiresTwoFactor": False})
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(
            guest_session_id, issued.user.id
        )
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _attach_session_cookies(resp, issued, settings, request)
    return resp


@router.post("/2fa/recovery-codes/regenerate")
def two_factor_regenerate_recovery(
    body: TotpCodeRequest,
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    codes = services.auth_service.regenerate_recovery_codes(
        principal.id, body.code, ctx=ctx
    )
    return make_success_response({"recoveryCodes": codes})


@router.post("/2fa/disable")
def two_factor_disable(
    body: Disable2faRequest,
    principal: AuthPrincipal = Depends(require_user),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
):
    user = services.auth_service.disable_2fa(
        user_id=principal.id, code=body.code, password=body.password, ctx=ctx
    )
    return make_success_response({"user": user, "totpEnabled": False})


# ── Google OAuth 2.0 (Authorization Code + PKCE) ─────────────────────────────


@router.get("/google/start")
def google_oauth_start(
    request: Request,
    next: Optional[str] = Query(default="/"),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    auth_url, sealed_tx = services.auth_service.start_google_oauth(next_path=next)
    resp = RedirectResponse(url=auth_url, status_code=302)
    resp.set_cookie(
        key=OAUTH_TX_COOKIE_NAME,
        value=sealed_tx,
        httponly=True,
        samesite="lax",
        secure=is_secure_cookie(settings, request),
        path="/api/auth/google",
        max_age=600,
    )
    return resp


@router.get("/google/callback")
def google_oauth_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    ctx: RequestContext = Depends(get_request_context),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    if error:
        login_err = f"{settings.frontend_url.rstrip('/')}/login?error=oauth_denied"
        resp = RedirectResponse(url=login_err, status_code=302)
        resp.delete_cookie(OAUTH_TX_COOKIE_NAME, path="/api/auth/google")
        return resp

    if not code or not state:
        from app.utils.errors import BadRequestError

        raise BadRequestError(
            "Missing OAuth code or state parameter", code="OAUTH_MISSING_PARAMS"
        )

    sealed_tx = request.cookies.get(OAUTH_TX_COOKIE_NAME)
    outcome, next_path = services.auth_service.complete_google_oauth(
        code=code,
        state=state,
        sealed_tx=sealed_tx,
        ctx=ctx,
    )

    base_frontend = settings.frontend_url.rstrip("/")
    if isinstance(outcome, LoginChallengeResult):
        qs = urlencode({"twofa": "1", "next": next_path})
        redirect_target = f"{base_frontend}/login?{qs}#challenge={outcome.challenge_token}"
        resp = RedirectResponse(url=redirect_target, status_code=302)
        resp.delete_cookie(OAUTH_TX_COOKIE_NAME, path="/api/auth/google")
        _attach_csrf_cookie(resp, settings, request)
        return resp

    target_url = f"{base_frontend}{next_path}"
    resp = RedirectResponse(url=target_url, status_code=302)
    resp.delete_cookie(OAUTH_TX_COOKIE_NAME, path="/api/auth/google")
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(
            guest_session_id, outcome.user.id
        )
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _attach_session_cookies(resp, outcome, settings, request)
    return resp
