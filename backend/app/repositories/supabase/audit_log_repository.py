from __future__ import annotations

import json
from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import AuditLogEntry
from app.repositories.interfaces import AuditLogRepository, CreateAuditLogInput
from app.repositories.supabase.db import iso_str


def _row_to_audit(row: dict[str, Any]) -> AuditLogEntry:
    return AuditLogEntry(
        id=row["id"],
        user_id=row.get("user_id"),
        event_type=row["event_type"],
        outcome=row["outcome"],
        target_id=row.get("target_id"),
        ip=row["ip"],
        user_agent=row["user_agent"],
        request_id=row["request_id"],
        metadata=dict(row.get("metadata") or {}),
        created_at=iso_str(row["created_at"]) or "",
    )


class SupabaseAuditLogRepository(AuditLogRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def create(self, data: CreateAuditLogInput) -> AuditLogEntry:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO audit_logs (
                    user_id, event_type, outcome, target_id,
                    ip, user_agent, request_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING *;
                """,
                (
                    data.user_id,
                    data.event_type,
                    data.outcome,
                    data.target_id,
                    data.ip,
                    data.user_agent,
                    data.request_id,
                    json.dumps(data.metadata or {}),
                ),
            ).fetchone()
            assert row is not None
            return _row_to_audit(row)

    def list(
        self,
        page: int = 1,
        limit: int = 25,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> tuple[list[AuditLogEntry], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if user_id:
            clauses.append("user_id = %s")
            params.append(user_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = (page - 1) * limit

        with self._pool.connection() as conn:
            cnt_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM audit_logs {where_sql};",
                tuple(params),
            ).fetchone()
            total = int(cnt_row["cnt"]) if cnt_row else 0

            rows = conn.execute(
                f"""
                SELECT * FROM audit_logs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
                """,
                (*params, limit, offset),
            ).fetchall()
            return [_row_to_audit(r) for r in rows], total
