from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def create_pg_pool(dsn: str) -> ConnectionPool[Any]:
    return ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=10,
        max_idle=300,
        open=True,
        kwargs={
            "row_factory": dict_row,
            "prepare_threshold": None,
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
