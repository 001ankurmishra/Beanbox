from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional

from app.models.domain import (
    CamelModel,
    Order,
    OrderAddressSnapshot,
    OrderItem,
    OrderPricing,
    OrderStatus,
    PaymentStatus,
)


@dataclass
class CreateOrderInput:
    order_number: str
    user_id: str
    items: list[OrderItem]
    shipping_address: OrderAddressSnapshot
    pricing: OrderPricing
    coupon_code: Optional[str] = None
    coupon_id: Optional[str] = None


@dataclass
class OrderUpdateFields:
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    payment_intent_id: Optional[str] = None
    stock_released: Optional[bool] = None
    cancel_reason: Optional[str] = None
    paid_at: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None
    cancelled_at: Optional[str] = None


class TopProductStat(CamelModel):
    product_id: str
    product_name: str
    product_slug: str
    units_sold: int
    revenue_paise: int


class OrderDashboardStats(CamelModel):
    total_revenue_paise: int
    total_orders: int
    paid_orders_count: int
    pending_orders_count: int
    status_breakdown: dict[str, int]
    top_products: list[TopProductStat]
    recent_orders: list[Order]


class OrderRepository(ABC):
    @abstractmethod
    def create(self, data: CreateOrderInput) -> Order: ...

    @abstractmethod
    def find_by_id(self, order_id: str) -> Optional[Order]: ...

    @abstractmethod
    def find_by_id_for_user(
        self, order_id: str, user_id: str
    ) -> Optional[Order]: ...

    @abstractmethod
    def find_by_order_number(self, order_number: str) -> Optional[Order]: ...

    @abstractmethod
    def find_by_payment_session_id(self, session_id: str) -> Optional[Order]: ...

    @abstractmethod
    def list_by_user_id(
        self, user_id: str, page: int, limit: int
    ) -> tuple[list[Order], int]: ...

    @abstractmethod
    def list_all(
        self, status: Optional[OrderStatus], page: int, limit: int
    ) -> tuple[list[Order], int]: ...

    @abstractmethod
    def attach_payment_session(
        self,
        order_id: str,
        provider: Literal["stripe", "mock"],
        session_id: str,
        payment_intent_id: Optional[str] = None,
    ) -> Optional[Order]: ...

    @abstractmethod
    def update_order(
        self, order_id: str, updates: OrderUpdateFields
    ) -> Optional[Order]: ...

    @abstractmethod
    def transition_status(
        self,
        order_id: str,
        expected_status: OrderStatus,
        updates: OrderUpdateFields,
    ) -> Optional[Order]: ...

    @abstractmethod
    def claim_cancellation(
        self,
        order_id: str,
        user_id: str,
        cancel_reason: str,
        cancelled_at: str,
    ) -> Optional[Order]: ...

    @abstractmethod
    def apply_webhook_transition(
        self,
        order_id: str,
        expected_status: Optional[OrderStatus],
        updates: Optional[OrderUpdateFields],
        event_id: str,
        provider: Literal["stripe", "mock"],
        event_type: str,
        payment_event_repo: object,
    ) -> tuple[bool, Optional[Order]]: ...

    @abstractmethod
    def has_verified_purchase(self, user_id: str, product_id: str) -> bool: ...

    @abstractmethod
    def count_orders_by_user(self, user_ids: list[str]) -> dict[str, int]: ...

    @abstractmethod
    def get_dashboard_stats(self) -> OrderDashboardStats: ...
