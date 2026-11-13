import json
import os
import re
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import psycopg
import pyotp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repositories import create_supabase_repositories
from app.seed.seed_supabase import seed_supabase_database
from app.services.google_oauth_service import GoogleOAuthClient
from app.services.payment_service import sign_mock_webhook_payload


def make_test_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "PORT": 4000,
        "APP_ENV": "test",
        "CELERY_ALWAYS_EAGER": True,
        "REPOSITORY_BACKEND": "memory",
        "FRONTEND_URL": "http://localhost:3000",
        "JWT_SECRET": "test-jwt-secret-key-at-least-32-characters-long",
        "ACCESS_TOKEN_EXPIRES_MINUTES": 15,
        "REFRESH_TOKEN_EXPIRES_DAYS": 30,
        "REFRESH_GRACE_SECONDS": 10,
        "TOTP_ENCRYPTION_KEY": "test-totp-encryption-key-at-least-32-chars",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "RATE_LIMIT_LOGIN_MAX": 500,
        "RATE_LIMIT_SIGNUP_MAX": 500,
        "RATE_LIMIT_RESET_MAX": 500,
        "RATE_LIMIT_VERIFY_RESEND_MAX": 500,
        "RATE_LIMIT_REFRESH_MAX": 500,
        "RATE_LIMIT_2FA_MAX": 500,
        "PAYMENT_PROVIDER": "mock",
        "STRIPE_SECRET_KEY": "",
        "STRIPE_WEBHOOK_SECRET": "",
        "MOCK_WEBHOOK_SECRET": "test-mock-webhook-secret-1234",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def create_test_app(
    settings: Optional[Settings] = None,
    google_oauth_client: Optional[GoogleOAuthClient] = None,
) -> FastAPI:
    app = create_app(
        settings=settings or make_test_settings(),
        google_oauth_client=google_oauth_client,
    )
    set_worker_test_doubles(
        repos=app.state.repos,
        services=app.state.services,
        redis_client=getattr(app.state.cache, "redis_client", None),
    )
    return app


def new_client(app: FastAPI) -> TestClient:
    return TestClient(app)


def sync_csrf(client: TestClient) -> None:
    csrf = client.cookies.get("beanbox_csrf")
    if csrf:
        client.headers["X-CSRF-Token"] = csrf
    client.headers["Origin"] = app_origin_for_client(client)


def app_origin_for_client(client: TestClient) -> str:
    return getattr(client, "_beanbox_origin", "http://localhost:3000")


def extract_email_token(body: str) -> str:
    match = re.search(r"Token:\s*([A-Za-z0-9_\-]+)", body)
    assert match is not None, f"Token not found in email body: {body}"
    return match.group(1)


def set_worker_test_doubles(
    repos: Optional[Any] = None,
    services: Optional[Any] = None,
    redis_client: Optional[Any] = None,
) -> None:
    """Injects test doubles directly into Celery worker runtime for isolated test suites."""
    import sys

    import app.worker.celery_app  # noqa: F401

    worker_mod = sys.modules["app.worker.celery_app"]
    if repos is not None:
        worker_mod._worker_repos = repos
    if services is not None:
        worker_mod._worker_services = services
    if redis_client is not None:
        worker_mod._worker_redis_client = redis_client



def enable_2fa_for_logged_in_client(client: TestClient) -> tuple[str, list[str]]:
    sync_csrf(client)
    setup_res = client.post("/api/auth/2fa/setup")
    assert setup_res.status_code == 200, setup_res.text
    secret = setup_res.json()["data"]["secret"]
    code = pyotp.TOTP(secret).now()
    enable_res = client.post("/api/auth/2fa/enable", json={"code": code})
    assert enable_res.status_code == 200, enable_res.text
    return secret, enable_res.json()["data"]["recoveryCodes"]


def login_client(
    app: FastAPI,
    email: str,
    password: str,
    enable_admin_2fa: bool = True,
) -> TestClient:
    client = TestClient(app)
    client.headers["Origin"] = app.state.settings.frontend_url
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    sync_csrf(client)
    data = res.json()["data"]
    if enable_admin_2fa and not data.get("requiresTwoFactor"):
        user = data.get("user", {})
        if user.get("role") == "admin" and not user.get("totpEnabled"):
            enable_2fa_for_logged_in_client(client)
    return client


def signup_verified_client(
    app: FastAPI,
    name: str,
    email: str,
    password: str,
    phone: Optional[str] = None,
) -> TestClient:
    client = TestClient(app)
    client.headers["Origin"] = app.state.settings.frontend_url
    payload: dict[str, Any] = {"name": name, "email": email, "password": password}
    if phone:
        payload["phone"] = phone
    res = client.post("/api/auth/signup", json=payload)
    assert res.status_code == 201, res.text
    sync_csrf(client)

    verify_email = next(
        e
        for e in reversed(app.state.services.email_service.get_sent_emails())
        if e.type == "email_verification" and e.to == email.lower()
    )
    token = extract_email_token(verify_email.body)
    v_res = client.post("/api/auth/verify-email", json={"token": token})
    assert v_res.status_code == 200, v_res.text
    return client


def build_signed_webhook(secret: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode("utf-8")
    sig = sign_mock_webhook_payload(raw, secret)
    return raw, sig


def _assert_safe_local_test_dsn(dsn: str) -> None:
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").lower()
    if "supabase" in dsn.lower() or host not in {
        "localhost",
        "127.0.0.1",
        "postgres",
        "postgres_test",
        "beanbox-postgres-test",
    }:
        raise RuntimeError(
            f"Refusing to run destructive pg test reset on non-local database host '{host}'. "
            "Set DATABASE_URL_TEST to a local Docker/CI Postgres instance."
        )


@pytest.fixture
def pg_app() -> Iterator[FastAPI]:
    """
    Creates a FastAPI app backed by an isolated local Postgres database pointed to
    by DATABASE_URL_TEST (never reading .env's live Supabase DATABASE_URL).
    """
    test_dsn = os.environ.get("DATABASE_URL_TEST", "").strip()
    if not test_dsn:
        pytest.skip("DATABASE_URL_TEST is not set; skipping local Postgres tests")

    _assert_safe_local_test_dsn(test_dsn)

    supabase_dir = Path(__file__).resolve().parents[1] / "supabase"
    schema_sql = (supabase_dir / "schema.sql").read_text(encoding="utf-8")
    migration_files = sorted((supabase_dir / "migrations").glob("*.sql"))

    with psycopg.connect(test_dsn, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        conn.execute(schema_sql)
        for mig in migration_files:
            conn.execute(mig.read_text(encoding="utf-8"))

    seed_supabase_database(test_dsn, apply_schema=False)

    repos, pool = create_supabase_repositories(test_dsn)
    settings = make_test_settings(
        REPOSITORY_BACKEND="supabase",
        DATABASE_URL=test_dsn,
    )
    app = create_app(settings=settings, repos=repos)
    try:
        yield app
    finally:
        pool.close(timeout=2.0)
