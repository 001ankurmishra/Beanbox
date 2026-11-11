from __future__ import annotations

from typing import Any

from psycopg_pool import ConnectionPool

from app.models.domain import WishlistItem
from app.repositories.interfaces import WishlistRepository
from app.repositories.supabase.db import iso_str


def _row_to_wishlist(row: dict[str, Any]) -> WishlistItem:
    return WishlistItem(
        id=row["id"],
        user_id=row["user_id"],
        product_id=row["product_id"],
        created_at=iso_str(row["created_at"]) or "",
    )


class SupabaseWishlistRepository(WishlistRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def list_by_user_id(self, user_id: str) -> list[WishlistItem]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM wishlist_items
                WHERE user_id = %s
                ORDER BY created_at DESC;
                """,
                (user_id,),
            ).fetchall()
            return [_row_to_wishlist(r) for r in rows]

    def add(self, user_id: str, product_id: str) -> WishlistItem:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO wishlist_items (user_id, product_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, product_id) DO UPDATE SET product_id = EXCLUDED.product_id
                RETURNING *;
                """,
                (user_id, product_id),
            ).fetchone()
            assert row is not None
            return _row_to_wishlist(row)

    def remove(self, user_id: str, product_id: str) -> bool:
        with self._pool.connection() as conn:
            res = conn.execute(
                "DELETE FROM wishlist_items WHERE user_id = %s AND product_id = %s;",
                (user_id, product_id),
            )
            return res.rowcount > 0

    def has_item(self, user_id: str, product_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM wishlist_items WHERE user_id = %s AND product_id = %s LIMIT 1;",
                (user_id, product_id),
            ).fetchone()
            return row is not None
