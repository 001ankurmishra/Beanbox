from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import Address
from app.repositories.interfaces import (
    AddressRepository,
    CreateAddressInput,
    UpdateAddressInput,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryAddressRepository(AddressRepository):
    def __init__(self, initial_addresses: Optional[list[Address]] = None) -> None:
        self._lock = RLock()
        self._addresses: list[Address] = [
            a.model_copy(deep=True) for a in (initial_addresses or [])
        ]

    def list_by_user_id(self, user_id: str) -> list[Address]:
        with self._lock:
            filtered = [a for a in self._addresses if a.user_id == user_id]
            filtered.sort(key=lambda a: int(a.is_default), reverse=True)
            return [a.model_copy(deep=True) for a in filtered]

    def find_by_id(self, address_id: str) -> Optional[Address]:
        with self._lock:
            for a in self._addresses:
                if a.id == address_id:
                    return a.model_copy(deep=True)
            return None

    def find_by_id_for_user(
        self, address_id: str, user_id: str
    ) -> Optional[Address]:
        with self._lock:
            for a in self._addresses:
                if a.id == address_id and a.user_id == user_id:
                    return a.model_copy(deep=True)
            return None

    def create(self, data: CreateAddressInput) -> Address:
        now = _now_iso()
        with self._lock:
            user_addrs = [a for a in self._addresses if a.user_id == data.user_id]
            should_default = data.is_default or len(user_addrs) == 0
            if should_default:
                for addr in user_addrs:
                    addr.is_default = False

            address = Address(
                id=str(uuid4()),
                user_id=data.user_id,
                label=data.label,
                full_name=data.full_name.strip(),
                phone=data.phone.strip(),
                line1=data.line1.strip(),
                line2=data.line2.strip() if data.line2 else None,
                city=data.city.strip(),
                state=data.state.strip(),
                postal_code=data.postal_code.strip(),
                country="India",
                is_default=should_default,
                created_at=now,
                updated_at=now,
            )
            self._addresses.append(address.model_copy(deep=True))
            return address

    def update(
        self, address_id: str, user_id: str, data: UpdateAddressInput
    ) -> Optional[Address]:
        with self._lock:
            target_idx = -1
            for idx, addr in enumerate(self._addresses):
                if addr.id == address_id and addr.user_id == user_id:
                    target_idx = idx
                    break
            if target_idx == -1:
                return None

            if data.is_default:
                for addr in self._addresses:
                    if addr.user_id == user_id:
                        addr.is_default = False

            updated = self._addresses[target_idx].model_copy(deep=True)
            for k, val in data.model_dump(exclude_unset=True).items():
                setattr(updated, k, val)
            updated.updated_at = _now_iso()
            self._addresses[target_idx] = updated.model_copy(deep=True)
            return updated

    def delete(self, address_id: str, user_id: str) -> bool:
        with self._lock:
            target = next(
                (a for a in self._addresses if a.id == address_id and a.user_id == user_id),
                None,
            )
            if not target:
                return False

            self._addresses = [a for a in self._addresses if a.id != address_id]
            if target.is_default:
                for addr in self._addresses:
                    if addr.user_id == user_id:
                        addr.is_default = True
                        addr.updated_at = _now_iso()
                        break
            return True

    def set_default(self, address_id: str, user_id: str) -> Optional[Address]:
        with self._lock:
            target = next(
                (a for a in self._addresses if a.id == address_id and a.user_id == user_id),
                None,
            )
            if not target:
                return None

            now = _now_iso()
            for addr in self._addresses:
                if addr.user_id == user_id:
                    addr.is_default = addr.id == address_id
                    addr.updated_at = now
            return target.model_copy(deep=True)
