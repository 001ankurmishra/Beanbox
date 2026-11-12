"""
Short-lived session validity cache (`beanbox:{env}:session:active:{sid}`, TTL 30s).

TRADEOFF DOCUMENTATION:
- `require_user` caches ONLY that `session_id` is currently active (`"1"`) for 30s
  to avoid querying Postgres `sessions` on every API request.
- Every revocation path (`logout`, `logout_all`, `revoke_session`, `change_password`,
  `reset_password`, OAuth pre-hijack link, refresh token reuse / `revoke_family`,
  and admin `update_user_role`) IMMEDIATELY calls `invalidate(...)` to delete cached keys.
- If Redis DELETE fails during revocation, an error is logged; the 30-second TTL is the
  bounded worst-case revocation propagation delay.
- `require_role("admin")` STILL queries Postgres `users` directly on every admin call
  so role & 2FA changes take effect immediately and are never served from cache.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

import redis

from app.cache.connection import shared_redis_warnings
from app.cache.interfaces import SessionCache
from app.cache.keys import SESSION_ACTIVE_TTL_SECONDS, session_active_key

logger = logging.getLogger("beanbox.session_cache")


class NoopSessionCache(SessionCache):
    """Fallback used when Redis is disabled (every auth check goes straight to DB)."""

    def is_active(self, session_id: str) -> Optional[bool]:
        return None

    def mark_active(
        self, session_id: str, ttl_seconds: int = SESSION_ACTIVE_TTL_SECONDS
    ) -> None:
        return None

    def invalidate(self, session_ids: Iterable[str]) -> None:
        return None


class RedisSessionCache(SessionCache):
    """Caches active session IDs in Redis with a 30s TTL and eager invalidation."""

    def __init__(self, client: redis.Redis, app_env: str) -> None:
        self._client = client
        self._app_env = app_env

    def is_active(self, session_id: str) -> Optional[bool]:
        if not session_id:
            return None
        try:
            val = self._client.get(session_active_key(self._app_env, session_id))
            return True if val == "1" else None
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "session_cache_read",
                "Redis session cache read failed (%s); falling back to database.",
                exc.__class__.__name__,
            )
            return None

    def mark_active(
        self, session_id: str, ttl_seconds: int = SESSION_ACTIVE_TTL_SECONDS
    ) -> None:
        if not session_id:
            return
        try:
            self._client.set(
                session_active_key(self._app_env, session_id),
                "1",
                ex=ttl_seconds,
            )
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "session_cache_write",
                "Redis session cache write failed (%s).",
                exc.__class__.__name__,
            )

    def invalidate(self, session_ids: Iterable[str]) -> None:
        keys = [session_active_key(self._app_env, sid) for sid in session_ids if sid]
        if not keys:
            return
        try:
            self._client.delete(*keys)
        except redis.RedisError as exc:
            # Explicit error log per security spec: 30s TTL bounds revocation delay if delete fails.
            logger.error(
                "Failed to delete %d cached session key(s) from Redis (%s); "
                "worst-case revocation delay is %ds TTL.",
                len(keys),
                exc.__class__.__name__,
                SESSION_ACTIVE_TTL_SECONDS,
            )
