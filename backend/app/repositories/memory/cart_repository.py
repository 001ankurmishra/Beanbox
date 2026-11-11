from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import Cart, CartItem
from app.repositories.interfaces import CartRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryCartRepository(CartRepository):
    def __init__(self) -> None:
        self._lock = RLock()
        self._carts: list[Cart] = []

    def find_by_user_id(self, user_id: str) -> Optional[Cart]:
        with self._lock:
            for c in self._carts:
                if c.user_id == user_id:
                    return c.model_copy(deep=True)
            return None

    def find_by_session_id(self, session_id: str) -> Optional[Cart]:
        with self._lock:
            for c in self._carts:
                if c.session_id == session_id and not c.user_id:
                    return c.model_copy(deep=True)
            return None

    def upsert_for_user(self, user_id: str, items: list[CartItem]) -> Cart:
        now = _now_iso()
        with self._lock:
            for c in self._carts:
                if c.user_id == user_id:
                    c.items = [i.model_copy(deep=True) for i in items]
                    c.updated_at = now
                    return c.model_copy(deep=True)
            created = Cart(
                id=str(uuid4()),
                user_id=user_id,
                items=[i.model_copy(deep=True) for i in items],
                updated_at=now,
            )
            self._carts.append(created.model_copy(deep=True))
            return created

    def upsert_for_session(self, session_id: str, items: list[CartItem]) -> Cart:
        now = _now_iso()
        with self._lock:
            for c in self._carts:
                if c.session_id == session_id and not c.user_id:
                    c.items = [i.model_copy(deep=True) for i in items]
                    c.updated_at = now
                    return c.model_copy(deep=True)
            created = Cart(
                id=str(uuid4()),
                session_id=session_id,
                items=[i.model_copy(deep=True) for i in items],
                updated_at=now,
            )
            self._carts.append(created.model_copy(deep=True))
            return created

    def clear_for_user(self, user_id: str) -> None:
        with self._lock:
            for c in self._carts:
                if c.user_id == user_id:
                    c.items = []
                    c.updated_at = _now_iso()
                    return

    def clear_for_session(self, session_id: str) -> None:
        with self._lock:
            for c in self._carts:
                if c.session_id == session_id and not c.user_id:
                    c.items = []
                    c.updated_at = _now_iso()
                    return

    def delete_by_session_id(self, session_id: str) -> None:
        with self._lock:
            self._carts = [
                c for c in self._carts if not (c.session_id == session_id and not c.user_id)
            ]
