import re
from typing import Optional

from pydantic import EmailStr, Field, field_validator

from app.models.domain import CamelModel

INDIAN_PHONE_RE = re.compile(r"^(\+91[\-\s]?)?[6-9]\d{9}$")


def _clean_optional_phone(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    stripped = v.strip()
    if not stripped:
        return None
    if not INDIAN_PHONE_RE.match(stripped):
        raise ValueError("Enter a valid 10-digit Indian mobile number")
    return stripped


class SignupRequest(CamelModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    phone: Optional[str] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def norm_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_phone(v)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def norm_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()


class UpdateProfileRequest(CamelModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    phone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_phone(v)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class VerifyEmailRequest(CamelModel):
    token: str = Field(min_length=16, max_length=256)


class ForgotPasswordRequest(CamelModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def norm_email(cls, v: EmailStr) -> str:
        return str(v).strip().lower()


class ResetPasswordRequest(CamelModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=10, max_length=128)


class TotpCodeRequest(CamelModel):
    code: str = Field(min_length=6, max_length=32)


class Verify2faLoginRequest(CamelModel):
    challenge_token: str = Field(min_length=16, max_length=2000)
    code: str = Field(min_length=6, max_length=32)


class Disable2faRequest(CamelModel):
    code: str = Field(min_length=6, max_length=32)
    password: Optional[str] = Field(default=None, max_length=128)
