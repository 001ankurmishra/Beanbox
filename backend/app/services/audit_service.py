from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from app.models.domain import AuditLogEntry, AuditOutcome
from app.repositories.interfaces import AuditLogRepository, CreateAuditLogInput
from app.schemas.common import PaginationMeta

REDACTED_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "totp_secret",
        "recovery_code",
        "code",
        "client_secret",
        "code_verifier",
    }
)


@dataclass
class RequestContext:
    ip: str = "unknown"
    user_agent: str = "unknown"
    request_id: str = "internal"


def _sanitize_metadata(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not raw:
        return {}
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k.lower() in REDACTED_KEYS:
            clean[k] = "[REDACTED]"
        else:
            clean[k] = v
    return clean


class AuditService:
    def __init__(self, repo: AuditLogRepository) -> None:
        self._repo = repo

    def record(
        self,
        event_type: str,
        outcome: AuditOutcome,
        ctx: Optional[RequestContext] = None,
        user_id: Optional[str] = None,
        target_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AuditLogEntry:
        req_ctx = ctx or RequestContext()
        return self._repo.create(
            CreateAuditLogInput(
                user_id=user_id,
                event_type=event_type,
                outcome=outcome,
                target_id=target_id,
                ip=req_ctx.ip,
                user_agent=req_ctx.user_agent,
                request_id=req_ctx.request_id,
                metadata=_sanitize_metadata(metadata),
            )
        )

    def list_logs(
        self,
        page: int = 1,
        limit: int = 25,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        items, total = self._repo.list(
            page=page, limit=limit, event_type=event_type, user_id=user_id
        )
        total_pages = max(1, math.ceil(total / limit))
        return {
            "items": items,
            "pagination": PaginationMeta(
                page=page,
                limit=limit,
                total_items=total,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1,
            ),
        }
