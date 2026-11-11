import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.middleware import (
    InMemoryRateLimiter,
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
from app.services.payment_service import PaymentProvider
from app.utils.response import make_success_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app(
    settings: Optional[Settings] = None,
    repos: Optional[Repositories] = None,
    email_service: Optional[EmailService] = None,
    payment_provider: Optional[PaymentProvider] = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    is_test = app_settings.app_env == "test"

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

    app_services: Services = create_services(
        app_repos,
        app_settings,
        email_service=email_service,
        payment_provider=payment_provider,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if pg_pool is not None:
            pg_pool.close(timeout=2.0)

    app = FastAPI(
        title="BeanBox Coffee E-Commerce API",
        version="1.0.0",
        description=(
            "Production-style Python + FastAPI backend for BeanBox, an India-based "
            "specialty coffee store (INR paise pricing, 5% GST, free shipping above ₹999, "
            "httpOnly JWT cookies, repository abstraction)."
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
    app.state.auth_limiter = InMemoryRateLimiter(
        max_requests=500 if is_test else 25,
        window_seconds=900,
    )

    general_limiter = InMemoryRateLimiter(
        max_requests=5000 if is_test else 240,
        window_seconds=60,
    )

    app.add_middleware(
        SecurityAndLoggingMiddleware,
        general_limiter=general_limiter,
        is_test=is_test,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
