import logging
import secrets
import time
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.cache.interfaces import RateLimiter
from app.cache.rate_limiter import InMemoryRateLimiter  # noqa: F401
from app.config import Settings
from app.utils.response import make_error_payload
from app.utils.security import extract_client_ip

logger = logging.getLogger("beanbox.api")

STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_EXEMPT_PATHS = frozenset({"/api/payments/webhook"})


def _normalize_origin(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _validate_cookie_csrf(
    request: Request,
    settings: Settings,
    request_id: str,
) -> JSONResponse | None:
    if request.method not in STATE_CHANGING_METHODS:
        return None
    if not request.url.path.startswith("/api"):
        return None
    if request.url.path in CSRF_EXEMPT_PATHS:
        return None

    # Enforce CSRF + Origin whenever any auth cookie is present, even if Authorization: Bearer is also sent.
    uses_auth_cookies = bool(
        request.cookies.get("beanbox_access")
        or request.cookies.get("beanbox_refresh")
    )
    if not uses_auth_cookies:
        return None

    # Layer 1: Double-submit CSRF cookie vs X-CSRF-Token header
    csrf_cookie = request.cookies.get("beanbox_csrf") or ""
    csrf_header = request.headers.get("x-csrf-token") or ""
    if (
        len(csrf_cookie) < 16
        or len(csrf_header) < 16
        or not secrets.compare_digest(csrf_cookie, csrf_header)
    ):
        return JSONResponse(
            status_code=403,
            content=make_error_payload(
                "CSRF_TOKEN_INVALID",
                "Missing or invalid CSRF token",
                request_id=request_id,
            ),
            headers={"X-Request-Id": request_id},
        )

    # Layer 2: Strict Origin / Referer check
    allowed_origins = {_normalize_origin(settings.frontend_url)}
    if settings.app_env != "production":
        allowed_origins.update(
            {
                f"http://localhost:{settings.port}",
                f"http://127.0.0.1:{settings.port}",
                f"https://localhost:{settings.port}",
                f"https://127.0.0.1:{settings.port}",
            }
        )
    allowed_origins.discard("")

    origin = request.headers.get("origin")
    if origin is not None:
        if origin.strip().lower() == "null" or _normalize_origin(origin) not in allowed_origins:
            return JSONResponse(
                status_code=403,
                content=make_error_payload(
                    "CSRF_ORIGIN_INVALID",
                    "Untrusted request Origin",
                    request_id=request_id,
                ),
                headers={"X-Request-Id": request_id},
            )
    else:
        referer = request.headers.get("referer")
        if not referer:
            return JSONResponse(
                status_code=403,
                content=make_error_payload(
                    "CSRF_ORIGIN_MISSING",
                    "Missing Origin or Referer header on cookie-authenticated request",
                    request_id=request_id,
                ),
                headers={"X-Request-Id": request_id},
            )
        if _normalize_origin(referer) not in allowed_origins:
            return JSONResponse(
                status_code=403,
                content=make_error_payload(
                    "CSRF_ORIGIN_INVALID",
                    "Untrusted request Referer",
                    request_id=request_id,
                ),
                headers={"X-Request-Id": request_id},
            )

    return None


class SecurityAndLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        general_limiter: RateLimiter,
        settings: Settings,
        general_limit: int = 240,
        general_window_seconds: int = 60,
        is_test: bool = False,
    ) -> None:
        super().__init__(app)
        self._general_limiter = general_limiter
        self._settings = settings
        self._general_limit = general_limit
        self._general_window_seconds = general_window_seconds
        self._is_test = is_test

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id

        client_ip = extract_client_ip(request, self._settings)
        general_headers: dict[str, str] = {}
        if request.url.path.startswith("/api"):
            allowed, remaining, reset_at = self._general_limiter.check(
                f"general:{client_ip}",
                self._general_limit,
                self._general_window_seconds,
            )
            general_headers = {
                "X-RateLimit-Limit": str(self._general_limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_at),
            }
            if not allowed:
                retry_after = str(max(1, reset_at - int(time.time())))
                logger.warning(
                    "ratelimit=BLOCK bucket=general ip=%s path=%s req=%s",
                    client_ip,
                    request.url.path,
                    request_id,
                )
                return JSONResponse(
                    status_code=429,
                    content=make_error_payload(
                        "RATE_LIMIT_EXCEEDED",
                        "Too many requests. Please slow down and try again shortly.",
                        request_id=request_id,
                    ),
                    headers={
                        "X-Request-Id": request_id,
                        **general_headers,
                        "Retry-After": retry_after,
                    },
                )

        csrf_failure = _validate_cookie_csrf(request, self._settings, request_id)
        if csrf_failure is not None:
            return csrf_failure

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0

        # Apply endpoint-specific rate-limit headers if set (e.g. /auth/login), else general
        endpoint_rl = getattr(request.state, "rate_limit_headers", None)
        for hk, hv in (endpoint_rl or general_headers).items():
            if hk not in response.headers:
                response.headers[hk] = hv

        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        if not request.url.path.startswith(("/api/docs", "/api/redoc")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )

        if not self._is_test:
            # Never log query strings (may contain reset/verify/OAuth tokens), headers, or bodies
            logger.info(
                "%s %s %s %.1fms req=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )

        return response
