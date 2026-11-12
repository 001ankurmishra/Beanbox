"""
Public catalog cache-aside layer with namespace-version invalidation and
SET NX EX stampede locking.

IMPORTANT SECURITY INVARIANT:
Catalog caching is ONLY used for public read endpoints (`GET /api/products` and
`GET /api/products/{slug}`). Cart hydration, checkout preview, stock reservation,
and order creation NEVER read from this cache; they always query the primary
database directly for authoritative prices and stock.
"""

from __future__ import annotations

import json
import logging
import time
from threading import RLock
from typing import Any, Callable, Optional
from uuid import uuid4

import redis
from fastapi.encoders import jsonable_encoder

from app.cache.connection import shared_redis_warnings
from app.cache.interfaces import CatalogCache
from app.cache.keys import (
    CATALOG_VERSION_TTL_SECONDS,
    PRODUCTS_DETAIL_TTL_SECONDS,
    PRODUCTS_LIST_TTL_SECONDS,
    STAMPEDE_LOCK_TTL_SECONDS,
    STATS_COUNTER_TTL_SECONDS,
    hash_normalized_query,
    products_detail_key,
    products_list_key,
    products_version_key,
    stampede_lock_key,
    stat_counter_key,
)
from app.models.domain import Product
from app.repositories.interfaces import ProductListQuery
from app.schemas.common import PaginationMeta

logger = logging.getLogger("beanbox.cache")

