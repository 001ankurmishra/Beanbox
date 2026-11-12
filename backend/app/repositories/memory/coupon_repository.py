from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import Coupon
from app.repositories.interfaces import (
    CouponRepository,
    CreateCouponInput,
    UpdateCouponInput,
)
from app.utils.errors import ConflictError


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class InMemoryCouponRepository(CouponRepository):
    def __init__(self, initial_coupons: Optional[list[Coupon]] = None) -> None:
        self._lock = RLock()
        self._coupons: list[Coupon] = [
            c.model_copy(deep=True) for c in (initial_coupons or [])
        ]

    def find_by_code(self, code: str) -> Optional[Coupon]:
        normalized = code.strip().upper()
        with self._lock:
            for c in self._coupons:
                if c.code.upper() == normalized:
                    return c.model_copy(deep=True)
            return None

    def find_by_id(self, coupon_id: str) -> Optional[Coupon]:
        with self._lock:
            for c in self._coupons:
                if c.id == coupon_id:
                    return c.model_copy(deep=True)
            return None

    def list(self) -> list[Coupon]:
        with self._lock:
            sorted_list = sorted(self._coupons, key=lambda c: c.created_at, reverse=True)
            return [c.model_copy(deep=True) for c in sorted_list]

    def create(self, data: CreateCouponInput) -> Coupon:
        now = _now_iso()
        norm_code = data.code.strip().upper()
        with self._lock:
            if any(c.code.upper() == norm_code for c in self._coupons):
                raise ConflictError("A coupon with this code already exists")
            coupon = Coupon(
                id=str(uuid4()),
                code=norm_code,
                description=data.description,
                type=data.type,
                value=data.value,
                min_order_paise=data.min_order_paise,
                max_discount_paise=data.max_discount_paise,
                expires_at=data.expires_at,
                usage_limit=data.usage_limit,
                used_count=0,
                is_active=data.is_active,
                created_at=now,
                updated_at=now,
            )
            self._coupons.append(coupon.model_copy(deep=True))
            return coupon

    def update(self, coupon_id: str, data: UpdateCouponInput) -> Optional[Coupon]:
        with self._lock:
            for idx, existing in enumerate(self._coupons):
                if existing.id == coupon_id:
                    updated = existing.model_copy(deep=True)
                    patch = data.model_dump(exclude_unset=True)
                    if "code" in patch and isinstance(patch["code"], str):
                        norm_code = patch["code"].strip().upper()
                        if any(
                            c.code.upper() == norm_code and c.id != coupon_id
                            for c in self._coupons
                        ):
                            raise ConflictError("A coupon with this code already exists")
                        patch["code"] = norm_code
                    for k, val in patch.items():
                        setattr(updated, k, val)
                    updated.updated_at = _now_iso()
                    self._coupons[idx] = updated.model_copy(deep=True)
                    return updated
            return None

    def delete(self, coupon_id: str) -> bool:
        with self._lock:
            before = len(self._coupons)
            self._coupons = [c for c in self._coupons if c.id != coupon_id]
            return len(self._coupons) < before

    def increment_usage_if_available(
        self, coupon_id: str, now_iso: str
    ) -> Optional[Coupon]:
        now_dt = _parse_iso(now_iso)
        with self._lock:
            for c in self._coupons:
                if c.id == coupon_id:
                    if not c.is_active:
                        return None
                    if _parse_iso(c.expires_at) <= now_dt:
                        return None
                    if c.used_count >= c.usage_limit:
                        return None
                    c.used_count += 1
                    c.updated_at = now_iso
                    return c.model_copy(deep=True)
            return None

    def decrement_usage(self, coupon_id: str) -> None:
        with self._lock:
            for c in self._coupons:
                if c.id == coupon_id and c.used_count > 0:
                    c.used_count -= 1
                    c.updated_at = _now_iso()
                    return
