from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import RecoveryCode, TotpSecret
from app.repositories.interfaces import TwoFactorRepository
from app.repositories.supabase.db import iso_str


def _row_to_totp(row: dict[str, Any]) -> TotpSecret:
    return TotpSecret(
        id=row["id"],
        user_id=row["user_id"],
        encrypted_secret=row["encrypted_secret"],
        is_enabled=bool(row["is_enabled"]),
        last_used_timestep=row.get("last_used_timestep"),
        verified_at=iso_str(row.get("verified_at")),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


def _row_to_recovery(row: dict[str, Any]) -> RecoveryCode:
    return RecoveryCode(
        id=row["id"],
        user_id=row["user_id"],
        code_hash=row["code_hash"],
        used_at=iso_str(row.get("used_at")),
        created_at=iso_str(row["created_at"]) or "",
    )


class SupabaseTwoFactorRepository(TwoFactorRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def get_totp_secret(self, user_id: str) -> Optional[TotpSecret]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM totp_secrets WHERE user_id = %s;",
                (user_id,),
            ).fetchone()
            return _row_to_totp(row) if row else None

    def upsert_pending_totp(
        self, user_id: str, encrypted_secret: str
    ) -> TotpSecret:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO totp_secrets (user_id, encrypted_secret, is_enabled, verified_at, last_used_timestep)
                VALUES (%s, %s, false, NULL, NULL)
                ON CONFLICT (user_id) DO UPDATE
                    SET encrypted_secret = EXCLUDED.encrypted_secret,
                        is_enabled = false,
                        verified_at = NULL,
                        last_used_timestep = NULL,
                        updated_at = now()
                RETURNING *;
                """,
                (user_id, encrypted_secret),
            ).fetchone()
            assert row is not None
            return _row_to_totp(row)

    def enable_totp(self, user_id: str) -> Optional[TotpSecret]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE totp_secrets
                SET is_enabled = true, verified_at = now(), updated_at = now()
                WHERE user_id = %s
                RETURNING *;
                """,
                (user_id,),
            ).fetchone()
            return _row_to_totp(row) if row else None

    def update_last_used_timestep(self, user_id: str, timestep: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE totp_secrets
                SET last_used_timestep = %s, updated_at = now()
                WHERE user_id = %s;
                """,
                (timestep, user_id),
            )

    def disable_totp(self, user_id: str) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM recovery_codes WHERE user_id = %s;", (user_id,))
                conn.execute("DELETE FROM totp_secrets WHERE user_id = %s;", (user_id,))

    def replace_recovery_codes(
        self, user_id: str, code_hashes: list[str]
    ) -> list[RecoveryCode]:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM recovery_codes WHERE user_id = %s;", (user_id,))
                rows = []
                for h in code_hashes:
                    r = conn.execute(
                        """
                        INSERT INTO recovery_codes (user_id, code_hash)
                        VALUES (%s, %s)
                        RETURNING *;
                        """,
                        (user_id, h),
                    ).fetchone()
                    if r:
                        rows.append(_row_to_recovery(r))
                return rows

    def consume_recovery_code(self, user_id: str, code_hash: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE recovery_codes
                SET used_at = now()
                WHERE user_id = %s AND code_hash = %s AND used_at IS NULL
                RETURNING id;
                """,
                (user_id, code_hash),
            ).fetchone()
            return row is not None

    def count_unused_recovery_codes(self, user_id: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM recovery_codes
                WHERE user_id = %s AND used_at IS NULL;
                """,
                (user_id,),
            ).fetchone()
            return int(row["cnt"]) if row else 0
