from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = Field(default=4000, alias="PORT")
    app_env: Literal["development", "test", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")
    trusted_proxy_count: int = Field(
        default=0, alias="TRUSTED_PROXY_COUNT", ge=0, le=10
    )
    cookie_secure: Literal["auto", "true", "false"] = Field(
        default="auto", alias="COOKIE_SECURE"
    )

    jwt_secret: str = Field(
        default="beanbox-dev-jwt-secret-change-in-production-32chars",
        alias="JWT_SECRET",
        min_length=16,
    )
    access_token_expires_minutes: int = Field(
        default=15, alias="ACCESS_TOKEN_EXPIRES_MINUTES", ge=1, le=120
    )
    refresh_token_expires_days: int = Field(
        default=30, alias="REFRESH_TOKEN_EXPIRES_DAYS", ge=1, le=365
    )
    refresh_grace_seconds: int = Field(
        default=10, alias="REFRESH_GRACE_SECONDS", ge=0, le=60
    )
    totp_encryption_key: str = Field(default="", alias="TOTP_ENCRYPTION_KEY")

    google_client_id: str = Field(default="", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(default="", alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:4000/api/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )

    # Brute-force & rate limit configuration
    login_max_failures: int = Field(default=5, alias="LOGIN_MAX_FAILURES", ge=1, le=20)
    login_lock_base_minutes: int = Field(
        default=15, alias="LOGIN_LOCK_BASE_MINUTES", ge=1, le=1440
    )
    rate_limit_login_max: int = Field(default=15, alias="RATE_LIMIT_LOGIN_MAX", ge=1)
    rate_limit_signup_max: int = Field(default=5, alias="RATE_LIMIT_SIGNUP_MAX", ge=1)
    rate_limit_reset_max: int = Field(default=5, alias="RATE_LIMIT_RESET_MAX", ge=1)
    rate_limit_verify_resend_max: int = Field(
        default=3, alias="RATE_LIMIT_VERIFY_RESEND_MAX", ge=1
    )
    rate_limit_refresh_max: int = Field(
        default=30, alias="RATE_LIMIT_REFRESH_MAX", ge=1
    )
    rate_limit_2fa_max: int = Field(default=10, alias="RATE_LIMIT_2FA_MAX", ge=1)
    rate_limit_window_seconds: int = Field(
        default=900, alias="RATE_LIMIT_WINDOW_SECONDS", ge=1
    )

    payment_provider: Literal["auto", "stripe", "mock"] = Field(
        default="auto", alias="PAYMENT_PROVIDER"
    )
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    mock_webhook_secret: str = Field(
        default="beanbox-mock-webhook-secret-change-me",
        alias="MOCK_WEBHOOK_SECRET",
        min_length=8,
    )

    repository_backend: Literal["auto", "supabase", "memory"] = Field(
        default="auto", alias="REPOSITORY_BACKEND"
    )
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    database_url: str = Field(default="", alias="DATABASE_URL")

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id.strip() and self.google_client_secret.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
