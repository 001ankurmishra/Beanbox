import math
from datetime import datetime, timezone
from typing import Optional

from app.models.domain import (
    CamelModel,
    Coupon,
    Order,
    OrderStatus,
    Product,
    ProductVariant,
    PublicUser,
)
from app.repositories.interfaces import (
    CouponRepository,
    CreateCouponInput,
    CreateProductInput,
    LowStockVariantEntry,
    OrderRepository,
    OrderUpdateFields,
    ProductListQuery,
    ProductRepository,
    TopProductStat,
    UpdateCouponInput,
    UpdateProductInput,
    UserRepository,
)
from app.schemas.common import PaginationMeta
from app.services.auth_service import to_public_user
from app.services.email_service import EmailService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentProvider
from app.utils.errors import ConflictError, NotFoundError

ALLOWED_STATUS_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    "pending": ["paid", "cancelled"],
    "paid": ["processing", "cancelled", "refunded"],
    "processing": ["shipped", "cancelled", "refunded"],
    "shipped": ["delivered"],
    "delivered": ["refunded"],
    "cancelled": [],
    "refunded": [],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AdminDashboardStats(CamelModel):
    total_revenue_paise: int
    total_orders: int
    paid_orders_count: int
    pending_orders_count: int
    status_breakdown: dict[str, int]
    top_products: list[TopProductStat]
    recent_orders: list[Order]
    total_customers: int
    low_stock_variants: list[LowStockVariantEntry]


class AdminUserEntry(PublicUser):
    order_count: int


class AdminService:
    def __init__(
        self,
        product_repo: ProductRepository,
        order_repo: OrderRepository,
        coupon_repo: CouponRepository,
        user_repo: UserRepository,
        order_service: OrderService,
        payment_provider: PaymentProvider,
        email_service: EmailService,
    ) -> None:
        self._product_repo = product_repo
        self._order_repo = order_repo
        self._coupon_repo = coupon_repo
        self._user_repo = user_repo
        self._order_service = order_service
        self._payment_provider = payment_provider
        self._email_service = email_service

    def get_dashboard_stats(self) -> AdminDashboardStats:
        order_stats = self._order_repo.get_dashboard_stats()
        low_stock = self._product_repo.list_low_stock(5)
        _, total_users = self._user_repo.list(page=1, limit=1)

        return AdminDashboardStats(
            total_revenue_paise=order_stats.total_revenue_paise,
            total_orders=order_stats.total_orders,
            paid_orders_count=order_stats.paid_orders_count,
            pending_orders_count=order_stats.pending_orders_count,
            status_breakdown=order_stats.status_breakdown,
            top_products=order_stats.top_products,
            recent_orders=order_stats.recent_orders,
            total_customers=total_users,
            low_stock_variants=low_stock,
        )

    def list_products(
        self, page: int, limit: int, search: Optional[str] = None
    ) -> dict:
        result = self._product_repo.list(
            ProductListQuery(
                page=page,
                limit=limit,
                search=search,
                include_inactive=True,
                sort="newest",
            )
        )
        total_pages = max(1, math.ceil(result.total / limit))
        return {
            "items": result.items,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=result.total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    def create_product(self, data: CreateProductInput) -> Product:
        if self._product_repo.find_by_slug(data.slug):
            raise ConflictError("A product with this slug already exists")
        return self._product_repo.create(data)

    def update_product(self, product_id: str, data: UpdateProductInput) -> Product:
        if data.slug:
            existing = self._product_repo.find_by_slug(data.slug)
            if existing and existing.id != product_id:
                raise ConflictError("A product with this slug already exists")
        updated = self._product_repo.update(product_id, data)
        if not updated:
            raise NotFoundError("Product not found")
        return updated

    def delete_product(self, product_id: str) -> None:
        if not self._product_repo.delete(product_id):
            raise NotFoundError("Product not found")

    def update_inventory(
        self,
        product_id: str,
        variant_id: str,
        stock: Optional[int] = None,
        price_paise: Optional[int] = None,
    ) -> ProductVariant:
        variant = self._product_repo.update_variant_inventory(
            product_id, variant_id, stock=stock, price_paise=price_paise
        )
        if not variant:
            raise NotFoundError("Product or variant not found")
        return variant

    def list_orders(
        self, status: Optional[OrderStatus], page: int, limit: int
    ) -> dict:
        items, total = self._order_repo.list_all(status, page, limit)
        total_pages = max(1, math.ceil(total / limit))
        return {
            "items": items,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }

    def update_order_status(
        self, order_id: str, next_status: OrderStatus, reason: Optional[str] = None
    ) -> Order:
        order = self._order_repo.find_by_id(order_id)
        if not order:
            raise NotFoundError("Order not found")

        allowed = ALLOWED_STATUS_TRANSITIONS.get(order.status, [])
        if next_status not in allowed:
            raise ConflictError(
                f"Invalid order status transition from '{order.status}' to '{next_status}'",
                details={"currentStatus": order.status, "allowedTransitions": allowed},
                code="INVALID_STATUS_TRANSITION",
            )

        now = _now_iso()
        updates = OrderUpdateFields(status=next_status)

        if next_status == "paid":
            updates.payment_status = "paid"
            updates.paid_at = now
        elif next_status == "shipped":
            updates.shipped_at = now
        elif next_status == "delivered":
            updates.delivered_at = now
        elif next_status in ("cancelled", "refunded"):
            if order.status in ("pending", "paid", "processing"):
                self._order_service.release_order_resources(order)
                updates.stock_released = True
            if order.payment_status == "paid":
                self._payment_provider.refund_payment(
                    order.payment_intent_id or "", order.pricing.total_paise
                )
                updates.payment_status = "refunded"
            if next_status == "cancelled":
                updates.cancelled_at = now
                updates.cancel_reason = (reason or "").strip() or "Cancelled by administrator"

        updated = self._order_repo.update_order(order.id, updates)
        if not updated:
            raise NotFoundError("Order not found")

        if next_status == "shipped":
            user = self._user_repo.find_by_id(updated.user_id)
            if user:
                self._email_service.send_order_shipped(
                    to=user.email, customer_name=user.name, order=updated
                )

        return updated

    def list_coupons(self) -> list[Coupon]:
        return self._coupon_repo.list()

    def create_coupon(self, data: CreateCouponInput) -> Coupon:
        if self._coupon_repo.find_by_code(data.code):
            raise ConflictError("A coupon with this code already exists")
        return self._coupon_repo.create(data)

    def update_coupon(self, coupon_id: str, data: UpdateCouponInput) -> Coupon:
        if data.code:
            existing = self._coupon_repo.find_by_code(data.code)
            if existing and existing.id != coupon_id:
                raise ConflictError("A coupon with this code already exists")
        updated = self._coupon_repo.update(coupon_id, data)
        if not updated:
            raise NotFoundError("Coupon not found")
        return updated

    def delete_coupon(self, coupon_id: str) -> None:
        if not self._coupon_repo.delete(coupon_id):
            raise NotFoundError("Coupon not found")

    def list_users(self, page: int, limit: int) -> dict:
        users, total = self._user_repo.list(page, limit)
        counts = self._order_repo.count_orders_by_user([u.id for u in users])
        total_pages = max(1, math.ceil(total / limit))

        items = [
            AdminUserEntry(
                **to_public_user(u).model_dump(),
                order_count=counts.get(u.id, 0),
            )
            for u in users
        ]
        return {
            "items": items,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }
