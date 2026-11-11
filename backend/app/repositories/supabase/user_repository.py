from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import PasswordResetToken, User
from app.repositories.interfaces import CreateUserInput, UpdateUserInput, UserRepository
from app.repositories.supabase.db import iso_str


def _row_to_user(row: dict[str, Any]) -> User:
    return User(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        password_hash=row["password_hash"],
        role=row["role"],
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
            row = conn.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.name.strip(),
                    data.email.strip().lower(),
                    data.phone.strip() if data.phone else None,
                    data.password_hash,
                    data.role,
                ),
            ).fetchone()
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

        if not sets:
            return self.find_by_id(user_id)

        sets.append("updated_at = now()")
        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(sets)} WHERE id = %s RETURNING *;"
        with self._pool.connection() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            return _row_to_user(row) if row else None

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
