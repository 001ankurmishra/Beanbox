from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import WishlistItem
from app.repositories.interfaces import WishlistRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryWishlistRepository(WishlistRepository):
    def __init__(self, initial_items: Optional[list[WishlistItem]] = None) -> None:
        self._lock = RLock()
        self._items: list[WishlistItem] = [
            i.model_copy(deep=True) for i in (initial_items or [])
        ]

    def list_by_user_id(self, user_id: str) -> list[WishlistItem]:
        with self._lock:
            filtered = [i for i in self._items if i.user_id == user_id]
            filtered.sort(key=lambda i: i.created_at, reverse=True)
            return [i.model_copy(deep=True) for i in filtered]

    def add(self, user_id: str, product_id: str) -> WishlistItem:
        with self._lock:
            for item in self._items:
                if item.user_id == user_id and item.product_id == product_id:
                    return item.model_copy(deep=True)
            created = WishlistItem(
                id=str(uuid4()),
                user_id=user_id,
                product_id=product_id,
                created_at=_now_iso(),
            )
            self._items.append(created.model_copy(deep=True))
            return created

    def remove(self, user_id: str, product_id: str) -> bool:
        with self._lock:
            before = len(self._items)
            self._items = [
                i
                for i in self._items
                if not (i.user_id == user_id and i.product_id == product_id)
            ]
            return len(self._items) < before

    def has_item(self, user_id: str, product_id: str) -> bool:
        with self._lock:
            return any(
                i.user_id == user_id and i.product_id == product_id for i in self._items
            )
