from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.config import Settings
from app.dependencies import (
    AUTH_COOKIE_NAME,
    GUEST_COOKIE_NAME,
    AuthPrincipal,
    auth_rate_limit,
    get_app_settings,
    get_guest_session_id,
    get_services,
    require_auth,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    UpdateProfileRequest,
)
from app.services import Services
from app.utils.response import make_success_response

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        path="/",
        max_age=settings.jwt_expires_minutes * 60,
    )


@router.post("/signup", dependencies=[Depends(auth_rate_limit)])
def signup(
    body: SignupRequest,
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    user, token = services.auth_service.signup(
        name=body.name,
        email=str(body.email),
        password=body.password,
        phone=body.phone,
    )
    resp = make_success_response({"user": user}, status_code=201)
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(guest_session_id, user.id)
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _set_auth_cookie(resp, token, settings)
    return resp


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
def login(
    body: LoginRequest,
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    user, token = services.auth_service.login(
        email=str(body.email),
        password=body.password,
    )
    resp = make_success_response({"user": user})
    if guest_session_id:
        services.cart_service.merge_guest_cart_into_user(guest_session_id, user.id)
        resp.delete_cookie(GUEST_COOKIE_NAME, path="/")
    _set_auth_cookie(resp, token, settings)
    return resp


@router.post("/logout")
def logout():
    resp = make_success_response({"message": "Logged out successfully"})
    resp.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return resp


@router.get("/me")
def me(
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    user = services.auth_service.get_me(principal.id)
    return make_success_response({"user": user})


@router.patch("/me")
def update_me(
    body: UpdateProfileRequest,
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    user = services.auth_service.update_profile(
        principal.id, name=body.name, phone=body.phone
    )
    return make_success_response({"user": user})


@router.post("/forgot-password", dependencies=[Depends(auth_rate_limit)])
def forgot_password(
    body: ForgotPasswordRequest,
    services: Services = Depends(get_services),
):
    result = services.auth_service.forgot_password(str(body.email))
    return make_success_response(result)


@router.post("/reset-password", dependencies=[Depends(auth_rate_limit)])
def reset_password(
    body: ResetPasswordRequest,
    services: Services = Depends(get_services),
):
    result = services.auth_service.reset_password(body.token, body.new_password)
    return make_success_response(result)
