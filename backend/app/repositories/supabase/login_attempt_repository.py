from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import LoginAttemptKeyType, LoginAttemptRecord
from app.repositories.interfaces import LoginAttemptRepository
from app.repositories.supabase.db import iso_str


def _row_to_record(row: dict[str, Any]) -> LoginAttemptRecord:
    return LoginAttemptRecord(
        id=row["id"],
        key=row["key"],
        key_type=row["key_type"],
        failed_count=int(row["failed_count"]),
        lockout_level=int(row["lockout_level"]),
        first_failed_at=iso_str(row["first_failed_at"]) or "",
        last_failed_at=iso_str(row["last_failed_at"]) or "",
        locked_until=iso_str(row.get("locked_until")),
    )


class SupabaseLoginAttemptRepository(LoginAttemptRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def get_by_key(self, key: str) -> Optional[LoginAttemptRecord]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM login_attempts WHERE key = %s LIMIT 1;",
                (key,),
            ).fetchone()
            return _row_to_record(row) if row else None

    def record_failure(
        self,
        key: str,
        key_type: LoginAttemptKeyType,
        max_failures: int = 5,
        base_lock_minutes: int = 15,
        failure_window_minutes: int = 15,
    ) -> LoginAttemptRecord:
        now = datetime.now(timezone.utc)
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM login_attempts WHERE key = %s FOR UPDATE;",
                    (key,),
                ).fetchone()
                if row is None:
                    failed_count = 1
                    lockout_level = 1 if failed_count >= max_failures else 0
                    locked_until = (
                        now + timedelta(minutes=base_lock_minutes)
                        if lockout_level > 0
                        else None
                    )
                    inserted = conn.execute(
                        """
                        INSERT INTO login_attempts (
                            key, key_type, failed_count, lockout_level,
                            first_failed_at, last_failed_at, locked_until
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING *;
                        """,
                        (key, key_type, failed_count, lockout_level, now, now, locked_until),
                    ).fetchone()
                    assert inserted is not None
                    return _row_to_record(inserted)

                last_failed_raw = row["last_failed_at"]
                last_failed_dt = (
                    last_failed_raw
                    if last_failed_raw.tzinfo
                    else last_failed_raw.replace(tzinfo=timezone.utc)
                )
                window_expired = (now - last_failed_dt) > timedelta(
                    minutes=failure_window_minutes
                )

                if window_expired:
                    failed_count = 1
                    lockout_level = 0
                    first_failed_at = now
                    existing_lock = None
                    currently_locked = False
                else:
                    failed_count = int(row["failed_count"]) + 1
                    lockout_level = int(row["lockout_level"])
                    first_failed_at = row["first_failed_at"]
                    existing_lock = row.get("locked_until")
                    currently_locked = False
                    if existing_lock is not None:
                        lock_dt = (
                            existing_lock
                            if existing_lock.tzinfo
                            else existing_lock.replace(tzinfo=timezone.utc)
                        )
                        currently_locked = lock_dt > now

                next_locked_until = existing_lock
                if not currently_locked and failed_count >= max_failures:
                    lockout_level = min(lockout_level + 1, 7)
                    lock_minutes = base_lock_minutes * (2 ** (lockout_level - 1))
                    next_locked_until = now + timedelta(minutes=lock_minutes)

                updated = conn.execute(
                    """
                    UPDATE login_attempts
                    SET failed_count = %s,
                        lockout_level = %s,
                        first_failed_at = %s,
                        last_failed_at = %s,
                        locked_until = %s
                    WHERE key = %s
                    RETURNING *;
                    """,
                    (failed_count, lockout_level, first_failed_at, now, next_locked_until, key),
                ).fetchone()
                assert updated is not None
                return _row_to_record(updated)

    def reset(self, key: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM login_attempts WHERE key = %s;", (key,))

    def cleanup_stale_attempts(
        self, idle_days: int = 7, batch_size: int = 1000
    ) -> int:
        total = 0
        with self._pool.connection() as conn:
            while True:
                with conn.transaction():
                    cur = conn.execute(
                        """
                        WITH doomed AS (
                            SELECT id FROM login_attempts
                            WHERE last_failed_at < now() - make_interval(days => %s)
                              AND (locked_until IS NULL OR locked_until < now())
                            LIMIT %s
                        )
                        DELETE FROM login_attempts
                        WHERE id IN (SELECT id FROM doomed)
                        RETURNING id;
                        """,
                        (idle_days, batch_size),
                    )
                    deleted = len(cur.fetchall())
                    total += deleted
                    if deleted < batch_size:
                        break
        return total
