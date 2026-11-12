from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import OAuthAccount, OAuthProvider
from app.repositories.interfaces import CreateOAuthAccountInput, OAuthAccountRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryOAuthAccountRepository(OAuthAccountRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._accounts: list[OAuthAccount] = []

    def find_by_provider_user(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> Optional[OAuthAccount]:
        with self._lock:
            for acc in self._accounts:
                if (
                    acc.provider == provider
                    and acc.provider_user_id == provider_user_id
                ):
                    return acc.model_copy(deep=True)
            return None

    def list_for_user(self, user_id: str) -> list[OAuthAccount]:
        with self._lock:
            return [
                acc.model_copy(deep=True)
                for acc in self._accounts
                if acc.user_id == user_id
            ]

    def create(self, data: CreateOAuthAccountInput) -> OAuthAccount:
        now = _now_iso()
        acc = OAuthAccount(
            id=str(uuid4()),
            user_id=data.user_id,
            provider=data.provider,
            provider_user_id=data.provider_user_id,
            provider_email=data.provider_email.strip().lower(),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._accounts.append(acc.model_copy(deep=True))
        return acc
