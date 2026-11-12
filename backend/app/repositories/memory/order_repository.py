from datetime import datetime, timezone
from threading import RLock
from typing import Literal, Optional
from uuid import uuid4

from app.models.domain import Order, OrderStatus
from app.repositories.interfaces import (
    CreateOrderInput,
    OrderDashboardStats,
    OrderRepository,
    OrderUpdateFields,
    TopProductStat,
)

REVENUE_STATUSES: frozenset[OrderStatus] = frozenset(
    {"paid", "processing", "shipped", "delivered"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryOrderRepository(OrderRepository):
    def __init__(self, initial_orders: Optional[list[Order]] = None) -> None:
        self._lock = RLock()
        self._orders: list[Order] = [
            o.model_copy(deep=True) for o in (initial_orders or [])
        ]

    def create(self, data: CreateOrderInput) -> Order:
        now = _now_iso()
        order = Order(
            id=str(uuid4()),
            order_number=data.order_number,
            user_id=data.user_id,
            items=[i.model_copy(deep=True) for i in data.items],
            shipping_address=data.shipping_address.model_copy(deep=True),
            coupon_code=data.coupon_code,
            coupon_id=data.coupon_id,
            pricing=data.pricing.model_copy(deep=True),
            status="pending",
            payment_status="unpaid",
            stock_released=False,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._orders.append(order.model_copy(deep=True))
        return order

    def find_by_id(self, order_id: str) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.id == order_id:
                    return o.model_copy(deep=True)
            return None

    def find_by_id_for_user(self, order_id: str, user_id: str) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.id == order_id and o.user_id == user_id:
                    return o.model_copy(deep=True)
            return None

    def find_by_order_number(self, order_number: str) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.order_number == order_number:
                    return o.model_copy(deep=True)
            return None

    def find_by_payment_session_id(self, session_id: str) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.payment_session_id == session_id:
                    return o.model_copy(deep=True)
            return None

    def list_by_user_id(
        self, user_id: str, page: int, limit: int
    ) -> tuple[list[Order], int]:
        with self._lock:
            filtered = [o for o in self._orders if o.user_id == user_id]
            filtered.sort(key=lambda o: o.created_at, reverse=True)
            total = len(filtered)
            start = (page - 1) * limit
            items = [o.model_copy(deep=True) for o in filtered[start : start + limit]]
            return items, total

    def list_all(
        self, status: Optional[OrderStatus], page: int, limit: int
    ) -> tuple[list[Order], int]:
        with self._lock:
            filtered = (
                [o for o in self._orders if o.status == status]
                if status
                else list(self._orders)
            )
            filtered.sort(key=lambda o: o.created_at, reverse=True)
            total = len(filtered)
            start = (page - 1) * limit
            items = [o.model_copy(deep=True) for o in filtered[start : start + limit]]
            return items, total

    def attach_payment_session(
        self,
        order_id: str,
        provider: Literal["stripe", "mock"],
        session_id: str,
        payment_intent_id: Optional[str] = None,
    ) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.id == order_id:
                    o.payment_provider = provider
                    o.payment_session_id = session_id
                    if payment_intent_id:
                        o.payment_intent_id = payment_intent_id
                    o.updated_at = _now_iso()
                    return o.model_copy(deep=True)
            return None

    def update_order(
        self, order_id: str, updates: OrderUpdateFields
    ) -> Optional[Order]:
        with self._lock:
            for o in self._orders:
                if o.id == order_id:
                    if updates.status is not None:
                        o.status = updates.status
                    if updates.payment_status is not None:
                        o.payment_status = updates.payment_status
                    if updates.payment_intent_id is not None:
                        o.payment_intent_id = updates.payment_intent_id
                    if updates.stock_released is not None:
                        o.stock_released = updates.stock_released
                    if updates.cancel_reason is not None:
                        o.cancel_reason = updates.cancel_reason
                    if updates.paid_at is not None:
                        o.paid_at = updates.paid_at
                    if updates.shipped_at is not None:
                        o.shipped_at = updates.shipped_at
                    if updates.delivered_at is not None:
                        o.delivered_at = updates.delivered_at
                    if updates.cancelled_at is not None:
                        o.cancelled_at = updates.cancelled_at
                    o.updated_at = _now_iso()
                    return o.model_copy(deep=True)
            return None

    def has_verified_purchase(self, user_id: str, product_id: str) -> bool:
        with self._lock:
            return any(
                o.user_id == user_id
                and o.status in REVENUE_STATUSES
                and any(item.product_id == product_id for item in o.items)
                for o in self._orders
            )

    def count_orders_by_user(self, user_ids: list[str]) -> dict[str, int]:
        counts = {uid: 0 for uid in user_ids}
        with self._lock:
            for o in self._orders:
                if o.user_id in counts:
                    counts[o.user_id] += 1
        return counts

    def get_dashboard_stats(self) -> OrderDashboardStats:
        status_breakdown: dict[str, int] = {
            "pending": 0,
            "paid": 0,
            "processing": 0,
            "shipped": 0,
            "delivered": 0,
            "cancelled": 0,
            "refunded": 0,
        }
        total_revenue_paise = 0
        paid_orders_count = 0
        product_map: dict[str, TopProductStat] = {}

        with self._lock:
            for o in self._orders:
                status_breakdown[o.status] = status_breakdown.get(o.status, 0) + 1
                if o.status in REVENUE_STATUSES:
                    total_revenue_paise += o.pricing.total_paise
                    paid_orders_count += 1
                    for item in o.items:
                        if item.product_id in product_map:
                            stat = product_map[item.product_id]
                            stat.units_sold += item.quantity
                            stat.revenue_paise += item.line_total_paise
                        else:
                            product_map[item.product_id] = TopProductStat(
                                product_id=item.product_id,
                                product_name=item.product_name,
                                product_slug=item.product_slug,
                                units_sold=item.quantity,
                                revenue_paise=item.line_total_paise,
                            )

            top_products = sorted(
                product_map.values(),
                key=lambda s: (s.revenue_paise, s.units_sold),
                reverse=True,
            )[:5]

            recent_orders = [
                o.model_copy(deep=True)
                for o in sorted(self._orders, key=lambda o: o.created_at, reverse=True)[:5]
            ]

            return OrderDashboardStats(
                total_revenue_paise=total_revenue_paise,
                total_orders=len(self._orders),
                paid_orders_count=paid_orders_count,
                pending_orders_count=status_breakdown["pending"],
                status_breakdown=status_breakdown,
                top_products=top_products,
                recent_orders=recent_orders,
            )
