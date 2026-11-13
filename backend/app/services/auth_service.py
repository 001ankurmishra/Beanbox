from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Union
from uuid import uuid4

import jwt
import pyotp

from app.cache.interfaces import SessionCache
from app.cache.session_cache import NoopSessionCache
from app.config import Settings
from app.models.domain import PublicSession, PublicUser, User, UserRole
from app.repositories.interfaces import (
    CreateOAuthAccountInput,
    CreateSessionInput,
    CreateUserInput,
    LoginAttemptRepository,
    OAuthAccountRepository,
    Repositories,
    SessionRepository,
    TwoFactorRepository,
    UpdateUserInput,
    UserRepository,
)
from app.services.audit_service import AuditService, RequestContext
from app.services.email_service import EmailService
from app.services.google_oauth_service import GoogleOAuthClient, pkce_code_challenge
from app.utils.errors import (
    AppError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    TooManyRequestsError,
    UnauthorizedError,
)
from app.utils.security import (
    decrypt_secret,
    dummy_password_work,
    encrypt_secret,
    generate_opaque_token,
    generate_recovery_codes,
    generate_totp_qr_data_url,
    hash_password_argon2,
    hmac_sha256_hex,
    normalize_recovery_code,
    sanitize_next_path,
    sha256_hex,
    validate_password_policy,
    verify_password_constant_time,
)
from app.worker.tasks_email import enqueue_email

