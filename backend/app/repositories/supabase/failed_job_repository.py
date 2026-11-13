from __future__ import annotations

import json
from typing import Any, Optional

from psycopg_pool import ConnectionPool

from app.models.domain import FailedJob
from app.repositories.interfaces.failed_job_repository import (
    CreateFailedJobInput,
    FailedJobRepository,
)
from app.repositories.supabase.db import iso_str


def _row_to_failed_job(row: dict[str, Any]) -> FailedJob:
    args_json = row["args_json"]
    if isinstance(args_json, str):
        try:
            args_json = json.loads(args_json)
        except Exception:
            pass
    return FailedJob(
        id=str(row["id"]),
        task_name=row["task_name"],
        args_json=args_json,
        error_message=row["error_message"],
        traceback=row["traceback"],
        attempts=row["attempts"],
        queue=row["queue"],
        created_at=iso_str(row["created_at"]) or "",
        resolved_at=iso_str(row.get("resolved_at")),
    )


class SupabaseFailedJobRepository(FailedJobRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def create(self, data: CreateFailedJobInput) -> FailedJob:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO failed_jobs (
                    task_name, args_json, error_message, traceback, attempts, queue
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING *;
                """,
                (
                    data.task_name,
                    json.dumps(data.args_json),
                    data.error_message,
                    data.traceback[:4096],
                    data.attempts,
                    data.queue,
                ),
            ).fetchone()
            assert row is not None
            return _row_to_failed_job(row)

    def list_all(self, limit: int = 50) -> list[FailedJob]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM failed_jobs ORDER BY created_at DESC LIMIT %s;",
                (limit,),
            ).fetchall()
            return [_row_to_failed_job(r) for r in rows]

    def find_by_id(self, job_id: str) -> Optional[FailedJob]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM failed_jobs WHERE id = %s;", (job_id,)
            ).fetchone()
            return _row_to_failed_job(row) if row else None

    def mark_resolved(self, job_id: str) -> Optional[FailedJob]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                UPDATE failed_jobs
                SET resolved_at = now()
                WHERE id = %s
                RETURNING *;
                """,
                (job_id,),
            ).fetchone()
            return _row_to_failed_job(row) if row else None
