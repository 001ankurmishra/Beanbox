from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

from app.models.domain import EmailVerificationToken, PasswordResetToken, User, UserRole
from app.repositories.interfaces import CreateUserInput, UpdateUserInput, UserRepository
from app.utils.errors import ConflictError


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
        norm_email = data.email.strip().lower()
        with self._lock:
            if any(u.email.lower() == norm_email for u in self._users):
                raise ConflictError(
                    "An account with this email already exists",
                    code="EMAIL_ALREADY_EXISTS",
                )
            user = User(
                id=str(uuid4()),
                name=data.name.strip(),
                email=norm_email,
                phone=data.phone.strip() if data.phone else None,
                password_hash=data.password_hash,
                role=data.role,
                email_verified=data.email_verified,
                email_verified_at=data.email_verified_at,
                totp_enabled=data.totp_enabled,
                created_at=now,
                updated_at=now,
            )
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

    def update_role_safe(
        self, user_id: str, next_role: UserRole
    ) -> tuple[Optional[User], str]:
        with self._lock:
            target_idx: Optional[int] = None
            target: Optional[User] = None
            admin_count = 0
            for idx, existing in enumerate(self._users):
                if existing.role == "admin":
                    admin_count += 1
                if existing.id == user_id:
                    target_idx = idx
                    target = existing
            if target is None or target_idx is None:
                return None, "not_found"
            if target.role == "admin" and next_role != "admin" and admin_count <= 1:
                return None, "last_admin"
            if target.role == next_role:
                return target.model_copy(deep=True), "ok"
            updated = target.model_copy(deep=True)
            updated.role = next_role
            updated.updated_at = _now_iso()
            self._users[target_idx] = updated.model_copy(deep=True)
            return updated, "ok"

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

    def delete_unused_tokens_for_user(self, user_id: str) -> None:
        with self._lock:
            self._verify_tokens = [
                t
                for t in self._verify_tokens
                if not (t.user_id == user_id and t.used_at is None)
            ]
            self._reset_tokens = [
                t
                for t in self._reset_tokens
                if not (t.user_id == user_id and t.used_at is None)
            ]

    def cleanup_expired_tokens(self, batch_size: int = 1000) -> tuple[int, int]:
        now = _now_iso()
        with self._lock:
            initial_v = len(self._verify_tokens)
            self._verify_tokens = [
                t
                for t in self._verify_tokens
                if not (t.expires_at < now or t.used_at is not None)
            ]
            v_deleted = initial_v - len(self._verify_tokens)

            initial_r = len(self._reset_tokens)
            self._reset_tokens = [
                t
                for t in self._reset_tokens
                if not (t.expires_at < now or t.used_at is not None)
            ]
            r_deleted = initial_r - len(self._reset_tokens)
            return v_deleted, r_deleted

    def list_admins(self) -> list[User]:
        with self._lock:
            return [u.model_copy(deep=True) for u in self._users if u.role == "admin"]
