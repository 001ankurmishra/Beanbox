from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import AuditLogEntry
from app.repositories.interfaces import AuditLogRepository, CreateAuditLogInput


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._logs: list[AuditLogEntry] = []

    def create(self, data: CreateAuditLogInput) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=str(uuid4()),
            user_id=data.user_id,
            event_type=data.event_type,
            outcome=data.outcome,
            target_id=data.target_id,
            ip=data.ip,
            user_agent=data.user_agent,
            request_id=data.request_id,
            metadata=dict(data.metadata or {}),
            created_at=_now_iso(),
        )
        with self._lock:
            self._logs.append(entry.model_copy(deep=True))
        return entry

    def list(
        self,
        page: int = 1,
        limit: int = 25,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> tuple[list[AuditLogEntry], int]:
        with self._lock:
            filtered = list(reversed(self._logs))
            if event_type:
                filtered = [e for e in filtered if e.event_type == event_type]
            if user_id:
                filtered = [e for e in filtered if e.user_id == user_id]
            total = len(filtered)
            start = (page - 1) * limit
            return [e.model_copy(deep=True) for e in filtered[start : start + limit]], total
