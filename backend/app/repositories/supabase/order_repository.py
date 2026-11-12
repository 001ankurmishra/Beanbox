from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Literal, Optional
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.models.domain import (
    Order,
    OrderAddressSnapshot,
    OrderItem,
    OrderPricing,
    OrderStatus,
)
from app.repositories.interfaces import (
    CreateOrderInput,
    OrderDashboardStats,
    OrderRepository,
    OrderUpdateFields,
    TopProductStat,
)
from app.repositories.supabase.db import iso_str

REVENUE_STATUSES: tuple[str, ...] = ("paid", "processing", "shipped", "delivered")


def _row_to_order_item(row: dict[str, Any]) -> OrderItem:
    return OrderItem(
        product_id=row["product_id"],
        variant_id=row["variant_id"],
        sku=row["sku"],
        product_name=row["product_name"],
        product_slug=row["product_slug"],
        variant_label=row["variant_label"],
        image=row["image"],
        unit_price_paise=int(row["unit_price_paise"]),
        quantity=int(row["quantity"]),
        line_total_paise=int(row["line_total_paise"]),
    )


def _row_to_order(row: dict[str, Any], items: list[OrderItem]) -> Order:
    addr = (
        row["shipping_address"]
        if isinstance(row["shipping_address"], dict)
        else json.loads(row["shipping_address"])
    )
    pricing = (
        row["pricing"]
        if isinstance(row["pricing"], dict)
        else json.loads(row["pricing"])
    )
    return Order(
        id=row["id"],
        order_number=row["order_number"],
        user_id=row["user_id"],
        items=items,
        shipping_address=OrderAddressSnapshot.model_validate(addr),
        coupon_code=row["coupon_code"],
        coupon_id=row["coupon_id"],
        pricing=OrderPricing.model_validate(pricing),
        status=row["status"],
        payment_status=row["payment_status"],
        payment_provider=row["payment_provider"],
        payment_session_id=row["payment_session_id"],
        payment_intent_id=row["payment_intent_id"],
        stock_released=bool(row["stock_released"]),
        cancel_reason=row["cancel_reason"],
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
        paid_at=iso_str(row["paid_at"]),
        shipped_at=iso_str(row["shipped_at"]),
        delivered_at=iso_str(row["delivered_at"]),
        cancelled_at=iso_str(row["cancelled_at"]),
    )


