from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Path, Response

from app.config import Settings
from app.dependencies import (
    GUEST_COOKIE_NAME,
    AuthPrincipal,
    get_app_settings,
    get_guest_session_id,
    get_optional_user,
    get_services,
)
from app.schemas.cart import AddToCartRequest, UpdateCartItemRequest
from app.services import Services
from app.services.cart_service import CartOwner
from app.utils.response import make_success_response

router = APIRouter(prefix="/api/cart", tags=["Cart"])


def _resolve_owner(
    user: Optional[AuthPrincipal],
    guest_session_id: Optional[str],
    create_if_missing: bool,
) -> tuple[Optional[CartOwner], Optional[str]]:
    if user:
        return CartOwner(user_id=user.id), None
    if guest_session_id:
        return CartOwner(session_id=guest_session_id), None
    if not create_if_missing:
        return None, None
    new_session = str(uuid4())
    return CartOwner(session_id=new_session), new_session


def _attach_guest_cookie(
    response: Response, new_session: Optional[str], settings: Settings
) -> None:
    if new_session:
        response.set_cookie(
            key=GUEST_COOKIE_NAME,
            value=new_session,
            httponly=True,
            samesite="lax",
            secure=settings.app_env == "production",
            path="/",
            max_age=30 * 24 * 60 * 60,
        )


@router.get("")
def get_cart(
    user: Optional[AuthPrincipal] = Depends(get_optional_user),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
):
    owner, _ = _resolve_owner(user, guest_session_id, False)
    if not owner:
        return make_success_response({"cart": services.cart_service.hydrate(None)})
    return make_success_response({"cart": services.cart_service.get_hydrated_cart(owner)})


@router.post("/items")
def add_item(
    body: AddToCartRequest,
    user: Optional[AuthPrincipal] = Depends(get_optional_user),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    owner, new_session = _resolve_owner(user, guest_session_id, True)
    assert owner is not None
    cart = services.cart_service.add_item(
        owner, body.product_id, body.variant_id, body.quantity
    )
    resp = make_success_response({"cart": cart}, status_code=201)
    _attach_guest_cookie(resp, new_session, settings)
    return resp


@router.patch("/items/{variant_id}")
def update_item(
    body: UpdateCartItemRequest,
    variant_id: str = Path(min_length=1, max_length=120),
    user: Optional[AuthPrincipal] = Depends(get_optional_user),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    owner, new_session = _resolve_owner(user, guest_session_id, True)
    assert owner is not None
    cart = services.cart_service.update_item_quantity(owner, variant_id, body.quantity)
    resp = make_success_response({"cart": cart})
    _attach_guest_cookie(resp, new_session, settings)
    return resp


@router.delete("/items/{variant_id}")
def remove_item(
    variant_id: str = Path(min_length=1, max_length=120),
    user: Optional[AuthPrincipal] = Depends(get_optional_user),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
    settings: Settings = Depends(get_app_settings),
):
    owner, new_session = _resolve_owner(user, guest_session_id, True)
    assert owner is not None
    cart = services.cart_service.remove_item(owner, variant_id)
    resp = make_success_response({"cart": cart})
    _attach_guest_cookie(resp, new_session, settings)
    return resp


@router.delete("")
def clear_cart(
    user: Optional[AuthPrincipal] = Depends(get_optional_user),
    guest_session_id: Optional[str] = Depends(get_guest_session_id),
    services: Services = Depends(get_services),
):
    owner, _ = _resolve_owner(user, guest_session_id, False)
    if not owner:
        return make_success_response({"cart": services.cart_service.hydrate(None)})
    return make_success_response({"cart": services.cart_service.clear(owner)})
