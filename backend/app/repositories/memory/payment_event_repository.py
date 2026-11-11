from datetime import datetime, timezone
from threading import RLock
from typing import Literal, Optional
from uuid import uuid4

from app.models.domain import PaymentEvent
from app.repositories.interfaces import PaymentEventRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryPaymentEventRepository(PaymentEventRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._events: list[PaymentEvent] = []

    def has_processed_event(self, event_id: str) -> bool:
        with self._lock:
            return any(e.event_id == event_id for e in self._events)

    def record_event(
        self,
        event_id: str,
        provider: Literal["stripe", "mock"],
        event_type: str,
        order_id: Optional[str] = None,
    ) -> PaymentEvent:
        event = PaymentEvent(
            id=str(uuid4()),
            event_id=event_id,
            provider=provider,
            event_type=event_type,
            order_id=order_id,
            processed_at=_now_iso(),
        )
        with self._lock:
            self._events.append(event.model_copy(deep=True))
        return event
