from __future__ import annotations

from typing import Any, Literal, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import PaymentEvent
from app.repositories.interfaces import PaymentEventRepository
from app.repositories.supabase.db import iso_str


class SupabasePaymentEventRepository(PaymentEventRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def has_processed_event(self, event_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM payment_events WHERE event_id = %s LIMIT 1;",
                (event_id,),
            ).fetchone()
            return row is not None

    def record_event(
        self,
        event_id: str,
        provider: Literal["stripe", "mock"],
        event_type: str,
        order_id: Optional[str] = None,
    ) -> PaymentEvent:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO payment_events (event_id, provider, event_type, order_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET event_type = EXCLUDED.event_type
                RETURNING *;
                """,
                (event_id, provider, event_type, order_id),
            ).fetchone()
            assert row is not None
            return PaymentEvent(
                id=row["id"],
                event_id=row["event_id"],
                provider=row["provider"],
                event_type=row["event_type"],
                order_id=row["order_id"],
                processed_at=iso_str(row["processed_at"]) or "",
            )
