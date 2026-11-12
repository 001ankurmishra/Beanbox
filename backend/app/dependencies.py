from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from uuid import uuid4

from fastapi import Depends, Request

from app.cache.keys import SESSION_ACTIVE_TTL_SECONDS
from app.config import Settings
from app.models.domain import UserRole
from app.services import Services
from app.services.audit_service import RequestContext
from app.utils.errors import (
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
)
from app.utils.security import extract_client_ip, extract_user_agent

logger = logging.getLogger("beanbox.auth")

ACCESS_COOKIE_NAME = "beanbox_access"
REFRESH_COOKIE_NAME = "beanbox_refresh"
CSRF_COOKIE_NAME = "beanbox_csrf"
OAUTH_TX_COOKIE_NAME = "beanbox_oauth_tx"
GUEST_COOKIE_NAME = "beanbox_guest_id"
LEGACY_AUTH_COOKIE_NAME = "beanbox_token"


@dataclass
class AuthPrincipal:
    id: str
    role: UserRole
    sid: str
    jti: str
    email: str = ""
    email_verified: bool = False
    totp_enabled: bool = False
    is_effective_admin: bool = False


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_request_context(
    request: Request,
    settings: Settings = Depends(get_app_settings),
) -> RequestContext:
    req_id = getattr(request.state, "request_id", None) or str(uuid4())
    return RequestContext(
        ip=extract_client_ip(request, settings),
        user_agent=extract_user_agent(request),
        request_id=req_id,
    )


