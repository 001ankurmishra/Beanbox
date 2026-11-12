from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import OAuthAccount, OAuthProvider
from app.repositories.interfaces import CreateOAuthAccountInput, OAuthAccountRepository
from app.repositories.supabase.db import iso_str


def _row_to_oauth(row: dict[str, Any]) -> OAuthAccount:
    return OAuthAccount(
        id=row["id"],
        user_id=row["user_id"],
        provider=row["provider"],
        provider_user_id=row["provider_user_id"],
        provider_email=row["provider_email"],
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


class SupabaseOAuthAccountRepository(OAuthAccountRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def find_by_provider_user(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> Optional[OAuthAccount]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM oauth_accounts
                WHERE provider = %s AND provider_user_id = %s
                LIMIT 1;
                """,
                (provider, provider_user_id),
            ).fetchone()
            return _row_to_oauth(row) if row else None

    def list_for_user(self, user_id: str) -> list[OAuthAccount]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM oauth_accounts WHERE user_id = %s ORDER BY created_at DESC;",
                (user_id,),
            ).fetchall()
            return [_row_to_oauth(r) for r in rows]

    def create(self, data: CreateOAuthAccountInput) -> OAuthAccount:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO oauth_accounts (user_id, provider, provider_user_id, provider_email)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider, provider_user_id) DO UPDATE
                    SET provider_email = EXCLUDED.provider_email,
                        updated_at = now()
                RETURNING *;
                """,
                (
                    data.user_id,
                    data.provider,
                    data.provider_user_id,
                    data.provider_email.strip().lower(),
                ),
            ).fetchone()
            assert row is not None
            return _row_to_oauth(row)
