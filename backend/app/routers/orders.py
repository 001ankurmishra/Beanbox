from fastapi import APIRouter, Depends, Path, Query

from app.dependencies import AuthPrincipal, get_services, require_auth, require_verified
from app.schemas.order import (
    CancelOrderRequest,
    CheckoutPreviewRequest,
    CreateOrderRequest,
)
from app.services import Services
from app.utils.response import make_success_response

checkout_router = APIRouter(prefix="/api/checkout", tags=["Checkout & Orders"])
orders_router = APIRouter(prefix="/api/orders", tags=["Checkout & Orders"])


@checkout_router.post("/preview")
def preview_checkout(
    body: CheckoutPreviewRequest,
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    preview = services.order_service.preview_checkout(
        user_id=principal.id,
        coupon_code=body.coupon_code,
        address_id=body.address_id,
    )
    return make_success_response({"preview": preview})


@orders_router.post("")
def create_order(
    body: CreateOrderRequest,
    principal: AuthPrincipal = Depends(require_verified),
    services: Services = Depends(get_services),
):
    order = services.order_service.create_order(
        user_id=principal.id,
        address_id=body.address_id,
        coupon_code=body.coupon_code,
    )
    return make_success_response({"order": order}, status_code=201)


@orders_router.get("")
def list_orders(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=12, ge=1, le=50),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    result = services.order_service.list_user_orders(principal.id, page, limit)
    return make_success_response(result)


@orders_router.get("/{order_id}")
def get_order(
    order_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    order = services.order_service.get_order_for_user(
        order_id,
        principal.id,
        principal.is_effective_admin,
        is_admin_role=principal.role == "admin",
    )
    return make_success_response({"order": order})


@orders_router.post("/{order_id}/cancel")
def cancel_order(
    body: CancelOrderRequest,
    order_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    order = services.order_service.cancel_order(
        order_id, principal.id, body.reason
    )
    return make_success_response({"order": order})


@orders_router.get("/{order_id}/invoice")
def get_invoice(
    order_id: str = Path(min_length=1, max_length=120),
    principal: AuthPrincipal = Depends(require_auth),
    services: Services = Depends(get_services),
):
    invoice = services.order_service.get_invoice(
        order_id,
        principal.id,
        principal.is_effective_admin,
        is_admin_role=principal.role == "admin",
    )
    return make_success_response({"invoice": invoice})
