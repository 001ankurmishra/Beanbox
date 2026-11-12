import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache.runtime import create_cache_runtime
from app.config import Settings, get_settings
from app.middleware import (
    SecurityAndLoggingMiddleware,
    register_exception_handlers,
)
from app.repositories import (
    create_in_memory_repositories,
    create_supabase_repositories,
)
from app.repositories.interfaces import Repositories
from app.routers import (
    addresses_router,
    admin_router,
    auth_router,
    cart_router,
    checkout_router,
    orders_router,
    payments_router,
    products_router,
    reviews_router,
    wishlist_router,
)
from app.services import Services, create_services
from app.services.email_service import EmailService
from app.services.google_oauth_service import GoogleOAuthClient
from app.services.payment_service import PaymentProvider
from app.utils.response import make_success_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("beanbox.boot")


def create_app(
    settings: Optional[Settings] = None,
    repos: Optional[Repositories] = None,
    email_service: Optional[EmailService] = None,
    payment_provider: Optional[PaymentProvider] = None,
    google_oauth_client: Optional[GoogleOAuthClient] = None,
    redis_client: Optional[redis.Redis] = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    is_test = app_settings.app_env == "test"

    if app_settings.app_env == "production" and not app_settings.totp_encryption_key.strip():
        logger.warning(
            "TOTP_ENCRYPTION_KEY is not set; falling back to HKDF key derived from JWT_SECRET."
        )

    pg_pool: Any = None
    backend_type = "memory"

    if repos is not None:
        app_repos = repos
    else:
        wants_supabase = app_settings.repository_backend == "supabase" or (
            app_settings.repository_backend == "auto"
            and bool(app_settings.database_url)
            and not is_test
        )
        if wants_supabase and app_settings.database_url:
            app_repos, pg_pool = create_supabase_repositories(
                app_settings.database_url
            )
            backend_type = "supabase"
        else:
            app_repos = create_in_memory_repositories()

    cache_runtime = create_cache_runtime(app_settings, redis_client=redis_client)

    app_services: Services = create_services(
        app_repos,
        app_settings,
        email_service=email_service,
        payment_provider=payment_provider,
        google_oauth_client=google_oauth_client,
        cache_runtime=cache_runtime,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if pg_pool is not None:
            pg_pool.close(timeout=2.0)
        cache_runtime.close()

    app = FastAPI(
        title="BeanBox Coffee E-Commerce API",
        version="2.0.0",
        description=(
            "Production-grade Python + FastAPI backend for BeanBox, an India-based "
            "specialty coffee store (short-lived httpOnly JWTs, rotating refresh tokens "
            "with reuse detection, Argon2id, double-submit CSRF, TOTP 2FA, Google OAuth PKCE)."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/docs.json",
        lifespan=lifespan,
    )

    app.state.settings = app_settings
    app.state.repos = app_repos
    app.state.services = app_services
    app.state.backend_type = backend_type
    app.state.cache = cache_runtime

    app.add_middleware(
        SecurityAndLoggingMiddleware,
        general_limiter=cache_runtime.rate_limiter,
        settings=app_settings,
        general_limit=5000 if is_test else 240,
        general_window_seconds=60,
        is_test=is_test,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_url],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-CSRF-Token",
            "X-Request-Id",
            "X-Guest-Session-Id",
        ],
        expose_headers=[
            "X-CSRF-Token",
            "X-Request-Id",
            "X-Cache",
            "Idempotent-Replay",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After",
        ],
    )

    register_exception_handlers(app, is_test=is_test)

    @app.get("/api/health", tags=["Health"])
    def health():
        return make_success_response(
            {
                "status": "ok",
                "service": "beanbox-fastapi",
                "repositoryBackend": backend_type,
                "paymentProvider": app_services.payment_provider.name,
                "redis": cache_runtime.health(),
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )

    app.include_router(auth_router)
    app.include_router(products_router)
    app.include_router(reviews_router)
    app.include_router(cart_router)
    app.include_router(addresses_router)
    app.include_router(checkout_router)
    app.include_router(orders_router)
    app.include_router(payments_router)
    app.include_router(wishlist_router)
    app.include_router(admin_router)

    return app


app = create_app()
