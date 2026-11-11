from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import Cart, CartItem


class CartRepository(ABC):
    @abstractmethod
    def find_by_user_id(self, user_id: str) -> Optional[Cart]: ...

    @abstractmethod
    def find_by_session_id(self, session_id: str) -> Optional[Cart]: ...

    @abstractmethod
    def upsert_for_user(self, user_id: str, items: list[CartItem]) -> Cart: ...

    @abstractmethod
    def upsert_for_session(self, session_id: str, items: list[CartItem]) -> Cart: ...

    @abstractmethod
    def clear_for_user(self, user_id: str) -> None: ...

    @abstractmethod
    def clear_for_session(self, session_id: str) -> None: ...

    @abstractmethod
    def delete_by_session_id(self, session_id: str) -> None: ...
