from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import Coupon
from app.repositories.interfaces import (
    CouponRepository,
    CreateCouponInput,
    UpdateCouponInput,
)
from app.repositories.supabase.db import iso_str


def _row_to_coupon(row: dict[str, Any]) -> Coupon:
    return Coupon(
        id=row["id"],
        code=row["code"],
        description=row["description"],
        type=row["type"],
        value=int(row["value"]),
        min_order_paise=int(row["min_order_paise"]),
        max_discount_paise=(
            int(row["max_discount_paise"])
            if row["max_discount_paise"] is not None
            else None
        ),
        expires_at=iso_str(row["expires_at"]) or "",
        usage_limit=int(row["usage_limit"]),
        used_count=int(row["used_count"]),
        is_active=bool(row["is_active"]),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


class SupabaseCouponRepository(CouponRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def find_by_code(self, code: str) -> Optional[Coupon]:
        normalized = code.strip().upper()
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM coupons WHERE UPPER(code) = %s LIMIT 1;",
                (normalized,),
            ).fetchone()
            return _row_to_coupon(row) if row else None

    def find_by_id(self, coupon_id: str) -> Optional[Coupon]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM coupons WHERE id = %s;", (coupon_id,)
            ).fetchone()
            return _row_to_coupon(row) if row else None

    def list(self) -> list[Coupon]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM coupons ORDER BY created_at DESC;"
            ).fetchall()
            return [_row_to_coupon(r) for r in rows]

    def create(self, data: CreateCouponInput) -> Coupon:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO coupons (
                  code, description, type, value, min_order_paise,
                  max_discount_paise, expires_at, usage_limit, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.code.strip().upper(),
                    data.description,
                    data.type,
                    data.value,
                    data.min_order_paise,
                    data.max_discount_paise,
                    data.expires_at,
                    data.usage_limit,
                    data.is_active,
                ),
            ).fetchone()
            assert row is not None
            return _row_to_coupon(row)

    def update(self, coupon_id: str, data: UpdateCouponInput) -> Optional[Coupon]:
        patch = data.model_dump(exclude_unset=True)
        if not patch:
            return self.find_by_id(coupon_id)

        if "code" in patch and isinstance(patch["code"], str):
            patch["code"] = patch["code"].strip().upper()

        sets = [f"{k} = %s" for k in patch.keys()]
        sets.append("updated_at = now()")
        params = [*patch.values(), coupon_id]
        with self._pool.connection() as conn:
            row = conn.execute(
                f"UPDATE coupons SET {', '.join(sets)} WHERE id = %s RETURNING *;",
                tuple(params),
            ).fetchone()
            return _row_to_coupon(row) if row else None

    def delete(self, coupon_id: str) -> bool:
        with self._pool.connection() as conn:
            res = conn.execute("DELETE FROM coupons WHERE id = %s;", (coupon_id,))
            return res.rowcount > 0

    def increment_usage_if_available(
        self, coupon_id: str, now_iso: str
    ) -> Optional[Coupon]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE coupons
                SET used_count = used_count + 1,
                    updated_at = %s
                WHERE id = %s
                  AND is_active = true
                  AND expires_at > %s
                  AND used_count < usage_limit
                RETURNING *;
                """,
                (now_iso, coupon_id, now_iso),
            ).fetchone()
            return _row_to_coupon(row) if row else None

    def decrement_usage(self, coupon_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE coupons
                SET used_count = GREATEST(0, used_count - 1),
                    updated_at = now()
                WHERE id = %s;
                """,
                (coupon_id,),
            )
