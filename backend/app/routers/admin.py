from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from app.dependencies import get_services, require_admin
from app.models.domain import OrderStatus
from app.repositories.interfaces import (
    CreateCouponInput,
    CreateProductInput,
    UpdateCouponInput,
    UpdateProductInput,
    VariantInput,
)
from app.schemas.admin import (
    AdminCreateCouponRequest,
    AdminCreateProductRequest,
    AdminInventoryUpdateRequest,
    AdminUpdateCouponRequest,
    AdminUpdateOrderStatusRequest,
    AdminUpdateProductRequest,
)
from app.services import Services
from app.utils.response import make_success_response

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/stats")
def dashboard_stats(services: Services = Depends(get_services)):
    return make_success_response({"stats": services.admin_service.get_dashboard_stats()})


@router.get("/products")
def admin_list_products(
    search: Optional[str] = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    services: Services = Depends(get_services),
):
    return make_success_response(
        services.admin_service.list_products(page=page, limit=limit, search=search)
    )


@router.post("/products")
def admin_create_product(
    body: AdminCreateProductRequest,
    services: Services = Depends(get_services),
):
    product = services.admin_service.create_product(
        CreateProductInput(
            name=body.name,
            slug=body.slug,
            short_description=body.short_description,
            description=body.description,
            category=body.category,
            roast_level=body.roast_level,
            origin=body.origin,
            tasting_notes=body.tasting_notes,
            images=body.images,
            variants=[VariantInput(**v.model_dump()) for v in body.variants],
            is_featured=body.is_featured,
            is_active=body.is_active,
        )
    )
    return make_success_response({"product": product}, status_code=201)


@router.patch("/products/{product_id}")
def admin_update_product(
    body: AdminUpdateProductRequest,
    product_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    patch = body.model_dump(exclude_unset=True)
    if "variants" in patch and body.variants is not None:
        patch["variants"] = [VariantInput(**v.model_dump()) for v in body.variants]
    product = services.admin_service.update_product(
        product_id, UpdateProductInput(**patch)
    )
    return make_success_response({"product": product})


@router.delete("/products/{product_id}")
def admin_delete_product(
    product_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    services.admin_service.delete_product(product_id)
    return make_success_response({"message": "Product deleted"})


@router.patch("/inventory/{product_id}/{variant_id}")
def admin_update_inventory(
    body: AdminInventoryUpdateRequest,
    product_id: str = Path(min_length=1, max_length=120),
    variant_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    variant = services.admin_service.update_inventory(
        product_id=product_id,
        variant_id=variant_id,
        stock=body.stock,
        price_paise=body.price_paise,
    )
    return make_success_response({"variant": variant})


@router.get("/orders")
def admin_list_orders(
    status: Optional[OrderStatus] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    services: Services = Depends(get_services),
):
    return make_success_response(
        services.admin_service.list_orders(status=status, page=page, limit=limit)
    )


@router.patch("/orders/{order_id}/status")
def admin_update_order_status(
    body: AdminUpdateOrderStatusRequest,
    order_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    order = services.admin_service.update_order_status(
        order_id=order_id, next_status=body.status, reason=body.reason
    )
    return make_success_response({"order": order})


@router.get("/coupons")
def admin_list_coupons(services: Services = Depends(get_services)):
    return make_success_response({"items": services.admin_service.list_coupons()})


@router.post("/coupons")
def admin_create_coupon(
    body: AdminCreateCouponRequest,
    services: Services = Depends(get_services),
):
    coupon = services.admin_service.create_coupon(
        CreateCouponInput(
            code=body.code,
            description=body.description,
            type=body.type,
            value=body.value,
            min_order_paise=body.min_order_paise,
            max_discount_paise=body.max_discount_paise,
            expires_at=body.expires_at.isoformat().replace("+00:00", "Z"),
            usage_limit=body.usage_limit,
            is_active=body.is_active,
        )
    )
    return make_success_response({"coupon": coupon}, status_code=201)


@router.patch("/coupons/{coupon_id}")
def admin_update_coupon(
    body: AdminUpdateCouponRequest,
    coupon_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    patch = body.model_dump(exclude_unset=True)
    if "expires_at" in patch and body.expires_at is not None:
        patch["expires_at"] = body.expires_at.isoformat().replace("+00:00", "Z")
    coupon = services.admin_service.update_coupon(
        coupon_id, UpdateCouponInput(**patch)
    )
    return make_success_response({"coupon": coupon})


@router.delete("/coupons/{coupon_id}")
def admin_delete_coupon(
    coupon_id: str = Path(min_length=1, max_length=120),
    services: Services = Depends(get_services),
):
    services.admin_service.delete_coupon(coupon_id)
    return make_success_response({"message": "Coupon deleted"})


@router.get("/users")
def admin_list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=50),
    services: Services = Depends(get_services),
):
    return make_success_response(
        services.admin_service.list_users(page=page, limit=limit)
    )
