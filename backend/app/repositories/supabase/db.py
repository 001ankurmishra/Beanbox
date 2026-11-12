from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.utils.errors import ConflictError


def map_pg_conflict(
    exc: Exception,
    unique_message: str = "Resource already exists",
    unique_code: str = "CONFLICT",
    fk_message: str = "Resource is referenced by existing records",
    fk_code: str = "RESOURCE_IN_USE",
) -> None:
    if isinstance(exc, pg_errors.UniqueViolation):
        raise ConflictError(unique_message, code=unique_code) from exc
    if isinstance(exc, pg_errors.ForeignKeyViolation):
        raise ConflictError(fk_message, code=fk_code) from exc


def create_pg_pool(dsn: str) -> ConnectionPool[Any]:
    return ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=10,
        max_idle=300,
        timeout=10.0,
        open=True,
        kwargs={
            "row_factory": dict_row,
            "prepare_threshold": None,
            "connect_timeout": 5,
            "options": "-c statement_timeout=10000",
        },
    )


def iso_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)
