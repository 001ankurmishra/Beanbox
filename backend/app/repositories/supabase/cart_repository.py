from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import Cart, CartItem
from app.repositories.interfaces import CartRepository
from app.repositories.supabase.db import iso_str


class SupabaseCartRepository(CartRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def _load_items(self, conn: Any, cart_id: str) -> list[CartItem]:
        rows = conn.execute(
            "SELECT * FROM cart_items WHERE cart_id = %s ORDER BY added_at ASC;",
            (cart_id,),
        ).fetchall()
        return [
            CartItem(
                product_id=r["product_id"],
                variant_id=r["variant_id"],
                quantity=int(r["quantity"]),
                added_at=iso_str(r["added_at"]) or "",
            )
            for r in rows
        ]

    def find_by_user_id(self, user_id: str) -> Optional[Cart]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM carts WHERE user_id = %s;", (user_id,)
            ).fetchone()
            if not row:
                return None
            return Cart(
                id=row["id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                items=self._load_items(conn, row["id"]),
                updated_at=iso_str(row["updated_at"]) or "",
            )

    def find_by_session_id(self, session_id: str) -> Optional[Cart]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM carts WHERE session_id = %s AND user_id IS NULL;",
                (session_id,),
            ).fetchone()
            if not row:
                return None
            return Cart(
                id=row["id"],
                user_id=row["user_id"],
                session_id=row["session_id"],
                items=self._load_items(conn, row["id"]),
                updated_at=iso_str(row["updated_at"]) or "",
            )

    def _replace_items(self, conn: Any, cart_id: str, items: list[CartItem]) -> None:
        conn.execute("DELETE FROM cart_items WHERE cart_id = %s;", (cart_id,))
        for item in items:
            conn.execute(
                """
                INSERT INTO cart_items (cart_id, product_id, variant_id, quantity, added_at)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (
                    cart_id,
                    item.product_id,
                    item.variant_id,
                    item.quantity,
                    item.added_at,
                ),
            )

    def upsert_for_user(self, user_id: str, items: list[CartItem]) -> Cart:
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO carts (user_id, updated_at)
                    VALUES (%s, now())
                    ON CONFLICT (user_id) DO UPDATE SET updated_at = now()
                    RETURNING *;
                    """,
                    (user_id,),
                ).fetchone()
                assert row is not None
                self._replace_items(conn, row["id"], items)
                return Cart(
                    id=row["id"],
                    user_id=row["user_id"],
                    session_id=row["session_id"],
                    items=self._load_items(conn, row["id"]),
                    updated_at=iso_str(row["updated_at"]) or "",
                )

    def upsert_for_session(self, session_id: str, items: list[CartItem]) -> Cart:
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    INSERT INTO carts (session_id, updated_at)
                    VALUES (%s, now())
                    ON CONFLICT (session_id) DO UPDATE SET updated_at = now()
                    RETURNING *;
                    """,
                    (session_id,),
                ).fetchone()
                assert row is not None
                self._replace_items(conn, row["id"], items)
                return Cart(
                    id=row["id"],
                    user_id=row["user_id"],
                    session_id=row["session_id"],
                    items=self._load_items(conn, row["id"]),
                    updated_at=iso_str(row["updated_at"]) or "",
                )

    def clear_for_user(self, user_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE user_id = %s);",
                (user_id,),
            )

    def clear_for_session(self, session_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE session_id = %s AND user_id IS NULL);",
                (session_id,),
            )

    def delete_by_session_id(self, session_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM carts WHERE session_id = %s AND user_id IS NULL;",
                (session_id,),
            )