class SupabaseOrderRepository(OrderRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def _fetch_items_map(
        self, conn: Any, order_ids: list[str]
    ) -> dict[str, list[OrderItem]]:
        if not order_ids:
            return {}
        rows = conn.execute(
            "SELECT * FROM order_items WHERE order_id = ANY(%s);",
            (order_ids,),
        ).fetchall()
        grouped: dict[str, list[OrderItem]] = defaultdict(list)
        for r in rows:
            grouped[r["order_id"]].append(_row_to_order_item(r))
        return grouped

    def create(self, data: CreateOrderInput) -> Order:
        order_id = str(uuid4())
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO orders (
                      id, order_number, user_id, shipping_address,
                      coupon_code, coupon_id, pricing, status, payment_status
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, 'pending', 'unpaid')
                    RETURNING *;
                    """,
                    (
                        order_id,
                        data.order_number,
                        data.user_id,
                        json.dumps(data.shipping_address.model_dump(mode="json")),
                        data.coupon_code,
                        data.coupon_id,
                        json.dumps(data.pricing.model_dump(mode="json")),
                    ),
                ).fetchone()

                for item in data.items:
                    conn.execute(
                        """
                        INSERT INTO order_items (
                          order_id, product_id, variant_id, sku, product_name,
                          product_slug, variant_label, image, unit_price_paise,
                          quantity, line_total_paise
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            order_id,
                            item.product_id,
                            item.variant_id,
                            item.sku,
                            item.product_name,
                            item.product_slug,
                            item.variant_label,
                            item.image,
                            item.unit_price_paise,
                            item.quantity,
                            item.line_total_paise,
                        ),
                    )
                assert row is not None
                return _row_to_order(row, list(data.items))

    def find_by_id(self, order_id: str) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = %s;", (order_id,)
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    def find_by_id_for_user(self, order_id: str, user_id: str) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = %s AND user_id = %s;",
                (order_id, user_id),
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    def find_by_order_number(self, order_number: str) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_number = %s;", (order_number,)
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [row["id"]]).get(row["id"], [])
            return _row_to_order(row, items)

    def find_by_payment_session_id(self, session_id: str) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE payment_session_id = %s;", (session_id,)
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [row["id"]]).get(row["id"], [])
            return _row_to_order(row, items)

    def list_by_user_id(
        self, user_id: str, page: int, limit: int
    ) -> tuple[list[Order], int]:
        offset = (page - 1) * limit
        with self._pool.connection() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) AS cnt FROM orders WHERE user_id = %s;", (user_id,)
            ).fetchone()
            total = int(cnt["cnt"]) if cnt else 0
            rows = conn.execute(
                "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                (user_id, limit, offset),
            ).fetchall()
            items_map = self._fetch_items_map(conn, [r["id"] for r in rows])
            return [
                _row_to_order(r, items_map.get(r["id"], [])) for r in rows
            ], total

    def list_all(
        self, status: Optional[OrderStatus], page: int, limit: int
    ) -> tuple[list[Order], int]:
        offset = (page - 1) * limit
        where_sql = "WHERE status = %s" if status else ""
        params: tuple[Any, ...] = (status,) if status else ()

        with self._pool.connection() as conn:
            cnt = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM orders {where_sql};", params
            ).fetchone()
            total = int(cnt["cnt"]) if cnt else 0
            rows = conn.execute(
                f"SELECT * FROM orders {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                (*params, limit, offset),
            ).fetchall()
            items_map = self._fetch_items_map(conn, [r["id"] for r in rows])
            return [
                _row_to_order(r, items_map.get(r["id"], [])) for r in rows
            ], total

    def attach_payment_session(
        self,
        order_id: str,
        provider: Literal["stripe", "mock"],
        session_id: str,
        payment_intent_id: Optional[str] = None,
    ) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE orders
                SET payment_provider = %s,
                    payment_session_id = %s,
                    payment_intent_id = COALESCE(%s, payment_intent_id),
                    updated_at = now()
                WHERE id = %s
                RETURNING *;
                """,
                (provider, session_id, payment_intent_id, order_id),
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    @staticmethod
    def _build_update_parts(updates: OrderUpdateFields) -> tuple[list[str], list[Any]]:
        sets: list[str] = []
        params: list[Any] = []
        for field_name in (
            "status",
            "payment_status",
            "payment_intent_id",
            "stock_released",
            "cancel_reason",
            "paid_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
        ):
            val = getattr(updates, field_name)
            if val is not None:
                sets.append(f"{field_name} = %s")
                params.append(val)
        return sets, params

    def update_order(
        self, order_id: str, updates: OrderUpdateFields
    ) -> Optional[Order]:
        sets, params = self._build_update_parts(updates)
        if not sets:
            return self.find_by_id(order_id)

        sets.append("updated_at = now()")
        params.append(order_id)
        with self._pool.connection() as conn:
            row = conn.execute(
                f"UPDATE orders SET {', '.join(sets)} WHERE id = %s RETURNING *;",
                tuple(params),
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    def transition_status(
        self,
        order_id: str,
        expected_status: OrderStatus,
        updates: OrderUpdateFields,
    ) -> Optional[Order]:
        sets, params = self._build_update_parts(updates)
        if not sets:
            return self.find_by_id(order_id)

        sets.append("updated_at = now()")
        params.extend([order_id, expected_status])
        with self._pool.connection() as conn:
            row = conn.execute(
                f"UPDATE orders SET {', '.join(sets)} WHERE id = %s AND status = %s RETURNING *;",
                tuple(params),
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    def claim_cancellation(
        self,
        order_id: str,
        user_id: str,
        cancel_reason: str,
        cancelled_at: str,
    ) -> Optional[Order]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE orders
                SET status = 'cancelled',
                    stock_released = true,
                    cancel_reason = %s,
                    cancelled_at = %s,
                    updated_at = now()
                WHERE id = %s
                  AND user_id = %s
                  AND status IN ('pending', 'paid', 'processing')
                  AND stock_released = false
                RETURNING *;
                """,
                (cancel_reason, cancelled_at, order_id, user_id),
            ).fetchone()
            if not row:
                return None
            items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
            return _row_to_order(row, items)

    def apply_webhook_transition(
        self,
        order_id: str,
        expected_status: Optional[OrderStatus],
        updates: Optional[OrderUpdateFields],
        event_id: str,
        provider: Literal["stripe", "mock"],
        event_type: str,
        payment_event_repo: object,
    ) -> tuple[bool, Optional[Order]]:
        with self._pool.connection() as conn:
            with conn.transaction():
                claimed_row = conn.execute(
                    """
                    INSERT INTO payment_events (event_id, provider, event_type, order_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    RETURNING id;
                    """,
                    (event_id, provider, event_type, order_id),
                ).fetchone()
                if not claimed_row:
                    return False, None
                if updates is None or expected_status is None:
                    return True, None
                sets, params = self._build_update_parts(updates)
                if not sets:
                    return True, None
                sets.append("updated_at = now()")
                params.extend([order_id, expected_status])
                row = conn.execute(
                    f"UPDATE orders SET {', '.join(sets)} WHERE id = %s AND status = %s RETURNING *;",
                    tuple(params),
                ).fetchone()
                if not row:
                    return True, None
                items = self._fetch_items_map(conn, [order_id]).get(order_id, [])
                return True, _row_to_order(row, items)

    def has_verified_purchase(self, user_id: str, product_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                WHERE o.user_id = %s
                  AND o.status = ANY(%s)
                  AND oi.product_id = %s
                LIMIT 1;
                """,
                (user_id, list(REVENUE_STATUSES), product_id),
            ).fetchone()
            return row is not None

    def count_orders_by_user(self, user_ids: list[str]) -> dict[str, int]:
        counts = {uid: 0 for uid in user_ids}
        if not user_ids:
            return counts
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT user_id, COUNT(*) AS cnt
                FROM orders
                WHERE user_id = ANY(%s)
                GROUP BY user_id;
                """,
                (user_ids,),
            ).fetchall()
            for r in rows:
                counts[r["user_id"]] = int(r["cnt"])
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
        with self._pool.connection() as conn:
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status;"
            ).fetchall()
            total_orders = 0
            for r in status_rows:
                c = int(r["cnt"])
                status_breakdown[r["status"]] = c
                total_orders += c

            rev_row = conn.execute(
                """
                SELECT
                  COALESCE(SUM((pricing->>'totalPaise')::bigint), 0) AS revenue_paise,
                  COUNT(*) AS paid_cnt
                FROM orders
                WHERE status = ANY(%s);
                """,
                (list(REVENUE_STATUSES),),
            ).fetchone()

            top_rows = conn.execute(
                """
                SELECT
                  oi.product_id,
                  oi.product_name,
                  oi.product_slug,
                  SUM(oi.quantity)::int AS units_sold,
                  SUM(oi.line_total_paise)::bigint AS revenue_paise
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.status = ANY(%s)
                GROUP BY oi.product_id, oi.product_name, oi.product_slug
                ORDER BY revenue_paise DESC, units_sold DESC
                LIMIT 5;
                """,
                (list(REVENUE_STATUSES),),
            ).fetchall()

            recent_rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT 5;"
            ).fetchall()
            items_map = self._fetch_items_map(conn, [r["id"] for r in recent_rows])

            return OrderDashboardStats(
                total_revenue_paise=int(rev_row["revenue_paise"]) if rev_row else 0,
                total_orders=total_orders,
                paid_orders_count=int(rev_row["paid_cnt"]) if rev_row else 0,
                pending_orders_count=status_breakdown["pending"],
                status_breakdown=status_breakdown,
                top_products=[
                    TopProductStat(
                        product_id=r["product_id"],
                        product_name=r["product_name"],
                        product_slug=r["product_slug"],
                        units_sold=int(r["units_sold"]),
                        revenue_paise=int(r["revenue_paise"]),
                    )
                    for r in top_rows
                ],
                recent_orders=[
                    _row_to_order(r, items_map.get(r["id"], []))
                    for r in recent_rows
                ],
            )