def _extract_token(request: Request) -> Optional[str]:
    # Cookie vs Bearer auth must never mix: if Authorization Bearer is used, ignore cookies.
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        return token or None
    cookie_token = request.cookies.get(ACCESS_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    return None


def _is_iso_expired(ts: str) -> bool:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt <= datetime.now(timezone.utc)


def _touch_session_if_stale(request: Request, session_id: str, last_used_at: str) -> None:
    try:
        last_dt = datetime.fromisoformat(last_used_at.replace("Z", "+00:00"))
        if (datetime.now(timezone.utc) - last_dt).total_seconds() >= 60:
            settings: Settings = request.app.state.settings
            request.app.state.repos.sessions.touch_last_used(
                session_id,
                extract_client_ip(request, settings),
                extract_user_agent(request),
            )
    except Exception:
        pass


def get_optional_user(
    request: Request,
    services: Services = Depends(get_services),
) -> Optional[AuthPrincipal]:
    token = _extract_token(request)
    if not token:
        return None
    try:
        return require_user(request=request, services=services)
    except UnauthorizedError:
        return None


def require_user(
    request: Request,
    services: Services = Depends(get_services),
) -> AuthPrincipal:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Authentication required")

    claims = services.auth_service.verify_access_token(token)
    session_cache = request.app.state.cache.session_cache
    cached_active = session_cache.is_active(claims.session_id)

    if cached_active is not True:
        session = request.app.state.repos.sessions.find_by_id(claims.session_id)
        if (
            not session
            or session.user_id != claims.user_id
            or session.revoked_at is not None
            or _is_iso_expired(session.expires_at)
        ):
            raise UnauthorizedError(
                "Session has been revoked or expired", code="SESSION_REVOKED"
            )
        session_cache.mark_active(session.id, SESSION_ACTIVE_TTL_SECONDS)
        _touch_session_if_stale(request, session.id, session.last_used_at)

    user = request.app.state.repos.users.find_by_id(claims.user_id)
    if not user:
        raise UnauthorizedError("User session no longer valid")

    return AuthPrincipal(
        id=user.id,
        role=user.role,
        sid=claims.session_id,
        jti=claims.jti,
        email=user.email,
        email_verified=user.email_verified,
        totp_enabled=user.totp_enabled,
        is_effective_admin=(user.role == "admin" and user.totp_enabled),
    )


def require_verified(
    principal: AuthPrincipal = Depends(require_user),
) -> AuthPrincipal:
    if not principal.email_verified:
        raise ForbiddenError(
            "Please verify your email address before placing an order.",
            code="EMAIL_NOT_VERIFIED",
        )
    return principal


def require_role(*roles: UserRole) -> Callable[..., AuthPrincipal]:
    """
    RBAC dependency that always re-checks the user's role and 2FA status from the database,
    never trusting JWT claims alone.
    """

    def _role_guard(
        request: Request,
        principal: AuthPrincipal = Depends(require_user),
    ) -> AuthPrincipal:
        db_user = request.app.state.repos.users.find_by_id(principal.id)
        if not db_user:
            raise UnauthorizedError("User session no longer valid")
        if db_user.role not in roles:
            raise ForbiddenError("You do not have permission to perform this action")
        if "admin" in roles and db_user.role == "admin" and not db_user.totp_enabled:
            raise ForbiddenError(
                "Two-factor authentication is required for administrator access. Please enable 2FA in Security Settings.",
                code="ADMIN_2FA_REQUIRED",
            )
        return AuthPrincipal(
            id=db_user.id,
            role=db_user.role,
            sid=principal.sid,
            jti=principal.jti,
            email=db_user.email,
            email_verified=db_user.email_verified,
            totp_enabled=db_user.totp_enabled,
            is_effective_admin=(db_user.role == "admin" and db_user.totp_enabled),
        )

    return _role_guard


# Convenience aliases used across routers
require_auth = require_user
require_admin = require_role("admin")


def get_guest_session_id(request: Request) -> Optional[str]:
    guest_id = request.cookies.get(GUEST_COOKIE_NAME) or request.headers.get(
        "x-guest-session-id"
    )
    if guest_id and guest_id.strip():
        return guest_id.strip()
    return None


_BUCKET_SETTING_ATTR = {
    "login": "rate_limit_login_max",
    "signup": "rate_limit_signup_max",
    "reset": "rate_limit_reset_max",
    "verify_resend": "rate_limit_verify_resend_max",
    "refresh": "rate_limit_refresh_max",
    "2fa": "rate_limit_2fa_max",
}


def _rate_limit_bucket(bucket: str, message: str) -> Callable[[Request], None]:
    def _dep(request: Request) -> None:
        settings: Settings = request.app.state.settings
        limiter = request.app.state.cache.rate_limiter
        limit = int(getattr(settings, _BUCKET_SETTING_ATTR[bucket]))
        window = settings.rate_limit_window_seconds
        client_ip = extract_client_ip(request, settings)
        allowed, remaining, reset_at = limiter.check(
            f"{bucket}:{client_ip}", limit, window
        )
        rl_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_at),
        }
        request.state.rate_limit_headers = rl_headers
        if not allowed:
            req_id = getattr(request.state, "request_id", "-")
            retry_after = str(max(1, reset_at - int(time.time())))
            logger.warning(
                "ratelimit=BLOCK bucket=%s ip=%s path=%s req=%s",
                bucket,
                client_ip,
                request.url.path,
                req_id,
            )
            raise TooManyRequestsError(
                message,
                code="AUTH_RATE_LIMIT_EXCEEDED",
                headers={**rl_headers, "Retry-After": retry_after},
            )

    return _dep


rate_limit_login = _rate_limit_bucket(
    "login", "Too many login attempts. Please try again shortly."
)
rate_limit_signup = _rate_limit_bucket(
    "signup", "Too many signup attempts from this IP. Please try again later."
)
rate_limit_reset = _rate_limit_bucket(
    "reset", "Too many password reset requests. Please try again later."
)
rate_limit_verify_resend = _rate_limit_bucket(
    "verify_resend", "Too many verification email requests. Please try again later."
)
rate_limit_refresh = _rate_limit_bucket(
    "refresh", "Too many token refresh requests. Please sign in again."
)
rate_limit_2fa = _rate_limit_bucket(
    "2fa", "Too many two-factor verification attempts. Please try again later."
)
auth_rate_limit = rate_limit_login
