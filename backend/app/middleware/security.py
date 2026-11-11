import logging
import time
from collections import deque
from threading import RLock
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.utils.response import make_error_payload

logger = logging.getLogger("beanbox.api")


class InMemoryRateLimiter:
    """Thread-safe sliding window rate limiter keyed by client IP and bucket."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._lock = RLock()
        self._buckets: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            dq = self._buckets.setdefault(key, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self._max_requests:
                return False
            dq.append(now)
            return True


class SecurityAndLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        general_limiter: InMemoryRateLimiter,
        is_test: bool = False,
    ) -> None:
        super().__init__(app)
        self._general_limiter = general_limiter
        self._is_test = is_test

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id

        client_ip = request.client.host if request.client else "unknown"
        if request.url.path.startswith("/api") and not self._general_limiter.allow(
            f"general:{client_ip}"
        ):
            return JSONResponse(
                status_code=429,
                content=make_error_payload(
                    "RATE_LIMIT_EXCEEDED",
                    "Too many requests. Please slow down and try again shortly.",
                    request_id=request_id,
                ),
                headers={"X-Request-Id": request_id},
            )

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0

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
            logger.info(
                "%s %s %s %.1fms req=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )

        return response
