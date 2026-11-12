"""
Sliding-window rate limiter implementations:
1. InMemoryRateLimiter (fallback / test default without Redis)
2. RedisRateLimiter (atomic ZSET + single Lua script via SCRIPT LOAD / register_script)
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from threading import RLock
from typing import Optional
from uuid import uuid4

import redis

from app.cache.connection import shared_redis_warnings
from app.cache.interfaces import RateLimitCheckResult, RateLimiter
from app.cache.keys import (
    STATS_COUNTER_TTL_SECONDS,
    rate_limit_key,
    stat_counter_key,
)

logger = logging.getLogger("beanbox.ratelimit")

# One atomic sliding-window log Lua script.
# Registered once via register_script (Redis SCRIPT LOAD -> EVALSHA with auto-reload).
SLIDING_WINDOW_LUA = """
-- KEYS[1]: sorted-set key holding request timestamps in milliseconds
-- ARGV[1]: current wall-clock time in milliseconds
-- ARGV[2]: sliding window duration in milliseconds
-- ARGV[3]: max allowed requests inside the window
-- ARGV[4]: unique member string so parallel requests in the same ms remain distinct
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

-- 1. Remove timestamps that have slid out of the active window
local cutoff = now_ms - window_ms
redis.call("ZREMRANGEBYSCORE", key, "-inf", cutoff)

-- 2. Count remaining timestamps currently inside the window
local count = redis.call("ZCARD", key)

-- 3. Read the oldest retained entry to compute exact Unix epoch second when a slot opens
local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
local reset_ms = now_ms + window_ms
if oldest[2] ~= nil then
    reset_ms = tonumber(oldest[2]) + window_ms
end
local reset_at = math.ceil(reset_ms / 1000)

-- 4. Reject if already at or above the limit (do not insert rejected timestamps)
if count >= limit then
    -- Ensure even a saturated key always carries a TTL
    redis.call("PEXPIRE", key, window_ms)
    return {0, 0, reset_at}
end

-- 5. Add the current request timestamp and refresh TTL so idle buckets auto-expire
redis.call("ZADD", key, now_ms, member)
redis.call("PEXPIRE", key, window_ms)
local remaining = limit - count - 1
return {1, remaining, reset_at}
"""


class InMemoryRateLimiter(RateLimiter):
    """Thread-safe sliding-window log rate limiter backed by process memory."""

    def __init__(self, max_requests: int = 15, window_seconds: int = 900) -> None:
        self._default_max_requests = max_requests
        self._default_window_seconds = window_seconds
        self._lock = RLock()
        self._buckets: dict[str, deque[float]] = {}

    def check(
        self, key: str, limit: int, window_seconds: int
    ) -> RateLimitCheckResult:
        now_epoch = time.time()
        cutoff = now_epoch - window_seconds
        with self._lock:
            dq = self._buckets.setdefault(key, deque())
            while dq and dq[0] <= cutoff:
                dq.popleft()
            oldest = dq[0] if dq else now_epoch
            reset_at = math.ceil(oldest + window_seconds)
            if len(dq) >= limit:
                return RateLimitCheckResult(
                    allowed=False, remaining=0, reset_at=reset_at
                )
            dq.append(now_epoch)
            return RateLimitCheckResult(
                allowed=True,
                remaining=max(0, limit - len(dq)),
                reset_at=reset_at,
            )

    def allow(self, key: str) -> bool:
        """Backward-compatible helper using the default configured limit & window."""
        return self.check(
            key, self._default_max_requests, self._default_window_seconds
        ).allowed


class RedisRateLimiter(RateLimiter):
    """
    Atomic Redis ZSET sliding-window rate limiter with transparent in-memory
    fallback if Redis becomes unreachable.
    """

    def __init__(
        self,
        client: redis.Redis,
        app_env: str,
        fallback: Optional[InMemoryRateLimiter] = None,
    ) -> None:
        self._client = client
        self._app_env = app_env
        self._fallback = fallback or InMemoryRateLimiter()
        self._script = self._client.register_script(SLIDING_WINDOW_LUA)

    @staticmethod
    def _split_bucket_key(raw_key: str) -> tuple[str, str]:
        if ":" in raw_key:
            bucket, subject = raw_key.split(":", 1)
            return bucket, subject
        return "default", raw_key

    def _record_block_stat(self) -> None:
        try:
            stat_key = stat_counter_key(self._app_env, "ratelimit_blocks")
            pipe = self._client.pipeline()
            pipe.incr(stat_key)
            pipe.expire(stat_key, STATS_COUNTER_TTL_SECONDS)
            pipe.execute()
        except redis.RedisError:
            pass

    def check(
        self, key: str, limit: int, window_seconds: int
    ) -> RateLimitCheckResult:
        bucket, subject = self._split_bucket_key(key)
        rkey = rate_limit_key(self._app_env, bucket, subject)
        now_ms = int(time.time() * 1000)
        window_ms = max(1, int(window_seconds)) * 1000
        member = f"{now_ms}:{uuid4().hex[:12]}"

        try:
            raw = self._script(
                keys=[rkey],
                args=[now_ms, window_ms, int(limit), member],
            )
            allowed = bool(int(raw[0]))
            remaining = max(0, int(raw[1]))
            reset_at = int(raw[2])
            if not allowed:
                self._record_block_stat()
            return RateLimitCheckResult(
                allowed=allowed, remaining=remaining, reset_at=reset_at
            )
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "ratelimit",
                "Redis rate-limiter failed (%s); falling back to in-memory limiter.",
                exc.__class__.__name__,
            )
            return self._fallback.check(key, limit, window_seconds)