EMAIL_VERIFICATION_TTL_HOURS = 24
EMAIL_RESEND_COOLDOWN_SECONDS = 60
PASSWORD_RESET_TTL_MINUTES = 15
TWO_FACTOR_CHALLENGE_TTL_MINUTES = 5
RECOVERY_CODE_COUNT = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def to_public_user(user: User) -> PublicUser:
    return PublicUser(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        email_verified=user.email_verified,
        email_verified_at=user.email_verified_at,
        totp_enabled=user.totp_enabled,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@dataclass
class AccessTokenClaims:
    user_id: str
    role: UserRole
    session_id: str
    jti: str


@dataclass
class IssuedSessionTokens:
    user: PublicUser
    session_id: str
    access_token: str
    refresh_token: Optional[str]
    requires_two_factor: bool = False


@dataclass
class LoginChallengeResult:
    challenge_token: str
    methods: list[Literal["totp", "recovery_code"]]
    user_id: str
    requires_two_factor: bool = True


LoginOutcome = Union[IssuedSessionTokens, LoginChallengeResult]


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        session_repo: SessionRepository,
        oauth_repo: OAuthAccountRepository,
        two_factor_repo: TwoFactorRepository,
        login_attempt_repo: LoginAttemptRepository,
        audit_service: AuditService,
        email_service: EmailService,
        google_oauth_client: Optional[GoogleOAuthClient],
        settings: Settings,
        session_cache: Optional[SessionCache] = None,
        repos: Optional[Repositories] = None,
    ) -> None:
        self._user_repo = user_repo
        self._session_repo = session_repo
        self._oauth_repo = oauth_repo
        self._two_factor_repo = two_factor_repo
        self._login_attempt_repo = login_attempt_repo
        self._audit = audit_service
        self._email_service = email_service
        self._google_oauth = google_oauth_client
        self._settings = settings
        self._session_cache: SessionCache = session_cache or NoopSessionCache()
        self._repos = repos

    def _revoke_session_by_id(self, session_id: str, user_id: str) -> bool:
        revoked = self._session_repo.revoke_by_id(session_id, user_id)
        if revoked:
            self._session_cache.invalidate([session_id])
        return revoked

    def _revoke_family(self, family_id: str) -> int:
        family_sids = self._session_repo.list_ids_by_family(family_id)
        count = self._session_repo.revoke_family(family_id)
        self._session_cache.invalidate(family_sids)
        return count

    def _revoke_all_for_user(
        self, user_id: str, except_session_id: Optional[str] = None
    ) -> int:
        active_sids = [
            s.id
            for s in self._session_repo.list_active_for_user(user_id)
            if except_session_id is None or s.id != except_session_id
        ]
        count = self._session_repo.revoke_all_for_user(
            user_id, except_session_id=except_session_id
        )
        self._session_cache.invalidate(active_sids)
        return count

    def sign_access_token(self, user: User, session_id: str) -> str:
        now = _now()
        exp = now + timedelta(minutes=self._settings.access_token_expires_minutes)
        payload = {
            "sub": user.id,
            "role": user.role,
            "sid": session_id,
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "typ": "access",
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    def verify_access_token(self, token: str) -> AccessTokenClaims:
        try:
            decoded = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "role", "sid", "jti", "iat", "exp", "typ"]},
            )
            if decoded.get("typ") != "access":
                raise UnauthorizedError("Invalid authentication token")
            user_id = decoded.get("sub")
            role = decoded.get("role")
            session_id = decoded.get("sid")
            jti = decoded.get("jti")
            if not user_id or not session_id or not jti or role not in ("customer", "admin"):
                raise UnauthorizedError("Invalid authentication token")
            return AccessTokenClaims(
                user_id=str(user_id),
                role=role,
                session_id=str(session_id),
                jti=str(jti),
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(
                "Invalid or expired authentication token", code="TOKEN_EXPIRED_OR_INVALID"
            ) from exc

    def _issue_session(
        self,
        user: User,
        ctx: Optional[RequestContext],
        family_id: Optional[str] = None,
        notify_new_device: bool = False,
    ) -> IssuedSessionTokens:
        req_ctx = ctx or RequestContext()
        has_prior, seen_device = (
            self._session_repo.check_device_history(user.id, req_ctx.user_agent)
            if notify_new_device
            else (False, True)
        )
        raw_refresh = generate_opaque_token(32)
        refresh_hash = sha256_hex(raw_refresh)
        expires_at = _iso(
            _now() + timedelta(days=self._settings.refresh_token_expires_days)
        )
        session = self._session_repo.create(
            CreateSessionInput(
                user_id=user.id,
                refresh_token_hash=refresh_hash,
                family_id=family_id or str(uuid4()),
                user_agent=req_ctx.user_agent,
                ip=req_ctx.ip,
                expires_at=expires_at,
            )
        )
        if notify_new_device and has_prior and not seen_device:
            enqueue_email(
                kind="security_notification",
                payload_ids={
                    "event_id": str(uuid4()),
                    "user_id": user.id,
                    "action": "new_device",
                    "ip": req_ctx.ip,
                    "user_agent": req_ctx.user_agent,
                },
                email_service=self._email_service,
                repos=self._repos,
            )
            self._audit.record(
                event_type="new_device_login_alert",
                outcome="success",
                ctx=req_ctx,
                user_id=user.id,
                target_id=session.id,
            )
        access_token = self.sign_access_token(user, session.id)
        return IssuedSessionTokens(
            user=to_public_user(user),
            session_id=session.id,
            access_token=access_token,
            refresh_token=raw_refresh,
        )

    def _create_2fa_challenge(self, user: User) -> str:
        now = _now()
        exp = now + timedelta(minutes=TWO_FACTOR_CHALLENGE_TTL_MINUTES)
        payload = {
            "sub": user.id,
            "jti": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "typ": "2fa_challenge",
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")

    def _consume_2fa_jti(self, jti: str, exp_ts: int) -> bool:
        expires_at = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return self._two_factor_repo.consume_challenge_jti(jti, expires_at)

    def _check_not_locked(self, key: str) -> bool:
        rec = self._login_attempt_repo.get_by_key(key)
        if not rec or not rec.locked_until:
            return False
        return _parse_iso(rec.locked_until) > _now()

    def _send_verification_for_user(self, user: User) -> None:
        raw_token = generate_opaque_token(32)
        token_hash = sha256_hex(raw_token)
        expires_at = _iso(_now() + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS))
        token_record = self._user_repo.save_email_verification_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        enqueue_email(
            kind="email_verification",
            payload_ids={"token_id": token_record.id, "user_id": user.id},
            raw_token=raw_token,
            email_service=self._email_service,
            repos=self._repos,
        )

    def signup(
        self,
        name: str,
        email: str,
        password: str,
        phone: Optional[str] = None,
        ctx: Optional[RequestContext] = None,
    ) -> IssuedSessionTokens:
        norm_email = email.strip().lower()
        existing = self._user_repo.find_by_email(norm_email)
        if existing:
            raise ConflictError(
                "An account with this email already exists",
                code="EMAIL_ALREADY_EXISTS",
            )

        validate_password_policy(password, norm_email)
        pw_hash = hash_password_argon2(password)
        created = self._user_repo.create(
            CreateUserInput(
                name=name,
                email=norm_email,
                phone=phone,
                password_hash=pw_hash,
                role="customer",
                email_verified=False,
                totp_enabled=False,
            )
        )
        enqueue_email(
            kind="welcome",
            payload_ids={"user_id": created.id},
            email_service=self._email_service,
            repos=self._repos,
        )
        self._send_verification_for_user(created)
        issued = self._issue_session(created, ctx)
        self._audit.record(
            event_type="signup",
            outcome="success",
            ctx=ctx,
            user_id=created.id,
            target_id=issued.session_id,
        )
        return issued

    def login(
        self,
        email: str,
        password: str,
        ctx: Optional[RequestContext] = None,
    ) -> LoginOutcome:
        req_ctx = ctx or RequestContext()
        norm_email = email.strip().lower()
        pair_key = f"pair:{norm_email}|{req_ctx.ip}"
        acct_key = f"acct:{norm_email}"
        ip_key = f"ip:{req_ctx.ip}"

        if (
            self._check_not_locked(pair_key)
            or self._check_not_locked(acct_key)
            or self._check_not_locked(ip_key)
        ):
            dummy_password_work(password)
            self._audit.record(
                event_type="login_locked",
                outcome="failure",
                ctx=req_ctx,
                metadata={"reason": "brute_force_lockout"},
            )
            raise TooManyRequestsError(
                "Invalid credentials or too many failed attempts. Please try again later.",
                code="ACCOUNT_LOCKED",
            )

        user = self._user_repo.find_by_email(norm_email)
        if not user:
            dummy_password_work(password)
            valid, needs_rehash = False, False
        else:
            valid, needs_rehash = verify_password_constant_time(
                password, user.password_hash
            )

        if not valid or not user:
            self._login_attempt_repo.record_failure(
                pair_key,
                "account",
                max_failures=self._settings.login_max_failures,
                base_lock_minutes=self._settings.login_lock_base_minutes,
            )
            self._login_attempt_repo.record_failure(
                acct_key,
                "account",
                max_failures=30,
                base_lock_minutes=15,
            )
            self._login_attempt_repo.record_failure(
                ip_key,
                "ip",
                max_failures=self._settings.login_max_failures,
                base_lock_minutes=self._settings.login_lock_base_minutes,
            )
            self._audit.record(
                event_type="login_failed",
                outcome="failure",
                ctx=req_ctx,
                user_id=user.id if user else None,
                metadata={"reason": "invalid_credentials"},
            )
            raise UnauthorizedError("Invalid credentials", code="INVALID_CREDENTIALS")

        self._login_attempt_repo.reset(pair_key)
        self._login_attempt_repo.reset(acct_key)
        self._login_attempt_repo.reset(ip_key)

        if needs_rehash:
            new_argon2 = hash_password_argon2(password)
            updated = self._user_repo.update(
                user.id, UpdateUserInput(password_hash=new_argon2)
            )
            if updated:
                user = updated

        if user.totp_enabled:
            challenge_token = self._create_2fa_challenge(user)
            self._audit.record(
                event_type="login_2fa_challenge",
                outcome="success",
                ctx=req_ctx,
                user_id=user.id,
            )
            return LoginChallengeResult(
                challenge_token=challenge_token,
                methods=["totp", "recovery_code"],
                user_id=user.id,
            )

        issued = self._issue_session(user, req_ctx, notify_new_device=True)
        self._audit.record(
            event_type="login_success",
            outcome="success",
            ctx=req_ctx,
            user_id=user.id,
            target_id=issued.session_id,
        )
        return issued

    def refresh_session(
        self,
        raw_refresh_token: Optional[str],
        ctx: Optional[RequestContext] = None,
    ) -> IssuedSessionTokens:
        req_ctx = ctx or RequestContext()
        if not raw_refresh_token or not raw_refresh_token.strip():
            raise UnauthorizedError(
                "Missing refresh token", code="REFRESH_TOKEN_MISSING"
            )

        token_hash = sha256_hex(raw_refresh_token.strip())
        session = self._session_repo.find_by_refresh_hash(token_hash)

        if not session:
            grace_sess = self._session_repo.find_by_grace_refresh_hash(token_hash)
            if grace_sess:
                if grace_sess.revoked_at is not None:
                    self._revoke_family(grace_sess.family_id)
                    self._audit.record(
                        event_type="refresh_reuse_detected",
                        outcome="warning",
                        ctx=req_ctx,
                        user_id=grace_sess.user_id,
                        target_id=grace_sess.id,
                        metadata={
                            "familyId": grace_sess.family_id,
                            "reason": "revoked_session_grace",
                        },
                    )
                    raise UnauthorizedError(
                        "Session has been revoked. Please sign in again.",
                        code="SESSION_REVOKED",
                    )
                if _parse_iso(grace_sess.expires_at) <= _now():
                    raise UnauthorizedError(
                        "Refresh token expired. Please sign in again.",
                        code="REFRESH_TOKEN_EXPIRED",
                    )
                consumed_grace = self._session_repo.consume_grace_refresh_token(
                    grace_sess.id, token_hash
                )
                if consumed_grace is not None:
                    user = self._user_repo.find_by_id(consumed_grace.user_id)
                    if not user:
                        raise UnauthorizedError("User session no longer valid")
                    access_token = self.sign_access_token(user, consumed_grace.id)
                    self._audit.record(
                        event_type="refresh_grace_hit",
                        outcome="success",
                        ctx=req_ctx,
                        user_id=user.id,
                        target_id=consumed_grace.id,
                        metadata={
                            "graceUsesRemaining": consumed_grace.grace_uses_remaining
                        },
                    )
                    return IssuedSessionTokens(
                        user=to_public_user(user),
                        session_id=consumed_grace.id,
                        access_token=access_token,
                        refresh_token=None,
                    )

            reused = grace_sess or self._session_repo.find_by_previous_refresh_hash(
                token_hash
            )
            if reused:
                revoked_count = self._revoke_family(reused.family_id)
                self._audit.record(
                    event_type="refresh_reuse_detected",
                    outcome="warning",
                    ctx=req_ctx,
                    user_id=reused.user_id,
                    target_id=reused.id,
                    metadata={
                        "familyId": reused.family_id,
                        "revokedSessions": revoked_count,
                        "reason": (
                            "grace_window_expired"
                            if grace_sess
                            else "previous_token_reused"
                        ),
                    },
                )
                raise UnauthorizedError(
                    "Refresh token reuse detected. Session family revoked; please sign in again.",
                    code="REFRESH_TOKEN_REUSE_DETECTED",
                )
            raise UnauthorizedError(
                "Invalid refresh token", code="INVALID_REFRESH_TOKEN"
            )

        if session.revoked_at is not None:
            self._revoke_family(session.family_id)
            self._audit.record(
                event_type="refresh_reuse_detected",
                outcome="warning",
                ctx=req_ctx,
                user_id=session.user_id,
                target_id=session.id,
                metadata={"familyId": session.family_id, "reason": "revoked_session"},
            )
            raise UnauthorizedError(
                "Session has been revoked. Please sign in again.",
                code="SESSION_REVOKED",
            )

        if _parse_iso(session.expires_at) <= _now():
            raise UnauthorizedError(
                "Refresh token expired. Please sign in again.",
                code="REFRESH_TOKEN_EXPIRED",
            )

        user = self._user_repo.find_by_id(session.user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")

        new_raw_refresh = generate_opaque_token(32)
        new_hash = sha256_hex(new_raw_refresh)
        now = _now()
        new_expires_at = _iso(
            now + timedelta(days=self._settings.refresh_token_expires_days)
        )
        grace_expires_at = (
            _iso(now + timedelta(seconds=self._settings.refresh_grace_seconds))
            if self._settings.refresh_grace_seconds > 0
            else None
        )
        rotated = self._session_repo.rotate_refresh_token(
            session_id=session.id,
            expected_hash=token_hash,
            new_hash=new_hash,
            new_expires_at=new_expires_at,
            ip=req_ctx.ip,
            user_agent=req_ctx.user_agent,
            grace_expires_at=grace_expires_at,
        )
        if rotated is None:
            latest = self._session_repo.find_by_id(session.id)
            if (
                latest is not None
                and latest.revoked_at is None
                and _parse_iso(latest.expires_at) > _now()
                and self._is_within_grace_window(latest, token_hash)
            ):
                access_token = self.sign_access_token(user, latest.id)
                self._audit.record(
                    event_type="refresh_grace_hit",
                    outcome="success",
                    ctx=req_ctx,
                    user_id=user.id,
                    target_id=latest.id,
                )
                return IssuedSessionTokens(
                    user=to_public_user(user),
                    session_id=latest.id,
                    access_token=access_token,
                    refresh_token=None,
                )
            self._revoke_family(session.family_id)
            self._audit.record(
                event_type="refresh_reuse_detected",
                outcome="warning",
                ctx=req_ctx,
                user_id=session.user_id,
                target_id=session.id,
                metadata={"familyId": session.family_id, "reason": "concurrent_rotation"},
            )
            raise UnauthorizedError(
                "Refresh token reuse detected. Please sign in again.",
                code="REFRESH_TOKEN_REUSE_DETECTED",
            )

        access_token = self.sign_access_token(user, rotated.id)
        return IssuedSessionTokens(
            user=to_public_user(user),
            session_id=rotated.id,
            access_token=access_token,
            refresh_token=new_raw_refresh,
        )

    def logout(
        self,
        session_id: Optional[str],
        user_id: Optional[str],
        raw_refresh_token: Optional[str],
        ctx: Optional[RequestContext] = None,
    ) -> None:
        resolved_sid = session_id
        resolved_uid = user_id

        if not resolved_sid and raw_refresh_token:
            sess = self._session_repo.find_by_refresh_hash(sha256_hex(raw_refresh_token))
            if sess:
                resolved_sid = sess.id
                resolved_uid = sess.user_id

        if resolved_sid and resolved_uid:
            self._revoke_session_by_id(resolved_sid, resolved_uid)
            self._audit.record(
                event_type="logout",
                outcome="success",
                ctx=ctx,
                user_id=resolved_uid,
                target_id=resolved_sid,
            )

    def logout_all(self, user_id: str, ctx: Optional[RequestContext] = None) -> int:
        count = self._revoke_all_for_user(user_id)
        self._audit.record(
            event_type="logout_all",
            outcome="success",
            ctx=ctx,
            user_id=user_id,
            metadata={"revokedCount": count},
        )
        return count

    def list_sessions(
        self, user_id: str, current_session_id: str
    ) -> list[PublicSession]:
        active = self._session_repo.list_active_for_user(user_id)
        return [
            PublicSession(
                id=s.id,
                user_agent=s.user_agent,
                ip=s.ip,
                created_at=s.created_at,
                last_used_at=s.last_used_at,
                expires_at=s.expires_at,
                is_current=(s.id == current_session_id),
            )
            for s in active
        ]

    def revoke_session(
        self,
        user_id: str,
        target_session_id: str,
        ctx: Optional[RequestContext] = None,
    ) -> None:
        revoked = self._revoke_session_by_id(target_session_id, user_id)
        if not revoked:
            raise NotFoundError("Session not found")
        self._audit.record(
            event_type="session_revoked",
            outcome="success",
            ctx=ctx,
            user_id=user_id,
            target_id=target_session_id,
        )

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

    def change_password(
        self,
        user_id: str,
        current_session_id: str,
        current_password: str,
        new_password: str,
        ctx: Optional[RequestContext] = None,
    ) -> dict[str, object]:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")

        if user.password_hash.startswith("!"):
            raise BadRequestError(
                "This account signs in via Google OAuth and has no local password. Use Forgot Password to set one.",
                code="OAUTH_NO_PASSWORD",
            )

        valid, _ = verify_password_constant_time(current_password, user.password_hash)
        if not valid:
            self._audit.record(
                event_type="password_change_failed",
                outcome="failure",
                ctx=ctx,
                user_id=user.id,
            )
            raise UnauthorizedError(
                "Current password is incorrect", code="INVALID_CREDENTIALS"
            )

        validate_password_policy(new_password, user.email)
        new_hash = hash_password_argon2(new_password)
        self._user_repo.update(user.id, UpdateUserInput(password_hash=new_hash))
        revoked_others = self._revoke_all_for_user(
            user.id, except_session_id=current_session_id
        )
        req_ctx = ctx or RequestContext()
        enqueue_email(
            kind="security_notification",
            payload_ids={
                "event_id": str(uuid4()),
                "user_id": user.id,
                "action": "password_changed",
                "ip": req_ctx.ip,
                "user_agent": req_ctx.user_agent,
            },
            email_service=self._email_service,
            repos=self._repos,
        )
        self._audit.record(
            event_type="password_changed",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
            metadata={"revokedOtherSessions": revoked_others},
        )
        return {
            "message": "Password changed successfully. All other devices have been logged out.",
            "revokedOtherSessions": revoked_others,
        }

    def verify_email(
        self, token: str, ctx: Optional[RequestContext] = None
    ) -> PublicUser:
        token_hash = sha256_hex(token.strip())
        record = self._user_repo.find_email_verification_token_by_hash(token_hash)

        if not record or record.used_at or _parse_iso(record.expires_at) <= _now():
            raise BadRequestError(
                "Invalid, expired, or already used email verification token",
                code="INVALID_VERIFICATION_TOKEN",
            )

        user = self._user_repo.find_by_id(record.user_id)
        if not user:
            raise NotFoundError("User not found")

        self._user_repo.mark_email_verification_token_used(record.id)
        self._user_repo.invalidate_unused_email_verification_tokens(user.id)
        updated = self._user_repo.update(
            user.id,
            UpdateUserInput(email_verified=True, email_verified_at=_iso(_now())),
        )
        assert updated is not None
        self._audit.record(
            event_type="email_verified",
            outcome="success",
            ctx=ctx,
            user_id=updated.id,
        )
        return to_public_user(updated)

    def resend_verification_email(
        self, user_id: str, ctx: Optional[RequestContext] = None
    ) -> dict[str, str]:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")

        if user.email_verified:
            raise BadRequestError(
                "Your email address is already verified.",
                code="EMAIL_ALREADY_VERIFIED",
            )

        latest = self._user_repo.get_latest_email_verification_token(user.id)
        if latest:
            elapsed = (_now() - _parse_iso(latest.created_at)).total_seconds()
            if elapsed < EMAIL_RESEND_COOLDOWN_SECONDS:
                wait_sec = max(1, int(EMAIL_RESEND_COOLDOWN_SECONDS - elapsed))
                raise TooManyRequestsError(
                    f"Please wait {wait_sec} seconds before requesting another verification email.",
                    code="VERIFICATION_RESEND_COOLDOWN",
                )

        self._user_repo.invalidate_unused_email_verification_tokens(user.id)
        self._send_verification_for_user(user)
        self._audit.record(
            event_type="email_verification_sent",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
        )
        return {"message": "Verification email sent. Please check your inbox."}

    def forgot_password(
        self, email: str, ctx: Optional[RequestContext] = None
    ) -> dict[str, str]:
        norm_email = email.strip().lower()
        user = self._user_repo.find_by_email(norm_email)

        if user:
            raw_token = generate_opaque_token(32)
            token_hash = sha256_hex(raw_token)
            expires_at = _iso(_now() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES))
            token_record = self._user_repo.save_password_reset_token(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            enqueue_email(
                kind="password_reset",
                payload_ids={"token_id": token_record.id, "user_id": user.id},
                raw_token=raw_token,
                email_service=self._email_service,
                repos=self._repos,
            )
            self._audit.record(
                event_type="password_reset_requested",
                outcome="success",
                ctx=ctx,
                user_id=user.id,
            )
        else:
            # Uniform CPU work & generic audit note without leaking account existence in response
            _ = sha256_hex(generate_opaque_token(32))
            self._audit.record(
                event_type="password_reset_requested",
                outcome="success",
                ctx=ctx,
                metadata={"accountMatched": False},
            )

        return {
            "message": "If an account exists with that email, a password reset link has been sent."
        }

    def reset_password(
        self,
        token: str,
        new_password: str,
        ctx: Optional[RequestContext] = None,
    ) -> dict[str, str]:
        token_hash = sha256_hex(token.strip())
        record = self._user_repo.find_password_reset_token_by_hash(token_hash)

        if not record or record.used_at:
            raise BadRequestError("Invalid or already used password reset token")

        if _parse_iso(record.expires_at) <= _now():
            raise BadRequestError("Password reset token has expired")

        user = self._user_repo.find_by_id(record.user_id)
        if not user:
            raise NotFoundError("User not found")

        validate_password_policy(new_password, user.email)
        pw_hash = hash_password_argon2(new_password)
        updated = self._user_repo.update(
            record.user_id, UpdateUserInput(password_hash=pw_hash)
        )
        if not updated:
            raise NotFoundError("User not found")

        self._user_repo.mark_password_reset_token_used(record.id)
        revoked_count = self._revoke_all_for_user(record.user_id)
        self._login_attempt_repo.reset(f"acct:{user.email.lower()}")
        req_ctx = ctx or RequestContext()
        enqueue_email(
            kind="security_notification",
            payload_ids={
                "event_id": str(uuid4()),
                "user_id": user.id,
                "action": "password_changed",
                "ip": req_ctx.ip,
                "user_agent": req_ctx.user_agent,
            },
            email_service=self._email_service,
            repos=self._repos,
        )
        self._audit.record(
            event_type="password_reset_completed",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
            metadata={"revokedSessions": revoked_count},
        )
        return {"message": "Password has been reset successfully. You can now log in."}

    # ── 2FA (TOTP + Recovery Codes) ───────────────────────────────────────────

    def get_2fa_status(self, user_id: str) -> dict[str, object]:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")
        remaining = self._two_factor_repo.count_unused_recovery_codes(user_id)
        return {
            "enabled": user.totp_enabled,
            "requiredForRole": user.role == "admin",
            "recoveryCodesRemaining": remaining,
        }

    def setup_2fa(
        self, user_id: str, ctx: Optional[RequestContext] = None
    ) -> dict[str, str]:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")
        existing = self._two_factor_repo.get_totp_secret(user.id)
        if user.totp_enabled or (existing and existing.is_enabled):
            raise ConflictError(
                "Two-factor authentication is already enabled on this account",
                code="2FA_ALREADY_ENABLED",
            )

        secret = pyotp.random_base32()
        encrypted = encrypt_secret(secret, self._settings, context=b"totp-secret-v1")
        self._two_factor_repo.upsert_pending_totp(user.id, encrypted)
        otpauth_url = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="BeanBox"
        )
        qr_data_url = generate_totp_qr_data_url(otpauth_url)

        self._audit.record(
            event_type="2fa_setup_initiated",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
        )
        return {
            "secret": secret,
            "otpauthUrl": otpauth_url,
            "qrDataUrl": qr_data_url,
        }

    def _verify_totp_code(
        self, user_id: str, code: str, prevent_replay: bool = True
    ) -> bool:
        sec_rec = self._two_factor_repo.get_totp_secret(user_id)
        if not sec_rec:
            return False
        secret = decrypt_secret(
            sec_rec.encrypted_secret, self._settings, context=b"totp-secret-v1"
        )
        totp = pyotp.TOTP(secret)
        cleaned = code.strip()
        if not cleaned.isdigit() or len(cleaned) != 6:
            return False

        now = _now()
        base_step = int(now.timestamp()) // totp.interval
        for offset in (0, -1, 1):
            step = base_step + offset
            expected = totp.generate_otp(step)
            if secrets.compare_digest(expected, cleaned):
                if not prevent_replay:
                    return True
                return self._two_factor_repo.consume_totp_timestep(user_id, step)
        return False

    def enable_2fa(
        self,
        user_id: str,
        code: str,
        ctx: Optional[RequestContext] = None,
    ) -> dict[str, object]:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")
        sec_rec = self._two_factor_repo.get_totp_secret(user.id)
        if not sec_rec:
            raise BadRequestError(
                "Please initiate 2FA setup before enabling", code="2FA_NOT_INITIATED"
            )
        if sec_rec.is_enabled or user.totp_enabled:
            raise ConflictError(
                "Two-factor authentication is already enabled",
                code="2FA_ALREADY_ENABLED",
            )

        if not self._verify_totp_code(user.id, code, prevent_replay=True):
            self._audit.record(
                event_type="2fa_enable_failed",
                outcome="failure",
                ctx=ctx,
                user_id=user.id,
            )
            raise BadRequestError(
                "Invalid 6-digit authenticator code", code="INVALID_TOTP_CODE"
            )

        self._two_factor_repo.enable_totp(user.id)
        updated = self._user_repo.update(user.id, UpdateUserInput(totp_enabled=True))
        assert updated is not None

        recovery_codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
        code_hashes = [
            hmac_sha256_hex(self._settings.jwt_secret, normalize_recovery_code(c))
            for c in recovery_codes
        ]
        self._two_factor_repo.replace_recovery_codes(user.id, code_hashes)

        req_ctx = ctx or RequestContext()
        enqueue_email(
            kind="security_notification",
            payload_ids={
                "event_id": str(uuid4()),
                "user_id": user.id,
                "action": "2fa_status",
                "enabled": True,
                "ip": req_ctx.ip,
                "user_agent": req_ctx.user_agent,
            },
            email_service=self._email_service,
            repos=self._repos,
        )
        self._audit.record(
            event_type="2fa_enabled",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
        )
        return {
            "user": to_public_user(updated),
            "totpEnabled": True,
            "recoveryCodes": recovery_codes,
        }

    def verify_2fa_login(
        self,
        challenge_token: str,
        code: str,
        ctx: Optional[RequestContext] = None,
    ) -> IssuedSessionTokens:
        req_ctx = ctx or RequestContext()
        try:
            decoded = jwt.decode(
                challenge_token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["sub", "jti", "exp", "typ"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(
                "2FA challenge expired or invalid. Please sign in again.",
                code="INVALID_2FA_CHALLENGE",
            ) from exc

        if decoded.get("typ") != "2fa_challenge":
            raise UnauthorizedError("Invalid 2FA challenge", code="INVALID_2FA_CHALLENGE")

        user_id = str(decoded["sub"])
        jti = str(decoded["jti"])
        exp_ts = int(decoded["exp"])

        attempt_key = f"2fa:{user_id}"
        if self._check_not_locked(attempt_key):
            self._audit.record(
                event_type="2fa_login_locked",
                outcome="failure",
                ctx=req_ctx,
                user_id=user_id,
            )
            raise TooManyRequestsError(
                "Too many failed 2FA attempts. Please wait 15 minutes before trying again.",
                code="TWO_FACTOR_LOCKED",
            )

        user = self._user_repo.find_by_id(user_id)
        if not user or not user.totp_enabled:
            raise UnauthorizedError("2FA is not active for this account")

        cleaned = code.strip()
        used_recovery = False
        verified = False

        if cleaned.isdigit() and len(cleaned) == 6:
            verified = self._verify_totp_code(user.id, cleaned, prevent_replay=True)
        else:
            normalized = normalize_recovery_code(cleaned)
            if len(normalized) >= 6:
                code_hash = hmac_sha256_hex(self._settings.jwt_secret, normalized)
                verified = self._two_factor_repo.consume_recovery_code(
                    user.id, code_hash
                )
                used_recovery = verified

        if not verified:
            self._login_attempt_repo.record_failure(
                attempt_key,
                "2fa",
                max_failures=self._settings.login_max_failures,
                base_lock_minutes=self._settings.login_lock_base_minutes,
            )
            self._audit.record(
                event_type="2fa_login_failed",
                outcome="failure",
                ctx=req_ctx,
                user_id=user.id,
            )
            raise UnauthorizedError(
                "Invalid authenticator or recovery code", code="INVALID_2FA_CODE"
            )

        if not self._consume_2fa_jti(jti, exp_ts):
            raise UnauthorizedError(
                "This 2FA challenge has already been used. Please sign in again.",
                code="INVALID_2FA_CHALLENGE",
            )

        self._login_attempt_repo.reset(attempt_key)
        issued = self._issue_session(user, req_ctx, notify_new_device=True)
        self._audit.record(
            event_type="2fa_recovery_used" if used_recovery else "2fa_login_success",
            outcome="success",
            ctx=req_ctx,
            user_id=user.id,
            target_id=issued.session_id,
        )
        return issued

    def regenerate_recovery_codes(
        self,
        user_id: str,
        code: str,
        ctx: Optional[RequestContext] = None,
    ) -> list[str]:
        user = self._user_repo.find_by_id(user_id)
        if not user or not user.totp_enabled:
            raise BadRequestError("Two-factor authentication is not enabled")
        if not self._verify_totp_code(user.id, code, prevent_replay=True):
            raise UnauthorizedError(
                "Invalid 6-digit authenticator code", code="INVALID_TOTP_CODE"
            )
        recovery_codes = generate_recovery_codes(RECOVERY_CODE_COUNT)
        code_hashes = [
            hmac_sha256_hex(self._settings.jwt_secret, normalize_recovery_code(c))
            for c in recovery_codes
        ]
        self._two_factor_repo.replace_recovery_codes(user.id, code_hashes)
        self._audit.record(
            event_type="2fa_recovery_regenerated",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
        )
        return recovery_codes

    def disable_2fa(
        self,
        user_id: str,
        code: str,
        password: Optional[str] = None,
        ctx: Optional[RequestContext] = None,
    ) -> PublicUser:
        user = self._user_repo.find_by_id(user_id)
        if not user:
            raise UnauthorizedError("User session no longer valid")

        if user.role == "admin":
            raise ForbiddenError(
                "Two-factor authentication is required for administrators and cannot be disabled.",
                code="ADMIN_2FA_REQUIRED",
            )

        if not user.totp_enabled:
            raise BadRequestError("Two-factor authentication is not enabled")

        if not user.password_hash.startswith("!"):
            if not password:
                raise BadRequestError(
                    "Password is required to disable two-factor authentication",
                    code="PASSWORD_REQUIRED",
                )
            pw_ok, _ = verify_password_constant_time(password, user.password_hash)
            if not pw_ok:
                raise UnauthorizedError("Invalid password", code="INVALID_CREDENTIALS")

        cleaned = code.strip()
        code_ok = False
        if cleaned.isdigit() and len(cleaned) == 6:
            code_ok = self._verify_totp_code(user.id, cleaned, prevent_replay=True)
        else:
            norm = normalize_recovery_code(cleaned)
            if norm:
                code_ok = self._two_factor_repo.consume_recovery_code(
                    user.id, hmac_sha256_hex(self._settings.jwt_secret, norm)
                )

        if not code_ok:
            raise UnauthorizedError(
                "Invalid authenticator or recovery code", code="INVALID_2FA_CODE"
            )

        self._two_factor_repo.disable_totp(user.id)
        updated = self._user_repo.update(user.id, UpdateUserInput(totp_enabled=False))
        assert updated is not None
        req_ctx = ctx or RequestContext()
        enqueue_email(
            kind="security_notification",
            payload_ids={
                "event_id": str(uuid4()),
                "user_id": user.id,
                "action": "2fa_status",
                "enabled": False,
                "ip": req_ctx.ip,
                "user_agent": req_ctx.user_agent,
            },
            email_service=self._email_service,
            repos=self._repos,
        )
        self._audit.record(
            event_type="2fa_disabled",
            outcome="success",
            ctx=ctx,
            user_id=user.id,
        )
        return to_public_user(updated)

    # ── Google OAuth 2.0 (Authorization Code + PKCE) ──────────────────────────

    def _ensure_google_oauth_enabled(self) -> GoogleOAuthClient:
        if not self._settings.google_oauth_enabled or self._google_oauth is None:
            raise AppError(
                status_code=503,
                code="OAUTH_DISABLED",
                message="Google Sign-In is not configured on this server.",
            )
        return self._google_oauth

    def start_google_oauth(self, next_path: Optional[str] = None) -> tuple[str, str]:
        client = self._ensure_google_oauth_enabled()
        state = generate_opaque_token(24)
        nonce = generate_opaque_token(24)
        code_verifier = generate_opaque_token(48)
        challenge = pkce_code_challenge(code_verifier)

        tx_payload = {
            "state": state,
            "nonce": nonce,
            "code_verifier": code_verifier,
            "next": sanitize_next_path(next_path, default="/"),
            "exp": int((_now() + timedelta(minutes=10)).timestamp()),
        }
        sealed_tx = encrypt_secret(
            json.dumps(tx_payload),
            self._settings,
            context=b"beanbox-oauth-tx-v1",
        )
        auth_url = client.build_authorization_url(
            state=state, nonce=nonce, code_challenge=challenge
        )
        return auth_url, sealed_tx

    def complete_google_oauth(
        self,
        code: str,
        state: str,
        sealed_tx: Optional[str],
        ctx: Optional[RequestContext] = None,
    ) -> tuple[LoginOutcome, str]:
        client = self._ensure_google_oauth_enabled()
        req_ctx = ctx or RequestContext()

        if not sealed_tx:
            self._audit.record(
                event_type="oauth_google_failed",
                outcome="failure",
                ctx=req_ctx,
                metadata={"reason": "missing_tx_cookie"},
            )
            raise BadRequestError(
                "Missing OAuth transaction state", code="OAUTH_INVALID_STATE"
            )

        try:
            tx = json.loads(
                decrypt_secret(
                    sealed_tx, self._settings, context=b"beanbox-oauth-tx-v1"
                )
            )
        except Exception as exc:
            raise BadRequestError(
                "Corrupted OAuth transaction state", code="OAUTH_INVALID_STATE"
            ) from exc

        if int(tx.get("exp", 0)) <= int(_now().timestamp()):
            raise BadRequestError(
                "OAuth login session expired. Please try again.",
                code="OAUTH_STATE_EXPIRED",
            )

        expected_state = str(tx.get("state", ""))
        if not expected_state or not secrets.compare_digest(state, expected_state):
            self._audit.record(
                event_type="oauth_google_failed",
                outcome="warning",
                ctx=req_ctx,
                metadata={"reason": "state_mismatch"},
            )
            raise BadRequestError(
                "OAuth state mismatch", code="OAUTH_INVALID_STATE"
            )

        identity = client.exchange_code_and_verify(
            code=code,
            code_verifier=str(tx["code_verifier"]),
            expected_nonce=str(tx["nonce"]),
        )
        next_path = sanitize_next_path(tx.get("next"), default="/")

        existing_oauth = self._oauth_repo.find_by_provider_user(
            "google", identity.provider_user_id
        )
        user: Optional[User] = None

        if existing_oauth:
            user = self._user_repo.find_by_id(existing_oauth.user_id)
            if user and not user.email_verified:
                user = self._user_repo.update(
                    user.id,
                    UpdateUserInput(
                        email_verified=True, email_verified_at=_iso(_now())
                    ),
                )

        if user is None:
            user_by_email = self._user_repo.find_by_email(identity.email)
            if user_by_email:
                user = user_by_email
                revoked_unverified = 0
                if not user.email_verified:
                    user = (
                        self._user_repo.update(
                            user.id,
                            UpdateUserInput(
                                password_hash="!oauth-only",
                                email_verified=True,
                                email_verified_at=_iso(_now()),
                            ),
                        )
                        or user
                    )
                    self._user_repo.delete_unused_tokens_for_user(user.id)
                    revoked_unverified = self._revoke_all_for_user(user.id)
                self._oauth_repo.create(
                    CreateOAuthAccountInput(
                        user_id=user.id,
                        provider="google",
                        provider_user_id=identity.provider_user_id,
                        provider_email=identity.email,
                    )
                )
                self._audit.record(
                    event_type="oauth_google_linked",
                    outcome="success",
                    ctx=req_ctx,
                    user_id=user.id,
                    metadata={"revokedUnverifiedSessions": revoked_unverified},
                )
            else:
                now_iso = _iso(_now())
                user = self._user_repo.create(
                    CreateUserInput(
                        name=identity.name,
                        email=identity.email,
                        password_hash="!oauth-only",
                        role="customer",
                        email_verified=True,
                        email_verified_at=now_iso,
                        totp_enabled=False,
                    )
                )
                self._oauth_repo.create(
                    CreateOAuthAccountInput(
                        user_id=user.id,
                        provider="google",
                        provider_user_id=identity.provider_user_id,
                        provider_email=identity.email,
                    )
                )
                enqueue_email(
                    kind="welcome",
                    payload_ids={"user_id": user.id},
                    email_service=self._email_service,
                    repos=self._repos,
                )
                self._audit.record(
                    event_type="signup_google",
                    outcome="success",
                    ctx=req_ctx,
                    user_id=user.id,
                )

        if user.totp_enabled:
            challenge = self._create_2fa_challenge(user)
            self._audit.record(
                event_type="login_2fa_challenge",
                outcome="success",
                ctx=req_ctx,
                user_id=user.id,
                metadata={"provider": "google"},
            )
            return (
                LoginChallengeResult(
                    challenge_token=challenge,
                    methods=["totp", "recovery_code"],
                    user_id=user.id,
                ),
                next_path,
            )

        issued = self._issue_session(user, req_ctx, notify_new_device=True)
        self._audit.record(
            event_type="oauth_google_login",
            outcome="success",
            ctx=req_ctx,
            user_id=user.id,
            target_id=issued.session_id,
        )
        return issued, next_path
