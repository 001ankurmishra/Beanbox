from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from app.models.domain import AuditLogEntry, AuditOutcome


@dataclass
class CreateAuditLogInput:
    event_type: str
    outcome: AuditOutcome
    ip: str
    user_agent: str
    request_id: str
    user_id: Optional[str] = None
    target_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogRepository(ABC):
    @abstractmethod
    def create(self, data: CreateAuditLogInput) -> AuditLogEntry: ...

    @abstractmethod
    def list(
        self,
        page: int = 1,
        limit: int = 25,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> tuple[list[AuditLogEntry], int]: ...
