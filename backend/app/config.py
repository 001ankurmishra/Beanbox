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

    jwt_secret: str = Field(
        default="beanbox-dev-jwt-secret-change-in-production-32chars",
        alias="JWT_SECRET",
        min_length=16,
    )
    jwt_expires_minutes: int = Field(default=60 * 24 * 7, alias="JWT_EXPIRES_MINUTES")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
