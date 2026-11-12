"""
Shared Redis ConnectionPool management and throttled error logging.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any, Optional

import redis

from app.config import Settings

logger = logging.getLogger("beanbox.redis")


class ThrottledWarningLogger:
    """Emits a warning at most once per `interval_seconds` per reason key."""

    def __init__(self, interval_seconds: float = 60.0) -> None:
        self._interval = interval_seconds
        self._lock = Lock()
        self._last_logged: dict[str, float] = {}

    def warn(self, key: str, message: str, *args: Any) -> None:
        now = time.monotonic()
        with self._lock:
            prev = self._last_logged.get(key)
            if prev is not None and (now - prev) < self._interval:
                return
            self._last_logged[key] = now
        logger.warning(message, *args)


shared_redis_warnings = ThrottledWarningLogger(interval_seconds=60.0)


def create_redis_pool(redis_url: str) -> redis.ConnectionPool:
    """
    Create one shared sync redis-py ConnectionPool with conservative network
    timeouts so Redis outages degrade quickly instead of stalling HTTP workers.
    """
    return redis.ConnectionPool.from_url(
        redis_url,
        socket_timeout=2,
        socket_connect_timeout=2,
        health_check_interval=30,
        decode_responses=True,
    )


def resolve_redis_client(
    settings: Settings,
    redis_client: Optional[redis.Redis] = None,
) -> tuple[Optional[redis.Redis], Optional[redis.ConnectionPool], bool]:
    """
    Decides whether Redis is active for this application instance:
    - Explicit injected client (e.g. fakeredis or real test client): enabled=True.
    - REDIS_ENABLED="false": disabled cleanly.
    - APP_ENV="test" with REDIS_ENABLED="auto": off unless REDIS_URL_TEST is set.
    - Otherwise builds one shared ConnectionPool (`REDIS_URL_TEST` or `REDIS_URL`).
      When REDIS_ENABLED="auto", checks PING at boot; if unreachable, logs a warning
      and disables Redis cleanly so local dev without Redis keeps working.
      When REDIS_ENABLED="true", keeps the client active even if Redis starts down so
      fallbacks engage and health reports `connected: false` until Redis recovers.
    """
    if redis_client is not None:
        return redis_client, None, True

    if settings.redis_enabled == "false":
        return None, None, False

    if (
        settings.app_env == "test"
        and settings.redis_enabled == "auto"
        and not settings.redis_url_test.strip()
    ):
        return None, None, False

    target_url = (
        settings.redis_url_test.strip()
        if settings.app_env == "test" and settings.redis_url_test.strip()
        else settings.redis_url.strip()
    )
    if not target_url:
        return None, None, False

    pool = create_redis_pool(target_url)
    client: redis.Redis = redis.Redis(connection_pool=pool)

    try:
        client.ping()
        return client, pool, True
    except redis.RedisError as exc:
        if settings.redis_enabled == "true":
            shared_redis_warnings.warn(
                "boot",
                "Redis enabled (%s) but initial PING failed (%s); falling back gracefully until reachable.",
                target_url,
                exc.__class__.__name__,
            )
            return client, pool, True
        logger.warning(
            "Redis unavailable at %s (%s); continuing with in-memory fallbacks.",
            target_url,
            exc.__class__.__name__,
        )
        pool.disconnect()
        return None, None, False


def ping_redis(client: Optional[redis.Redis], enabled: bool) -> dict[str, Any]:
    if not enabled or client is None:
        return {"enabled": False, "connected": False, "latencyMs": None}
    started = time.perf_counter()
    try:
        client.ping()
        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        return {"enabled": True, "connected": True, "latencyMs": latency_ms}
    except redis.RedisError:
        return {"enabled": True, "connected": False, "latencyMs": None}
