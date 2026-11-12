from __future__ import annotations

import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt

from app.config import Settings
from app.utils.errors import BadRequestError, UnauthorizedError

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


@dataclass
class GoogleVerifiedIdentity:
    provider_user_id: str
    email: str
    email_verified: bool
    name: str


def pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GoogleOAuthClient(ABC):
    @abstractmethod
    def build_authorization_url(
        self, state: str, nonce: str, code_challenge: str
    ) -> str: ...

    @abstractmethod
    def exchange_code_and_verify(
        self, code: str, code_verifier: str, expected_nonce: str
    ) -> GoogleVerifiedIdentity: ...


class HttpxGoogleOAuthClient(GoogleOAuthClient):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL)

    def build_authorization_url(
        self, state: str, nonce: str, code_challenge: str
    ) -> str:
        params = {
            "client_id": self._settings.google_client_id.strip(),
            "redirect_uri": self._settings.google_redirect_uri.strip(),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code_and_verify(
        self, code: str, code_verifier: str, expected_nonce: str
    ) -> GoogleVerifiedIdentity:
        try:
            with httpx.Client(timeout=10.0) as client:
                token_res = client.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self._settings.google_client_id.strip(),
                        "client_secret": self._settings.google_client_secret.strip(),
                        "redirect_uri": self._settings.google_redirect_uri.strip(),
                        "code_verifier": code_verifier,
                        "grant_type": "authorization_code",
                    },
                )
        except httpx.HTTPError as exc:
            raise BadRequestError(
                "Could not reach Google authentication service",
                code="OAUTH_EXCHANGE_FAILED",
            ) from exc

        if token_res.status_code != 200:
            raise UnauthorizedError(
                "Google authorization code exchange failed",
                code="OAUTH_EXCHANGE_FAILED",
            )

        payload = token_res.json()
        id_token = payload.get("id_token")
        if not id_token or not isinstance(id_token, str):
            raise UnauthorizedError(
                "Missing ID token in Google OAuth response",
                code="OAUTH_INVALID_TOKEN",
            )

        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.google_client_id.strip(),
                options={"require": ["exp", "sub", "email", "nonce", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError(
                "Invalid Google ID token", code="OAUTH_INVALID_TOKEN"
            ) from exc

        if claims.get("iss") not in GOOGLE_ISSUERS:
            raise UnauthorizedError(
                "Untrusted Google token issuer", code="OAUTH_INVALID_TOKEN"
            )

        token_nonce: Optional[str] = claims.get("nonce")
        if not token_nonce or not secrets.compare_digest(
            str(token_nonce), expected_nonce
        ):
            raise UnauthorizedError(
                "Invalid OAuth nonce", code="OAUTH_INVALID_NONCE"
            )

        if claims.get("email_verified") is not True:
            raise UnauthorizedError(
                "Your Google account email is not verified",
                code="OAUTH_EMAIL_UNVERIFIED",
            )

        email = str(claims["email"]).strip().lower()
        name = str(claims.get("name") or email.split("@")[0]).strip()
        return GoogleVerifiedIdentity(
            provider_user_id=str(claims["sub"]),
            email=email,
            email_verified=True,
            name=name[:80] if len(name) >= 2 else "BeanBox Member",
        )
