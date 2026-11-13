from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import EmailVerificationToken, PasswordResetToken, User, UserRole
from app.repositories.interfaces import CreateUserInput, UpdateUserInput, UserRepository
from app.repositories.supabase.db import iso_str, map_pg_conflict


def _row_to_user(row: dict[str, Any]) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        password_hash=row["password_hash"],
        role=row["role"],
        email_verified=bool(row.get("email_verified", False)),
        email_verified_at=iso_str(row.get("email_verified_at")),
        totp_enabled=bool(row.get("totp_enabled", False)),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


def _row_to_reset_token(row: dict[str, Any]) -> PasswordResetToken:
    return PasswordResetToken(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        expires_at=iso_str(row["expires_at"]) or "",
        used_at=iso_str(row["used_at"]),
        created_at=iso_str(row["created_at"]) or "",
    )


def _row_to_verify_token(row: dict[str, Any]) -> EmailVerificationToken:
    return EmailVerificationToken(
        id=row["id"],
        user_id=row["user_id"],
        token_hash=row["token_hash"],
        expires_at=iso_str(row["expires_at"]) or "",
        used_at=iso_str(row["used_at"]),
        created_at=iso_str(row["created_at"]) or "",
    )


class SupabaseUserRepository(UserRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def find_by_id(self, user_id: str) -> Optional[User]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = %s;",
                (user_id,),
            ).fetchone()
            return _row_to_user(row) if row else None

    def find_by_email(self, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = %s LIMIT 1;",
                (normalized,),
            ).fetchone()
            return _row_to_user(row) if row else None

    def create(self, data: CreateUserInput) -> User:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    """
                    INSERT INTO users (
                        name, email, phone, password_hash, role,
                        email_verified, email_verified_at, totp_enabled
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *;
                    """,
                    (
                        data.name.strip(),
                        data.email.strip().lower(),
                        data.phone.strip() if data.phone else None,
                        data.password_hash,
                        data.role,
                        data.email_verified,
                        data.email_verified_at,
                        data.totp_enabled,
                    ),
                ).fetchone()
            except Exception as exc:
                map_pg_conflict(
                    exc,
                    unique_message="An account with this email already exists",
                    unique_code="EMAIL_ALREADY_EXISTS",
                )
                raise
            assert row is not None
            return _row_to_user(row)

    def update(self, user_id: str, data: UpdateUserInput) -> Optional[User]:
        sets: list[str] = []
        params: list[Any] = []
        if data.name is not None:
            sets.append("name = %s")
            params.append(data.name.strip())
        if data.phone is not None:
            sets.append("phone = %s")
            params.append(data.phone.strip())
        if data.password_hash is not None:
            sets.append("password_hash = %s")
            params.append(data.password_hash)
        if data.role is not None:
            sets.append("role = %s")
            params.append(data.role)
        if data.email_verified is not None:
            sets.append("email_verified = %s")
            params.append(data.email_verified)
        if data.email_verified_at is not None:
            sets.append("email_verified_at = %s")
            params.append(data.email_verified_at)
        if data.totp_enabled is not None:
            sets.append("totp_enabled = %s")
            params.append(data.totp_enabled)

        if not sets:
            return self.find_by_id(user_id)

        sets.append("updated_at = now()")
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(sets)} WHERE id = %s RETURNING *;"
        with self._pool.connection() as conn:
            try:
                row = conn.execute(sql, tuple(params)).fetchone()
            except Exception as exc:
                map_pg_conflict(
                    exc,
                    unique_message="An account with this email already exists",
                    unique_code="EMAIL_ALREADY_EXISTS",
                )
                raise
            return _row_to_user(row) if row else None

    def update_role_safe(
        self, user_id: str, next_role: UserRole
    ) -> tuple[Optional[User], str]:
        with self._pool.connection() as conn:
            with conn.transaction():
                admin_rows = conn.execute(
                    "SELECT id FROM users WHERE role = 'admin' ORDER BY id FOR UPDATE;"
                ).fetchall()
                target_row = conn.execute(
                    "SELECT * FROM users WHERE id = %s FOR UPDATE;",
                    (user_id,),
                ).fetchone()
                if not target_row:
                    return None, "not_found"
                if (
                    target_row["role"] == "admin"
                    and next_role != "admin"
                    and len(admin_rows) <= 1
                ):
                    return None, "last_admin"
                if target_row["role"] == next_role:
                    return _row_to_user(target_row), "ok"
                updated = conn.execute(
                    "UPDATE users SET role = %s, updated_at = now() WHERE id = %s RETURNING *;",
                    (next_role, user_id),
                ).fetchone()
                assert updated is not None
                return _row_to_user(updated), "ok"

    def list(self, page: int, limit: int) -> tuple[list[User], int]:
        offset = (page - 1) * limit
        with self._pool.connection() as conn:
            count_row = conn.execute("SELECT COUNT(*) AS cnt FROM users;").fetchone()
            total = int(count_row["cnt"]) if count_row else 0
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s;",
                (limit, offset),
            ).fetchall()
            return [_row_to_user(r) for r in rows], total

    def save_password_reset_token(
        self, user_id: str, token_hash: str, expires_at: str
    ) -> PasswordResetToken:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                RETURNING *;
                """,
                (user_id, token_hash, expires_at),
            ).fetchone()
            assert row is not None
            return _row_to_reset_token(row)

    def find_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM password_reset_tokens WHERE token_hash = %s;",
                (token_hash,),
            ).fetchone()
            return _row_to_reset_token(row) if row else None

    def mark_password_reset_token_used(self, token_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = now() WHERE id = %s;",
                (token_id,),
            )

    def save_email_verification_token(
        self, user_id: str, token_hash: str, expires_at: str
    ) -> EmailVerificationToken:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                RETURNING *;
                """,
                (user_id, token_hash, expires_at),
            ).fetchone()
            assert row is not None
            return _row_to_verify_token(row)

    def find_email_verification_token_by_hash(
        self, token_hash: str
    ) -> Optional[EmailVerificationToken]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM email_verification_tokens WHERE token_hash = %s;",
                (token_hash,),
            ).fetchone()
            return _row_to_verify_token(row) if row else None

    def get_latest_email_verification_token(
        self, user_id: str
    ) -> Optional[EmailVerificationToken]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM email_verification_tokens
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                (user_id,),
            ).fetchone()
            return _row_to_verify_token(row) if row else None

    def mark_email_verification_token_used(self, token_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE email_verification_tokens SET used_at = now() WHERE id = %s;",
                (token_id,),
            )

    def invalidate_unused_email_verification_tokens(self, user_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE email_verification_tokens
                SET used_at = now()
                WHERE user_id = %s AND used_at IS NULL;
                """,
                (user_id,),
            )

    def delete_unused_tokens_for_user(self, user_id: str) -> None:
        with self._pool.connection() as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM email_verification_tokens WHERE user_id = %s AND used_at IS NULL;",
                    (user_id,),
                )
                conn.execute(
                    "DELETE FROM password_reset_tokens WHERE user_id = %s AND used_at IS NULL;",
                    (user_id,),
                )

    def cleanup_expired_tokens(self, batch_size: int = 1000) -> tuple[int, int]:
        total_v = 0
        total_r = 0
        with self._pool.connection() as conn:
            while True:
                with conn.transaction():
                    cur = conn.execute(
                        """
                        WITH doomed AS (
                            SELECT id FROM email_verification_tokens
                            WHERE expires_at < now() OR used_at IS NOT NULL
                            LIMIT %s
                        )
                        DELETE FROM email_verification_tokens
                        WHERE id IN (SELECT id FROM doomed)
                        RETURNING id;
                        """,
                        (batch_size,),
                    )
                    deleted = len(cur.fetchall())
                    total_v += deleted
                    if deleted < batch_size:
                        break

            while True:
                with conn.transaction():
                    cur = conn.execute(
                        """
                        WITH doomed AS (
                            SELECT id FROM password_reset_tokens
                            WHERE expires_at < now() OR used_at IS NOT NULL
                            LIMIT %s
                        )
                        DELETE FROM password_reset_tokens
                        WHERE id IN (SELECT id FROM doomed)
                        RETURNING id;
                        """,
                        (batch_size,),
                    )
                    deleted = len(cur.fetchall())
                    total_r += deleted
                    if deleted < batch_size:
                        break

        return total_v, total_r

    def list_admins(self) -> list[User]:
        with self._pool.connection() as conn:
            rows = conn.execute("SELECT * FROM users WHERE role = 'admin';").fetchall()
            return [_row_to_user(r) for r in rows]
