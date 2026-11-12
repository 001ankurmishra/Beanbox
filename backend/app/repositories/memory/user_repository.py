from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import EmailVerificationToken, PasswordResetToken, User
from app.repositories.interfaces import CreateUserInput, UpdateUserInput, UserRepository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class InMemoryUserRepository(UserRepository):
    def __init__(self, initial_users: Optional[list[User]] = None) -> None:
        self._lock = RLock()
        self._users: list[User] = [u.model_copy(deep=True) for u in (initial_users or [])]
        self._reset_tokens: list[PasswordResetToken] = []
        self._verify_tokens: list[EmailVerificationToken] = []

    def find_by_id(self, user_id: str) -> Optional[User]:
        with self._lock:
            for u in self._users:
                if u.id == user_id:
                    return u.model_copy(deep=True)
            return None

    def find_by_email(self, email: str) -> Optional[User]:
        normalized = email.strip().lower()
        with self._lock:
            for u in self._users:
                if u.email.lower() == normalized:
                    return u.model_copy(deep=True)
            return None

    def create(self, data: CreateUserInput) -> User:
        now = _now_iso()
        user = User(
            id=str(uuid4()),
            name=data.name.strip(),
            email=data.email.strip().lower(),
            phone=data.phone.strip() if data.phone else None,
            password_hash=data.password_hash,
            role=data.role,
            email_verified=data.email_verified,
            email_verified_at=data.email_verified_at,
            totp_enabled=data.totp_enabled,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._users.append(user.model_copy(deep=True))
        return user

    def update(self, user_id: str, data: UpdateUserInput) -> Optional[User]:
        with self._lock:
            for idx, existing in enumerate(self._users):
                if existing.id == user_id:
                    updated = existing.model_copy(deep=True)
                    if data.name is not None:
                        updated.name = data.name.strip()
                    if data.phone is not None:
                        updated.phone = data.phone.strip()
                    if data.password_hash is not None:
                        updated.password_hash = data.password_hash
                    if data.role is not None:
                        updated.role = data.role
                    if data.email_verified is not None:
                        updated.email_verified = data.email_verified
                    if data.email_verified_at is not None:
                        updated.email_verified_at = data.email_verified_at
                    if data.totp_enabled is not None:
                        updated.totp_enabled = data.totp_enabled
                    updated.updated_at = _now_iso()
                    self._users[idx] = updated.model_copy(deep=True)
                    return updated
            return None

    def list(self, page: int, limit: int) -> tuple[list[User], int]:
        with self._lock:
            sorted_users = sorted(
                self._users,
                key=lambda u: u.created_at,
                reverse=True,
            )
            total = len(sorted_users)
            start = (page - 1) * limit
            items = [u.model_copy(deep=True) for u in sorted_users[start : start + limit]]
            return items, total

    def save_password_reset_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> PasswordResetToken:
        record = PasswordResetToken(
            id=str(uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=_now_iso(),
        )
        with self._lock:
            self._reset_tokens.append(record.model_copy(deep=True))
        return record

    def find_password_reset_token_by_hash(
        self, token_hash: str
    ) -> Optional[PasswordResetToken]:
        with self._lock:
            for t in self._reset_tokens:
                if t.token_hash == token_hash:
                    return t.model_copy(deep=True)
            return None

    def mark_password_reset_token_used(self, token_id: str) -> None:
        with self._lock:
            for t in self._reset_tokens:
                if t.id == token_id:
                    t.used_at = _now_iso()
                    return

    def save_email_verification_token(
        self,
        user_id: str,
        token_hash: str,
        expires_at: str,
    ) -> EmailVerificationToken:
        record = EmailVerificationToken(
            id=str(uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=_now_iso(),
        )
        with self._lock:
            self._verify_tokens.append(record.model_copy(deep=True))
        return record

    def find_email_verification_token_by_hash(
        self, token_hash: str
    ) -> Optional[EmailVerificationToken]:
        with self._lock:
            for t in self._verify_tokens:
                if t.token_hash == token_hash:
                    return t.model_copy(deep=True)
            return None

    def get_latest_email_verification_token(
        self, user_id: str
    ) -> Optional[EmailVerificationToken]:
        with self._lock:
            matching = [t for t in self._verify_tokens if t.user_id == user_id]
            if not matching:
                return None
            return matching[-1].model_copy(deep=True)

    def mark_email_verification_token_used(self, token_id: str) -> None:
        with self._lock:
            for t in self._verify_tokens:
                if t.id == token_id:
                    t.used_at = _now_iso()
                    return

    def invalidate_unused_email_verification_tokens(self, user_id: str) -> None:
        now = _now_iso()
        with self._lock:
            for t in self._verify_tokens:
                if t.user_id == user_id and t.used_at is None:
                    t.used_at = now
