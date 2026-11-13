from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.domain import Session


@dataclass
class CreateSessionInput:
    user_id: str
    refresh_token_hash: str
    family_id: str
    user_agent: str
    ip: str
    expires_at: str


class SessionRepository(ABC):
    @abstractmethod
    def create(self, data: CreateSessionInput) -> Session: ...

    @abstractmethod
    def find_by_id(self, session_id: str) -> Optional[Session]: ...

    @abstractmethod
    def find_by_refresh_hash(self, token_hash: str) -> Optional[Session]: ...

    @abstractmethod
    def find_by_grace_refresh_hash(self, token_hash: str) -> Optional[Session]: ...

    @abstractmethod
    def find_by_previous_refresh_hash(self, token_hash: str) -> Optional[Session]: ...

    @abstractmethod
    def rotate_refresh_token(
        self,
        session_id: str,
        expected_hash: str,
        new_hash: str,
        new_expires_at: str,
        ip: str,
        user_agent: str,
        grace_expires_at: Optional[str] = None,
        max_history: int = 100,
    ) -> Optional[Session]: ...

    @abstractmethod
    def consume_grace_refresh_token(
        self, session_id: str, token_hash: str
    ) -> Optional[Session]: ...

    @abstractmethod
    def check_device_history(
        self, user_id: str, user_agent: str
    ) -> tuple[bool, bool]: ...

    @abstractmethod
    def touch_last_used(
        self, session_id: str, ip: str, user_agent: str
    ) -> None: ...

    @abstractmethod
    def list_active_for_user(self, user_id: str) -> list[Session]: ...

    @abstractmethod
    def list_ids_by_family(self, family_id: str) -> list[str]: ...

    @abstractmethod
    def revoke_by_id(self, session_id: str, user_id: str) -> bool: ...

    @abstractmethod
    def revoke_family(self, family_id: str) -> int: ...

    @abstractmethod
    def revoke_all_for_user(
        self, user_id: str, except_session_id: Optional[str] = None
    ) -> int: ...

    @abstractmethod
    def cleanup_expired_sessions(
        self, older_than_days: int = 30, batch_size: int = 1000
    ) -> int: ...
