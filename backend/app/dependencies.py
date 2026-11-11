from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request

from app.config import Settings
from app.models.domain import UserRole
from app.services import Services
from app.utils.errors import (
    ForbiddenError,
    TooManyRequestsError,
    UnauthorizedError,
)

AUTH_COOKIE_NAME = "beanbox_token"
GUEST_COOKIE_NAME = "beanbox_guest_id"


@dataclass
class AuthPrincipal:
    id: str
    role: UserRole


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def _extract_token(request: Request) -> Optional[str]:
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return None


def get_optional_user(
    request: Request,
    services: Services = Depends(get_services),
) -> Optional[AuthPrincipal]:
    token = _extract_token(request)
    if not token:
        return None
    try:
        user_id, role = services.auth_service.verify_token(token)
        return AuthPrincipal(id=user_id, role=role)
    except UnauthorizedError:
        return None


def require_auth(
    request: Request,
    services: Services = Depends(get_services),
) -> AuthPrincipal:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Authentication required")
    user_id, role = services.auth_service.verify_token(token)
    return AuthPrincipal(id=user_id, role=role)


def require_admin(
    principal: AuthPrincipal = Depends(require_auth),
) -> AuthPrincipal:
    if principal.role != "admin":
        raise ForbiddenError("You do not have permission to perform this action")
    return principal


def get_guest_session_id(request: Request) -> Optional[str]:
    guest_id = request.cookies.get(GUEST_COOKIE_NAME) or request.headers.get(
        "x-guest-session-id"
    )
    if guest_id and guest_id.strip():
        return guest_id.strip()
    return None


def auth_rate_limit(request: Request) -> None:
    limiter = request.app.state.auth_limiter
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.allow(f"auth:{client_ip}"):
        raise TooManyRequestsError(
            "Too many authentication attempts. Please try again in 15 minutes.",
            code="AUTH_RATE_LIMIT_EXCEEDED",
        )
