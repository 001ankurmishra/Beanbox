from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import LoginAttemptKeyType, LoginAttemptRecord


class LoginAttemptRepository(ABC):
    @abstractmethod
    def get_by_key(self, key: str) -> Optional[LoginAttemptRecord]: ...

    @abstractmethod
    def record_failure(
        self,
        key: str,
        key_type: LoginAttemptKeyType,
        max_failures: int = 5,
        base_lock_minutes: int = 15,
        failure_window_minutes: int = 15,
    ) -> LoginAttemptRecord: ...

    @abstractmethod
    def reset(self, key: str) -> None: ...
