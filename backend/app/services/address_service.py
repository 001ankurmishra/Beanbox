from app.models.domain import Address
from app.repositories.interfaces import (
    AddressRepository,
    CreateAddressInput,
    UpdateAddressInput,
)
from app.utils.errors import NotFoundError


class AddressService:
    def __init__(self, address_repo: AddressRepository) -> None:
        self._address_repo = address_repo

    def list(self, user_id: str) -> list[Address]:
        return self._address_repo.list_by_user_id(user_id)

    def create(self, data: CreateAddressInput) -> Address:
        return self._address_repo.create(data)

    def update(
        self, address_id: str, user_id: str, data: UpdateAddressInput
    ) -> Address:
        updated = self._address_repo.update(address_id, user_id, data)
        if not updated:
            raise NotFoundError("Address not found")
        return updated

    def remove(self, address_id: str, user_id: str) -> None:
        deleted = self._address_repo.delete(address_id, user_id)
        if not deleted:
            raise NotFoundError("Address not found")

    def set_default(self, address_id: str, user_id: str) -> Address:
        updated = self._address_repo.set_default(address_id, user_id)
        if not updated:
            raise NotFoundError("Address not found")
        return updated
