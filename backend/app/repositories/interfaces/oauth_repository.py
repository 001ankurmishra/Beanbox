from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.domain import OAuthAccount, OAuthProvider


@dataclass
class CreateOAuthAccountInput:
    user_id: str
    provider: OAuthProvider
    provider_user_id: str
    provider_email: str


class OAuthAccountRepository(ABC):
    @abstractmethod
    def find_by_provider_user(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> Optional[OAuthAccount]: ...

    @abstractmethod
    def list_for_user(self, user_id: str) -> list[OAuthAccount]: ...

    @abstractmethod
    def create(self, data: CreateOAuthAccountInput) -> OAuthAccount: ...
