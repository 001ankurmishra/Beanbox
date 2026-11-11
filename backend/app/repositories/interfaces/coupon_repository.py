from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import CamelModel, Coupon, CouponType


class CreateCouponInput(CamelModel):
    code: str
    description: str
    type: CouponType
    value: int
    min_order_paise: int
    max_discount_paise: Optional[int] = None
    expires_at: str
    usage_limit: int
    is_active: bool = True


class UpdateCouponInput(CamelModel):
    code: Optional[str] = None
    description: Optional[str] = None
    type: Optional[CouponType] = None
    value: Optional[int] = None
    min_order_paise: Optional[int] = None
    max_discount_paise: Optional[int] = None
    expires_at: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None


class CouponRepository(ABC):
    @abstractmethod
    def find_by_code(self, code: str) -> Optional[Coupon]: ...

    @abstractmethod
    def find_by_id(self, coupon_id: str) -> Optional[Coupon]: ...

    @abstractmethod
    def list(self) -> list[Coupon]: ...

    @abstractmethod
    def create(self, data: CreateCouponInput) -> Coupon: ...

    @abstractmethod
    def update(self, coupon_id: str, data: UpdateCouponInput) -> Optional[Coupon]: ...

    @abstractmethod
    def delete(self, coupon_id: str) -> bool: ...

    @abstractmethod
    def increment_usage_if_available(
        self, coupon_id: str, now_iso: str
    ) -> Optional[Coupon]:
        """Atomically increments used_count only if active, unexpired, and used_count < usage_limit."""
        ...

    @abstractmethod
    def decrement_usage(self, coupon_id: str) -> None: ...
