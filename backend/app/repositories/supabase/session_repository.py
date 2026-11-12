from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import Session
from app.repositories.interfaces import CreateSessionInput, SessionRepository
from app.repositories.supabase.db import iso_str


def _row_to_session(row: dict[str, Any]) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        refresh_token_hash=row["refresh_token_hash"],
        previous_refresh_hashes=list(row.get("previous_refresh_hashes") or []),
        grace_refresh_hash=row.get("grace_refresh_hash"),
        grace_expires_at=iso_str(row.get("grace_expires_at")),
        family_id=row["family_id"],
        user_agent=row["user_agent"],
        ip=row["ip"],
        created_at=iso_str(row["created_at"]) or "",
        last_used_at=iso_str(row["last_used_at"]) or "",
        expires_at=iso_str(row["expires_at"]) or "",
        revoked_at=iso_str(row.get("revoked_at")),
    )


class SupabaseSessionRepository(SessionRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def create(self, data: CreateSessionInput) -> Session:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO sessions (
                    user_id, refresh_token_hash, family_id, user_agent, ip, expires_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.user_id,
                    data.refresh_token_hash,
                    data.family_id,
                    data.user_agent,
                    data.ip,
                    data.expires_at,
                ),
            ).fetchone()
            assert row is not None
            return _row_to_session(row)

    def find_by_id(self, session_id: str) -> Optional[Session]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = %s;",
                (session_id,),
            ).fetchone()
            return _row_to_session(row) if row else None

    def find_by_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE refresh_token_hash = %s LIMIT 1;",
                (token_hash,),
            ).fetchone()
            return _row_to_session(row) if row else None

    def find_by_grace_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE grace_refresh_hash = %s LIMIT 1;",
                (token_hash,),
            ).fetchone()
            return _row_to_session(row) if row else None

    def find_by_previous_refresh_hash(self, token_hash: str) -> Optional[Session]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM sessions
                WHERE previous_refresh_hashes @> ARRAY[%s::text]
                LIMIT 1;
                """,
                (token_hash,),
            ).fetchone()
            return _row_to_session(row) if row else None

    def rotate_refresh_token(
        self,
        session_id: str,
        expected_hash: str,
        new_hash: str,
        new_expires_at: str,
        ip: str,
        user_agent: str,
        grace_expires_at: Optional[str] = None,
        max_history: int = 100,
    ) -> Optional[Session]:
        grace_hash = expected_hash if grace_expires_at is not None else None
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE sessions
                SET
                    previous_refresh_hashes = CASE
                        WHEN COALESCE(array_length(previous_refresh_hashes, 1), 0) >= %s
                        THEN (previous_refresh_hashes[2:] || ARRAY[%s::text])
                        ELSE array_append(previous_refresh_hashes, %s::text)
                    END,
                    refresh_token_hash = %s,
                    grace_refresh_hash = %s,
                    grace_expires_at = %s,
                    expires_at = %s,
                    ip = %s,
                    user_agent = %s,
                    last_used_at = now()
                WHERE id = %s
                  AND refresh_token_hash = %s
                  AND revoked_at IS NULL
                RETURNING *;
                """,
                (
                    max_history,
                    expected_hash,
                    expected_hash,
                    new_hash,
                    grace_hash,
                    grace_expires_at,
                    new_expires_at,
                    ip,
                    user_agent,
                    session_id,
                    expected_hash,
                ),
            ).fetchone()
            return _row_to_session(row) if row else None

    def check_device_history(self, user_id: str, user_agent: str) -> tuple[bool, bool]:
        normalized = (user_agent or "").strip()
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_count,
                    COALESCE(BOOL_OR(BTRIM(user_agent) = %s), false) AS seen_device
                FROM sessions
                WHERE user_id = %s;
                """,
                (normalized, user_id),
            ).fetchone()
            if not row or int(row["total_count"] or 0) == 0:
                return False, False
            return True, bool(row["seen_device"])

    def touch_last_used(self, session_id: str, ip: str, user_agent: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET last_used_at = now(), ip = %s, user_agent = %s
                WHERE id = %s AND revoked_at IS NULL;
                """,
                (ip, user_agent, session_id),
            )

    def list_active_for_user(self, user_id: str) -> list[Session]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > now()
                ORDER BY last_used_at DESC;
                """,
                (user_id,),
            ).fetchall()
            return [_row_to_session(r) for r in rows]

    def revoke_by_id(self, session_id: str, user_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = COALESCE(revoked_at, now())
                WHERE id = %s AND user_id = %s
                RETURNING id;
                """,
                (session_id, user_id),
            ).fetchone()
            return row is not None

    def revoke_family(self, family_id: str) -> int:
        with self._pool.connection() as conn:
            cur = conn.execute(
                """
                UPDATE sessions
                SET revoked_at = now()
                WHERE family_id = %s AND revoked_at IS NULL;
                """,
                (family_id,),
            )
            return int(cur.rowcount or 0)

    def revoke_all_for_user(
        self, user_id: str, except_session_id: Optional[str] = None
    ) -> int:
        with self._pool.connection() as conn:
            if except_session_id:
                cur = conn.execute(
                    """
                    UPDATE sessions
                    SET revoked_at = now()
                    WHERE user_id = %s
                      AND id <> %s
                      AND revoked_at IS NULL;
                    """,
                    (user_id, except_session_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE sessions
                    SET revoked_at = now()
                    WHERE user_id = %s
                      AND revoked_at IS NULL;
                    """,
                    (user_id,),
                )
            return int(cur.rowcount or 0)
