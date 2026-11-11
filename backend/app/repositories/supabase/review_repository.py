from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import Review
from app.repositories.interfaces import (
    CreateReviewInput,
    ReviewRepository,
    ReviewStats,
)
from app.repositories.supabase.db import iso_str


def _row_to_review(row: dict[str, Any]) -> Review:
    return Review(
        id=row["id"],
        product_id=row["product_id"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        rating=int(row["rating"]),
        title=row["title"],
        comment=row["comment"],
        verified_purchase=bool(row["verified_purchase"]),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


class SupabaseReviewRepository(ReviewRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def _compute_stats(self, conn: Any, product_id: str) -> ReviewStats:
        rows = conn.execute(
            """
            SELECT rating, COUNT(*) AS cnt
            FROM reviews
            WHERE product_id = %s
            GROUP BY rating;
            """,
            (product_id,),
        ).fetchall()
        distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_cnt = 0
        total_sum = 0
        for r in rows:
            star = int(r["rating"])
            cnt = int(r["cnt"])
            distribution[star] = cnt
            total_cnt += cnt
            total_sum += star * cnt

        avg = round(total_sum / total_cnt, 2) if total_cnt > 0 else 0.0
        return ReviewStats(average=avg, count=total_cnt, distribution=distribution)

    def list_by_product_id(
        self, product_id: str, page: int, limit: int
    ) -> tuple[list[Review], int, ReviewStats]:
        offset = (page - 1) * limit
        with self._pool.connection() as conn:
            stats = self._compute_stats(conn, product_id)
            rows = conn.execute(
                """
                SELECT * FROM reviews
                WHERE product_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
                """,
                (product_id, limit, offset),
            ).fetchall()
            return [_row_to_review(r) for r in rows], stats.count, stats

    def find_by_id(self, review_id: str) -> Optional[Review]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE id = %s;", (review_id,)
            ).fetchone()
            return _row_to_review(row) if row else None

    def find_by_user_and_product(
        self, user_id: str, product_id: str
    ) -> Optional[Review]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE user_id = %s AND product_id = %s;",
                (user_id, product_id),
            ).fetchone()
            return _row_to_review(row) if row else None

    def create(self, data: CreateReviewInput) -> Review:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO reviews (
                  product_id, user_id, user_name, rating, title, comment, verified_purchase
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.product_id,
                    data.user_id,
                    data.user_name,
                    data.rating,
                    data.title,
                    data.comment,
                    data.verified_purchase,
                ),
            ).fetchone()
            assert row is not None
            return _row_to_review(row)

    def delete(self, review_id: str) -> bool:
        with self._pool.connection() as conn:
            res = conn.execute("DELETE FROM reviews WHERE id = %s;", (review_id,))
            return res.rowcount > 0

    def get_stats_for_product(self, product_id: str) -> ReviewStats:
        with self._pool.connection() as conn:
            return self._compute_stats(conn, product_id)
