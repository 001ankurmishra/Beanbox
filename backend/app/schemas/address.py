import re
from typing import Optional

from pydantic import Field, field_validator

from app.models.domain import AddressLabel, CamelModel

INDIAN_PHONE_RE = re.compile(r"^(\+91[\-\s]?)?[6-9]\d{9}$")
INDIAN_PIN_RE = re.compile(r"^[1-9][0-9]{5}$")


class CreateAddressRequest(CamelModel):
    label: AddressLabel = "Home"
    full_name: str = Field(min_length=2, max_length=80)
    phone: str
    line1: str = Field(min_length=4, max_length=150)
    line2: Optional[str] = Field(default=None, max_length=150)
    city: str = Field(min_length=2, max_length=60)
    state: str = Field(min_length=2, max_length=60)
    postal_code: str
    is_default: bool = False

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: str) -> str:
        s = v.strip()
        if not INDIAN_PHONE_RE.match(s):
            raise ValueError("Valid 10-digit Indian mobile number required")
        return s

    @field_validator("postal_code")
    @classmethod
    def check_pin(cls, v: str) -> str:
        s = v.strip()
        if not INDIAN_PIN_RE.match(s):
            raise ValueError("Valid 6-digit Indian PIN code required")
        return s


class UpdateAddressRequest(CamelModel):
    label: Optional[AddressLabel] = None
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    phone: Optional[str] = None
    line1: Optional[str] = Field(default=None, min_length=4, max_length=150)
    line2: Optional[str] = Field(default=None, max_length=150)
    city: Optional[str] = Field(default=None, min_length=2, max_length=60)
    state: Optional[str] = Field(default=None, min_length=2, max_length=60)
    postal_code: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def check_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not INDIAN_PHONE_RE.match(s):
            raise ValueError("Valid 10-digit Indian mobile number required")
        return s

    @field_validator("postal_code")
    @classmethod
    def check_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not INDIAN_PIN_RE.match(s):
            raise ValueError("Valid 6-digit Indian PIN code required")
        return s
