from __future__ import annotations

from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import Address
from app.repositories.interfaces import (
    AddressRepository,
    CreateAddressInput,
    UpdateAddressInput,
)
from app.repositories.supabase.db import iso_str


def _row_to_address(row: dict[str, Any]) -> Address:
    return Address(
        id=row["id"],
        user_id=row["user_id"],
        label=row["label"],
        full_name=row["full_name"],
        phone=row["phone"],
        line1=row["line1"],
        line2=row["line2"],
        city=row["city"],
        state=row["state"],
        postal_code=row["postal_code"],
        country="India",
        is_default=bool(row["is_default"]),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


class SupabaseAddressRepository(AddressRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def list_by_user_id(self, user_id: str) -> list[Address]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM addresses
                WHERE user_id = %s
                ORDER BY is_default DESC, created_at DESC;
                """,
                (user_id,),
            ).fetchall()
            return [_row_to_address(r) for r in rows]

    def find_by_id(self, address_id: str) -> Optional[Address]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM addresses WHERE id = %s;", (address_id,)
            ).fetchone()
            return _row_to_address(row) if row else None

    def create(self, data: CreateAddressInput) -> Address:
        with self._pool.connection() as conn:
            with conn.transaction():
                cnt_row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM addresses WHERE user_id = %s;",
                    (data.user_id,),
                ).fetchone()
                should_default = data.is_default or (
                    int(cnt_row["cnt"]) == 0 if cnt_row else True
                )
                if should_default:
                    conn.execute(
                        "UPDATE addresses SET is_default = false WHERE user_id = %s;",
                        (data.user_id,),
                    )

                row = conn.execute(
                    """
                    INSERT INTO addresses (
                      user_id, label, full_name, phone, line1, line2,
                      city, state, postal_code, country, is_default
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'India', %s)
                    RETURNING *;
                    """,
                    (
                        data.user_id,
                        data.label,
                        data.full_name.strip(),
                        data.phone.strip(),
                        data.line1.strip(),
                        data.line2.strip() if data.line2 else None,
                        data.city.strip(),
                        data.state.strip(),
                        data.postal_code.strip(),
                        should_default,
                    ),
                ).fetchone()
                assert row is not None
                return _row_to_address(row)

    def update(
        self, address_id: str, user_id: str, data: UpdateAddressInput
    ) -> Optional[Address]:
        patch = data.model_dump(exclude_unset=True)
        with self._pool.connection() as conn:
            with conn.transaction():
                existing = conn.execute(
                    "SELECT * FROM addresses WHERE id = %s AND user_id = %s;",
                    (address_id, user_id),
                ).fetchone()
                if not existing:
                    return None

                if patch.get("is_default"):
                    conn.execute(
                        "UPDATE addresses SET is_default = false WHERE user_id = %s;",
                        (user_id,),
                    )

                if not patch:
                    return _row_to_address(existing)

                sets = [f"{k} = %s" for k in patch.keys()]
                sets.append("updated_at = now()")
                params = [*patch.values(), address_id, user_id]
                row = conn.execute(
                    f"UPDATE addresses SET {', '.join(sets)} WHERE id = %s AND user_id = %s RETURNING *;",
                    tuple(params),
                ).fetchone()
                return _row_to_address(row) if row else None

    def delete(self, address_id: str, user_id: str) -> bool:
        with self._pool.connection() as conn:
            with conn.transaction():
                target = conn.execute(
                    "SELECT is_default FROM addresses WHERE id = %s AND user_id = %s;",
                    (address_id, user_id),
                ).fetchone()
                if not target:
                    return False

                conn.execute(
                    "DELETE FROM addresses WHERE id = %s AND user_id = %s;",
                    (address_id, user_id),
                )
                if target["is_default"]:
                    next_addr = conn.execute(
                        "SELECT id FROM addresses WHERE user_id = %s ORDER BY created_at ASC LIMIT 1;",
                        (user_id,),
                    ).fetchone()
                    if next_addr:
                        conn.execute(
                            "UPDATE addresses SET is_default = true, updated_at = now() WHERE id = %s;",
                            (next_addr["id"],),
                        )
                return True

    def set_default(self, address_id: str, user_id: str) -> Optional[Address]:
        with self._pool.connection() as conn:
            with conn.transaction():
                existing = conn.execute(
                    "SELECT id FROM addresses WHERE id = %s AND user_id = %s;",
                    (address_id, user_id),
                ).fetchone()
                if not existing:
                    return None
                conn.execute(
                    "UPDATE addresses SET is_default = (id = %s), updated_at = now() WHERE user_id = %s;",
                    (address_id, user_id),
                )
                row = conn.execute(
                    "SELECT * FROM addresses WHERE id = %s;", (address_id,)
                ).fetchone()
                return _row_to_address(row) if row else None
