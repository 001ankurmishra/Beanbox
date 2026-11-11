from abc import ABC, abstractmethod
from typing import Literal, Optional

from app.models.domain import PaymentEvent


class PaymentEventRepository(ABC):
    @abstractmethod
    def has_processed_event(self, event_id: str) -> bool: ...

    @abstractmethod
    def record_event(
        self,
        event_id: str,
        provider: Literal["stripe", "mock"],
        event_type: str,
        order_id: Optional[str] = None,
    ) -> PaymentEvent: ...