_RELEASE_LOCK_LUA = """
-- Only release the stampede lock if we still own the random lock token
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


def _normalize_list_query(query: ProductListQuery) -> str:
    payload = {
        "search": (query.search or "").strip().lower(),
        "category": query.category,
        "roast": query.roast,
        "origin": (query.origin or "").strip().lower(),
        "min_price_paise": query.min_price_paise,
        "max_price_paise": query.max_price_paise,
        "in_stock_only": query.in_stock_only,
        "featured_only": query.featured_only,
        "include_inactive": query.include_inactive,
        "sort": query.sort,
        "page": query.page,
        "limit": query.limit,
    }
    return hash_normalized_query(payload)


def _serialize_list_result(result: dict[str, Any]) -> str:
    return json.dumps(jsonable_encoder(result), separators=(",", ":"))


def _deserialize_list_result(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    return {
        "items": [Product.model_validate(p) for p in data["items"]],
        "pagination": PaginationMeta.model_validate(data["pagination"]),
        "facets": data["facets"],
    }


class InMemoryCatalogCache(CatalogCache):
    """
    Simple versioned in-memory catalog cache (no external Redis required).
    Used as local fallback or when Redis is disabled.
    """

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self._lock = RLock()
        self._version = 1
        self._entries: dict[str, tuple[float, str]] = {}
        self.hits = 0
        self.misses = 0

    def get_or_set_list(
        self,
        query: ProductListQuery,
        loader: Callable[[], dict[str, Any]],
        request_id: str = "-",
    ) -> tuple[dict[str, Any], bool]:
        if not self._enabled:
            return loader(), False
        key = f"list:v{self._version}:{_normalize_list_query(query)}"
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > now:
                self.hits += 1
                return _deserialize_list_result(cached[1]), True
        fresh = loader()
        with self._lock:
            self.misses += 1
            self._entries[key] = (
                time.monotonic() + PRODUCTS_LIST_TTL_SECONDS,
                _serialize_list_result(fresh),
            )
        return fresh, False

    def get_or_set_detail(
        self,
        slug: str,
        loader: Callable[[], Product],
        request_id: str = "-",
    ) -> tuple[Product, bool]:
        if not self._enabled:
            return loader(), False
        key = f"detail:v{self._version}:{slug}"
        now = time.monotonic()
        with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > now:
                self.hits += 1
                return Product.model_validate_json(cached[1]), True
        fresh = loader()
        with self._lock:
            self.misses += 1
            self._entries[key] = (
                time.monotonic() + PRODUCTS_DETAIL_TTL_SECONDS,
                json.dumps(jsonable_encoder(fresh), separators=(",", ":")),
            )
        return fresh, False

    def invalidate_catalog(self, reason: str) -> None:
        with self._lock:
            self._version += 1
            self._entries.clear()


class RedisCatalogCache(CatalogCache):
    """
    Redis cache-aside implementation with:
    - Namespace version keys (`beanbox:{env}:cache:products:ver`) so invalidation
      is O(1) via `INCR` (never `KEYS` or `SCAN`-delete)
    - Stampede mutex (`SET NX EX 5`) so concurrent misses collapse to 1 DB query
    - 7-day TTL hit/miss counters (`INCR`) and structured logs
    """

    def __init__(
        self,
        client: redis.Redis,
        app_env: str,
        stampede_wait_seconds: float = 1.5,
    ) -> None:
        self._client = client
        self._app_env = app_env
        self._stampede_wait_seconds = stampede_wait_seconds
        self._release_lock_script = self._client.register_script(_RELEASE_LOCK_LUA)

    def _get_or_init_version(self) -> int:
        vkey = products_version_key(self._app_env)
        val = self._client.get(vkey)
        if val is None:
            self._client.set(vkey, "1", nx=True, ex=CATALOG_VERSION_TTL_SECONDS)
            val = self._client.get(vkey) or "1"
        return int(val)

    def _incr_stat(self, metric: str) -> None:
        try:
            skey = stat_counter_key(self._app_env, metric)
            pipe = self._client.pipeline()
            pipe.incr(skey)
            pipe.expire(skey, STATS_COUNTER_TTL_SECONDS)
            pipe.execute()
        except redis.RedisError:
            pass

    def _fetch_with_stampede_protection(
        self,
        cache_key: str,
        ttl_seconds: int,
        serialize: Callable[[Any], str],
        deserialize: Callable[[str], Any],
        loader: Callable[[], Any],
        request_id: str,
    ) -> tuple[Any, bool]:
        try:
            cached_raw = self._client.get(cache_key)
            if cached_raw is not None:
                self._incr_stat("cache_hits")
                logger.info("cache=HIT key=%s req=%s", cache_key, request_id)
                return deserialize(cached_raw), True

            lkey = stampede_lock_key(self._app_env, cache_key)
            lock_token = uuid4().hex
            acquired = self._client.set(
                lkey, lock_token, nx=True, ex=STAMPEDE_LOCK_TTL_SECONDS
            )

            if acquired:
                try:
                    # Double-check in case another writer filled right before lock
                    second_read = self._client.get(cache_key)
                    if second_read is not None:
                        self._incr_stat("cache_hits")
                        logger.info("cache=HIT key=%s req=%s", cache_key, request_id)
                        return deserialize(second_read), True

                    self._incr_stat("cache_misses")
                    logger.info("cache=MISS key=%s req=%s", cache_key, request_id)
                    fresh = loader()
                    self._client.set(cache_key, serialize(fresh), ex=ttl_seconds)
                    return fresh, False
                finally:
                    try:
                        self._release_lock_script(keys=[lkey], args=[lock_token])
                    except redis.RedisError:
                        pass
            else:
                # Another request holds the stampede lock; wait briefly and re-read cache.
                deadline = time.monotonic() + self._stampede_wait_seconds
                while time.monotonic() < deadline:
                    time.sleep(0.02)
                    waited_raw = self._client.get(cache_key)
                    if waited_raw is not None:
                        self._incr_stat("cache_hits")
                        logger.info(
                            "cache=HIT waited=true key=%s req=%s",
                            cache_key,
                            request_id,
                        )
                        return deserialize(waited_raw), True

                # Stampede lock expired or holder failed: fall back cleanly to DB.
                self._incr_stat("cache_misses")
                logger.info(
                    "cache=MISS fallback=timeout key=%s req=%s", cache_key, request_id
                )
                return loader(), False
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "catalog_cache",
                "Redis catalog cache error (%s); bypassing cache directly to DB.",
                exc.__class__.__name__,
            )
            return loader(), False

    def get_or_set_list(
        self,
        query: ProductListQuery,
        loader: Callable[[], dict[str, Any]],
        request_id: str = "-",
    ) -> tuple[dict[str, Any], bool]:
        try:
            ver = self._get_or_init_version()
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "catalog_cache",
                "Redis catalog version lookup failed (%s); bypassing cache directly to DB.",
                exc.__class__.__name__,
            )
            return loader(), False

        ckey = products_list_key(self._app_env, ver, _normalize_list_query(query))
        return self._fetch_with_stampede_protection(
            cache_key=ckey,
            ttl_seconds=PRODUCTS_LIST_TTL_SECONDS,
            serialize=_serialize_list_result,
            deserialize=_deserialize_list_result,
            loader=loader,
            request_id=request_id,
        )

    def get_or_set_detail(
        self,
        slug: str,
        loader: Callable[[], Product],
        request_id: str = "-",
    ) -> tuple[Product, bool]:
        try:
            ver = self._get_or_init_version()
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "catalog_cache",
                "Redis catalog version lookup failed (%s); bypassing cache directly to DB.",
                exc.__class__.__name__,
            )
            return loader(), False

        ckey = products_detail_key(self._app_env, ver, slug)
        return self._fetch_with_stampede_protection(
            cache_key=ckey,
            ttl_seconds=PRODUCTS_DETAIL_TTL_SECONDS,
            serialize=lambda prod: json.dumps(
                jsonable_encoder(prod), separators=(",", ":")
            ),
            deserialize=Product.model_validate_json,
            loader=loader,
            request_id=request_id,
        )

    def invalidate_catalog(self, reason: str) -> None:
        vkey = products_version_key(self._app_env)
        try:
            pipe = self._client.pipeline()
            pipe.incr(vkey)
            pipe.expire(vkey, CATALOG_VERSION_TTL_SECONDS)
            new_ver = pipe.execute()[0]
            logger.info("catalog=INVALIDATE reason=%s ver=%s", reason, new_ver)
        except redis.RedisError as exc:
            shared_redis_warnings.warn(
                "catalog_invalidate",
                "Redis catalog version bump failed on %s (%s).",
                reason,
                exc.__class__.__name__,
            )


def safe_deserialize_cached_product(raw: str) -> Optional[Product]:
    try:
        return Product.model_validate_json(raw)
    except Exception:
        return None
