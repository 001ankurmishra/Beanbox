import json
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.payment_service import sign_mock_webhook_payload


def make_test_settings() -> Settings:
    return Settings(
        PORT=4000,
        APP_ENV="test",
        FRONTEND_URL="http://localhost:3000",
        JWT_SECRET="test-jwt-secret-key-at-least-32-characters-long",
        JWT_EXPIRES_MINUTES=1440,
        PAYMENT_PROVIDER="mock",
        STRIPE_SECRET_KEY="",
        STRIPE_WEBHOOK_SECRET="",
        MOCK_WEBHOOK_SECRET="test-mock-webhook-secret-1234",
    )


def create_test_app() -> FastAPI:
    return create_app(settings=make_test_settings())


def new_client(app: FastAPI) -> TestClient:
    return TestClient(app)


def login_client(app: FastAPI, email: str, password: str) -> TestClient:
    client = TestClient(app)
    res = client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return client


def build_signed_webhook(secret: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    raw = json.dumps(payload).encode("utf-8")
    sig = sign_mock_webhook_payload(raw, secret)
    return raw, sig
