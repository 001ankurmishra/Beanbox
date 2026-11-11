import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.config import Settings
from app.models.domain import PublicUser, User, UserRole
from app.repositories.interfaces import CreateUserInput, UpdateUserInput, UserRepository
from app.services.email_service import EmailService
from app.utils.errors import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)


def to_public_user(user: User) -> PublicUser:
    return PublicUser(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        email_service: EmailService,
        settings: Settings,
    ) -> None:
        self._user_repo = user_repo
        self._email_service = email_service
        self._settings = settings

    def sign_token(self, user: User) -> str:
        exp = datetime.now(timezone.utc) + timedelta(
            minutes=self._settings.jwt_expires_minutes
        )
        payload = {"sub": user.id, "role": user.role, "exp": exp}
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> tuple[str, UserRole]:
        try:
            decoded = jwt.decode(
                token, self._settings.jwt_secret, algorithms=["HS256"]
            )
            user_id = decoded.get("sub")
            role = decoded.get("role")
            if not user_id or role not in ("customer", "admin"):
                raise UnauthorizedError("Invalid authentication token")
            return str(user_id), role
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid or expired authentication token") from exc

    def signup(
        self,
        name: str,
        email: str,
        password: str,
        phone: Optional[str] = None,
    ) -> tuple[PublicUser, str]:
        existing = self._user_repo.find_by_email(email)
        if existing:
            raise ConflictError(
                "An account with this email already exists",
                code="EMAIL_ALREADY_EXISTS",
            )

        pw_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=10)
        ).decode("utf-8")
        created = self._user_repo.create(
            CreateUserInput(
                name=name,
                email=email,
                phone=phone,
                password_hash=pw_hash,
                role="customer",
            )
        )
        self._email_service.send_welcome(to=created.email, name=created.name)
        token = self.sign_token(created)
        return to_public_user(created), token

    def login(self, email: str, password: str) -> tuple[PublicUser, str]:
        user = self._user_repo.find_by_email(email)
        if not user:
            raise UnauthorizedError(
                "Invalid email or password", code="INVALID_CREDENTIALS"
            )

        if not bcrypt.checkpw(
            password.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            raise UnauthorizedError(
                "Invalid email or password", code="INVALID_CREDENTIALS"
            )

        token = self.sign_token(user)
        return to_public_user(user), token

    def get_me(self, user_id: str) -> PublicUser:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")
        return to_public_user(user)

    def update_profile(
        self,
        user_id: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> PublicUser:
        updated = self._user_repo.update(
            user_id, UpdateUserInput(name=name, phone=phone)
        )
        if not updated:
            raise NotFoundError("User not found")
        return to_public_user(updated)

    def forgot_password(self, email: str) -> dict[str, str]:
        user = self._user_repo.find_by_email(email)
        if user:
            raw_token = secrets.token_hex(32)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            expires_at = (
                (datetime.now(timezone.utc) + timedelta(minutes=15))
                .isoformat()
                .replace("+00:00", "Z")
            )
            self._user_repo.save_password_reset_token(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            reset_url = (
                f"{self._settings.frontend_url.rstrip('/')}/reset-password?token={raw_token}"
            )
            self._email_service.send_password_reset(
                to=user.email,
                name=user.name,
                reset_token=raw_token,
                reset_url=reset_url,
            )

        return {
            "message": "If an account exists with that email, a password reset link has been sent."
        }

    def reset_password(self, token: str, new_password: str) -> dict[str, str]:
        token_hash = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
        record = self._user_repo.find_password_reset_token_by_hash(token_hash)

        if not record or record.used_at:
            raise BadRequestError("Invalid or already used password reset token")

        exp_dt = datetime.fromisoformat(record.expires_at.replace("Z", "+00:00"))
        if exp_dt <= datetime.now(timezone.utc):
            raise BadRequestError("Password reset token has expired")

        pw_hash = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt(rounds=10)
        ).decode("utf-8")
        updated = self._user_repo.update(record.user_id, UpdateUserInput(password_hash=pw_hash))
        if not updated:
            raise NotFoundError("User not found")

        self._user_repo.mark_password_reset_token_used(record.id)
        return {"message": "Password has been reset successfully. You can now log in."}
