"""
Runtime wiring & admin observability helper (`CacheRuntime`) combining Redis and
in-memory/no-op components plus safe bounded SCAN statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import redis

from app.cache.catalog_cache import InMemoryCatalogCache, RedisCatalogCache
from app.cache.connection import ping_redis, resolve_redis_client
from app.cache.idempotency import NoopIdempotencyStore, RedisIdempotencyStore
from app.cache.interfaces import (
    CatalogCache,
    IdempotencyStore,
    RateLimiter,
    SessionCache,
)
from app.cache.keys import key_prefix, stat_counter_key
from app.cache.rate_limiter import InMemoryRateLimiter, RedisRateLimiter
from app.cache.session_cache import NoopSessionCache, RedisSessionCache
from app.config import Settings

MAX_SCAN_ITERATIONS = 100
SCAN_COUNT_HINT = 100
MAX_KEYS_SCANNED = 5000


@dataclass
class CacheRuntime:
    enabled: bool
    app_env: str
    redis_client: Optional[redis.Redis]
    redis_pool: Optional[redis.ConnectionPool]
    rate_limiter: RateLimiter
    fallback_rate_limiter: InMemoryRateLimiter
    catalog_cache: CatalogCache
    session_cache: SessionCache
    idempotency_store: IdempotencyStore

    def health(self) -> dict[str, Any]:
        return ping_redis(self.redis_client, self.enabled)

    def close(self) -> None:
        if self.redis_pool is not None:
            self.redis_pool.disconnect()

    def collect_admin_stats(self) -> dict[str, Any]:
        """
        Collects observability metrics using `MGET` for counters, `INFO memory` for RAM,
        and bounded `SCAN` (with prefix + count cap, never `KEYS *`) for domain breakdown.
        """
        if not self.enabled or self.redis_client is None:
            in_mem_hits = (
                self.catalog_cache.hits
                if isinstance(self.catalog_cache, InMemoryCatalogCache)
                else 0
            )
            in_mem_misses = (
                self.catalog_cache.misses
                if isinstance(self.catalog_cache, InMemoryCatalogCache)
                else 0
            )
            total = in_mem_hits + in_mem_misses
            return {
                "enabled": False,
                "connected": False,
                "hits": in_mem_hits,
                "misses": in_mem_misses,
                "hitRatio": round(in_mem_hits / total, 4) if total else 0.0,
                "rateLimitBlocks": 0,
                "idempotentReplays": 0,
                "memoryUsedBytes": 0,
                "memoryUsedHuman": "0B",
                "totalKeys": 0,
                "keysByDomain": {},
                "scanTruncated": False,
            }

        try:
            counter_keys = [
                stat_counter_key(self.app_env, "cache_hits"),
                stat_counter_key(self.app_env, "cache_misses"),
                stat_counter_key(self.app_env, "ratelimit_blocks"),
                stat_counter_key(self.app_env, "idempotent_replays"),
            ]
            raw_counts = self.redis_client.mget(counter_keys)
            hits = int(raw_counts[0] or 0)
            misses = int(raw_counts[1] or 0)
            rate_blocks = int(raw_counts[2] or 0)
            idem_replays = int(raw_counts[3] or 0)
            total_reqs = hits + misses
            hit_ratio = round(hits / total_reqs, 4) if total_reqs else 0.0

            mem_bytes = 0
            mem_human = "0B"
            try:
                mem_info = self.redis_client.info("memory") or {}
                mem_bytes = int(mem_info.get("used_memory") or 0)
                mem_human = str(mem_info.get("used_memory_human") or f"{mem_bytes}B")
            except redis.ResponseError:
                pass

            prefix = key_prefix(self.app_env)
            keys_by_domain: dict[str, int] = {}
            total_keys = 0
            scan_truncated = False

            cursor: int | str = 0
            iterations = 0
            while True:
                cursor, batch = self.redis_client.scan(
                    cursor=cursor, match=f"{prefix}*", count=SCAN_COUNT_HINT
                )
                iterations += 1
                for k in batch:
                    total_keys += 1
                    rest = k[len(prefix) :] if k.startswith(prefix) else k
                    domain = rest.split(":", 1)[0] or "other"
                    keys_by_domain[domain] = keys_by_domain.get(domain, 0) + 1
                if cursor == 0 or cursor == "0":
                    break
                if iterations >= MAX_SCAN_ITERATIONS or total_keys >= MAX_KEYS_SCANNED:
                    scan_truncated = True
                    break

            return {
                "enabled": True,
                "connected": True,
                "hits": hits,
                "misses": misses,
                "hitRatio": hit_ratio,
                "rateLimitBlocks": rate_blocks,
                "idempotentReplays": idem_replays,
                "memoryUsedBytes": mem_bytes,
                "memoryUsedHuman": mem_human,
                "totalKeys": total_keys,
                "keysByDomain": keys_by_domain,
                "scanTruncated": scan_truncated,
            }
        except redis.RedisError:
            return {
                "enabled": True,
                "connected": False,
                "hits": 0,
                "misses": 0,
                "hitRatio": 0.0,
                "rateLimitBlocks": 0,
                "idempotentReplays": 0,
                "memoryUsedBytes": 0,
                "memoryUsedHuman": "unavailable",
                "totalKeys": 0,
                "keysByDomain": {},
                "scanTruncated": False,
            }


def create_cache_runtime(
    settings: Settings,
    redis_client: Optional[redis.Redis] = None,
) -> CacheRuntime:
    client, pool, enabled = resolve_redis_client(settings, redis_client=redis_client)
    fallback_limiter = InMemoryRateLimiter()

    if enabled and client is not None:
        return CacheRuntime(
            enabled=True,
            app_env=settings.app_env,
            redis_client=client,
            redis_pool=pool,
            rate_limiter=RedisRateLimiter(
                client=client,
                app_env=settings.app_env,
                fallback=fallback_limiter,
            ),
            fallback_rate_limiter=fallback_limiter,
            catalog_cache=RedisCatalogCache(client=client, app_env=settings.app_env),
            session_cache=RedisSessionCache(client=client, app_env=settings.app_env),
            idempotency_store=RedisIdempotencyStore(
                client=client, app_env=settings.app_env
            ),
        )

    return CacheRuntime(
        enabled=False,
        app_env=settings.app_env,
        redis_client=None,
        redis_pool=None,
        rate_limiter=fallback_limiter,
        fallback_rate_limiter=fallback_limiter,
        catalog_cache=InMemoryCatalogCache(enabled=False),
        session_cache=NoopSessionCache(),
        idempotency_store=NoopIdempotencyStore(),
    )
