from abc import ABC, abstractmethod

from app.models.domain import WishlistItem


class WishlistRepository(ABC):
    @abstractmethod
    def list_by_user_id(self, user_id: str) -> list[WishlistItem]: ...

    @abstractmethod
    def add(self, user_id: str, product_id: str) -> WishlistItem: ...

    @abstractmethod
    def remove(self, user_id: str, product_id: str) -> bool: ...

    @abstractmethod
    def has_item(self, user_id: str, product_id: str) -> bool: ...
