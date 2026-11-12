from abc import ABC, abstractmethod
from typing import Optional

from app.models.domain import Address, AddressLabel, CamelModel


class CreateAddressInput(CamelModel):
    user_id: str
    label: AddressLabel = "Home"
    full_name: str
    phone: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    is_default: bool = False


class UpdateAddressInput(CamelModel):
    label: Optional[AddressLabel] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    is_default: Optional[bool] = None


class AddressRepository(ABC):
    @abstractmethod
    def list_by_user_id(self, user_id: str) -> list[Address]: ...

    @abstractmethod
    def find_by_id(self, address_id: str) -> Optional[Address]: ...

    @abstractmethod
    def find_by_id_for_user(
        self, address_id: str, user_id: str
    ) -> Optional[Address]: ...

    @abstractmethod
    def create(self, data: CreateAddressInput) -> Address: ...

    @abstractmethod
    def update(
        self, address_id: str, user_id: str, data: UpdateAddressInput
    ) -> Optional[Address]: ...

    @abstractmethod
    def delete(self, address_id: str, user_id: str) -> bool: ...

    @abstractmethod
    def set_default(self, address_id: str, user_id: str) -> Optional[Address]: ...
