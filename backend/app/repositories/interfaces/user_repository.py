from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from app.models.domain import EmailVerificationToken, PasswordResetToken, User, UserRole


@dataclass
class CreateUserInput:
    name: str
    email: str
    password_hash: str
    phone: Optional[str] = None
    role: UserRole = "customer"
    email_verified: bool = False
    email_verified_at: Optional[str] = None
    totp_enabled: bool = False


@dataclass
class UpdateUserInput:
    name: Optional[str] = None
    phone: Optional[str] = None
    password_hash: Optional[str] = None
    role: Optional[UserRole] = None
    email_verified: Optional[bool] = None
    email_verified_at: Optional[str] = None
    totp_enabled: Optional[bool] = None


class UserRepository(ABC):
    @abstractmethod
    def find_by_id(self, user_id: str) -> Optional[User]: ...

    @abstractmethod
    def find_by_email(self, email: str) -> Optional[User]: ...

    @abstractmethod
    def create(self, data: CreateUserInput) -> User: ...

    @abstractmethod
    def update(self, user_id: str, data: UpdateUserInput) -> Optional[User]: ...

    @abstractmethod
    def list(self, page: int, limit: int) -> tuple[list[User], int]: ...

    @abstractmethod
    def save_password_reset_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> PasswordResetToken: ...

    @abstractmethod
    def find_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]: ...

    @abstractmethod
    def mark_password_reset_token_used(self, token_id: str) -> None: ...

    @abstractmethod
    def save_email_verification_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> EmailVerificationToken: ...

    @abstractmethod
    def find_email_verification_token_by_hash(
        self, token_hash: str
    ) -> Optional[EmailVerificationToken]: ...

    @abstractmethod
    def get_latest_email_verification_token(
        self, user_id: str
    ) -> Optional[EmailVerificationToken]: ...

    @abstractmethod
    def mark_email_verification_token_used(self, token_id: str) -> None: ...

    @abstractmethod
    def invalidate_unused_email_verification_tokens(self, user_id: str) -> None: ...
