from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import secrets
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

import bcrypt
import qrcode
import qrcode.constants
import qrcode.image.svg
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import Request

from app.config import Settings
from app.utils.errors import BadRequestError

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Curated common / leaked >=10-character passwords & base patterns (lowercase)
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "0000000000",
        "1111111111",
        "1234567890",
        "12345678901",
        "123456789012",
        "0123456789",
        "9876543210",
        "aaaaaaaaaa",
        "abc1234567",
        "abcd123456",
        "admin12345",
        "admin@12345",
        "administrator",
        "baseball123",
        "beanbox123",
        "beanbox1234",
        "changeme12",
        "changeme123",
        "chocolate1",
        "coffee1234",
        "coffee12345",
        "computer12",
        "dragon1234",
        "football12",
        "football123",
        "hello12345",
        "iloveyou12",
        "iloveyou123",
        "india12345",
        "letmein123",
        "letmein1234",
        "master1234",
        "monkey1234",
        "passw0rd12",
        "passw0rd123",
        "password10",
        "password12",
        "password123",
        "password1234",
        "password12345",
        "password!1",
        "password@1",
        "princess12",
        "qazwsxedc1",
        "qwerty1234",
        "qwerty12345",
        "qwertyuiop",
        "shadow1234",
        "starwars12",
        "sunshine12",
        "superman12",
        "trustno123",
        "welcome123",
        "welcome1234",
        "welcome@12",
    }
)


@lru_cache(maxsize=1)
def _dummy_argon2_hash() -> str:
    return _PASSWORD_HASHER.hash("BeanBoxConstantTimeDummyPassword!2026")


def hash_password_argon2(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password_constant_time(password: str, stored_hash: str) -> tuple[bool, bool]:
    """
    Verifies a plaintext password against a stored Argon2id or legacy bcrypt hash.
    Always performs meaningful work even for OAuth-only ('!...') placeholders.
    Returns (is_valid, needs_rehash_to_argon2id).
    """
    if not stored_hash or stored_hash.startswith("!"):
        # Execute full Argon2id verification against dummy hash for uniform timing
        try:
            _PASSWORD_HASHER.verify(_dummy_argon2_hash(), password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass
        return False, False

    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            matched = bcrypt.checkpw(
                password.encode("utf-8"), stored_hash.encode("utf-8")
            )
            return matched, matched
        except ValueError:
            return False, False

    if stored_hash.startswith("$argon2"):
        try:
            _PASSWORD_HASHER.verify(stored_hash, password)
            return True, _PASSWORD_HASHER.check_needs_rehash(stored_hash)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False, False

    return False, False


def dummy_password_work(password: str) -> None:
    """Runs constant-time Argon2id work when a user account does not exist or is locked."""
    try:
        _PASSWORD_HASHER.verify(_dummy_argon2_hash(), password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass


def validate_password_policy(password: str, email: Optional[str] = None) -> None:
    if len(password) < 10:
        raise BadRequestError(
            "Password must be at least 10 characters long",
            code="WEAK_PASSWORD",
        )
    if len(password) > 128:
        raise BadRequestError(
            "Password cannot exceed 128 characters",
            code="WEAK_PASSWORD",
        )

    lowered = password.strip().lower()
    if lowered in COMMON_PASSWORDS:
        raise BadRequestError(
            "This password is too common. Please choose a stronger passphrase.",
            code="COMMON_PASSWORD",
        )

    if email:
        norm_email = email.strip().lower()
        if norm_email and norm_email in password.lower():
            raise BadRequestError(
                "Password must not contain your email address",
                code="PASSWORD_CONTAINS_EMAIL",
            )


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hmac_sha256_hex(secret_key: str, raw: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_opaque_token(nbytes: int = 32) -> str:
    """Generates a CSPRNG URL-safe token (default 32 bytes = 256 bits)."""
    return secrets.token_urlsafe(nbytes)


def normalize_recovery_code(raw: str) -> str:
    return "".join(ch for ch in raw.strip().upper() if ch.isalnum())


def generate_recovery_codes(count: int = 10) -> list[str]:
    codes: list[str] = []
    for _ in range(count):
        raw = secrets.token_hex(4).upper()  # 8 hex chars (32 bits each)
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def _derive_aead_key(material: str, info: bytes) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"beanbox-security-kdf-v1",
        info=info,
    )
    return hkdf.derive(material.encode("utf-8"))


def encrypt_secret(plaintext: str, settings: Settings, context: bytes = b"totp-secret-v1") -> str:
    material = settings.totp_encryption_key.strip() or settings.jwt_secret
    key = _derive_aead_key(material, context)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), context)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return f"v1:{blob}"


def decrypt_secret(token: str, settings: Settings, context: bytes = b"totp-secret-v1") -> str:
    if not token.startswith("v1:"):
        raise ValueError("Unsupported encrypted secret format")
    material = settings.totp_encryption_key.strip() or settings.jwt_secret
    key = _derive_aead_key(material, context)
    raw = base64.urlsafe_b64decode(token[3:].encode("ascii"))
    if len(raw) < 13:
        raise ValueError("Corrupted encrypted secret")
    nonce, ct = raw[:12], raw[12:]
    pt = AESGCM(key).decrypt(nonce, ct, context)
    return pt.decode("utf-8")


def generate_totp_qr_data_url(otpauth_url: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


def extract_client_ip(request: Request, settings: Settings) -> str:
    proxy_count = settings.trusted_proxy_count
    if proxy_count > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [part.strip() for part in xff.split(",") if part.strip()]
            if len(parts) >= proxy_count:
                return parts[-proxy_count][:64]
    return request.client.host if request.client else "unknown"


def extract_user_agent(request: Request) -> str:
    ua = request.headers.get("user-agent") or "unknown"
    return ua.strip()[:300]


def is_secure_cookie(settings: Settings, request: Optional[Request] = None) -> bool:
    if settings.cookie_secure == "true":
        return True
    if settings.cookie_secure == "false":
        return False
    if settings.app_env == "production":
        return True
    if request is not None and request.url.scheme == "https":
        return True
    return False


def sanitize_next_path(next_path: Optional[str], default: str = "/") -> str:
    """Prevents open redirects: allows only app-relative '/...' paths."""
    if not next_path:
        return default
    candidate = next_path.strip()
    if not candidate.startswith("/") or candidate.startswith("//") or "\\" in candidate:
        return default
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return default
    return candidate
