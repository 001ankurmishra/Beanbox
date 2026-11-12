"""
Centralized Redis key naming and TTL definitions for BeanBox.

Every key in Redis follows the convention: `beanbox:{env}:{domain}:{id}`
where `{env}` is `APP_ENV` (`development`, `test`, or `production`).
Every key written by BeanBox MUST carry a TTL (no unbounded keys).
No tokens, passwords, or PII are ever stored in Redis.

| Key Pattern | Redis Type | TTL | Writer(s) | Reader(s) | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `beanbox:{env}:ratelimit:{bucket}:{subject}` | ZSET | `window_seconds` (60s or 900s) | `RedisRateLimiter` Lua script | `RedisRateLimiter` Lua script | Sliding-window request timestamps (`score=ms`, `member=ms:uuid`) |
| `beanbox:{env}:cache:products:ver` | STRING (int) | 7 days (`604800s`) | `RedisCatalogCache.invalidate_catalog` / lazy init | `RedisCatalogCache` | Namespace version incremented on any product/stock/order mutation |
| `beanbox:{env}:cache:products:list:v{ver}:{hash}` | STRING (JSON) | `60s` | `RedisCatalogCache.get_or_set_list` | `RedisCatalogCache.get_or_set_list` | Cached public `GET /api/products` response payload |
| `beanbox:{env}:cache:products:detail:v{ver}:{slug}` | STRING (JSON) | `300s` | `RedisCatalogCache.get_or_set_detail` | `RedisCatalogCache.get_or_set_detail` | Cached public `GET /api/products/{slug}` product payload |
| `beanbox:{env}:lock:{digest}` | STRING | `5s` | `RedisCatalogCache` (`SET NX EX 5`) | `RedisCatalogCache` | Short mutex preventing DB stampede on simultaneous cache misses |
| `beanbox:{env}:session:active:{sid}` | STRING (`"1"`) | `30s` | `require_user` via `RedisSessionCache` | `require_user` | Short-lived session validity flag; deleted immediately on revocation |
| `beanbox:{env}:idem:{user_id}:{route}:{key}` | STRING (JSON) | `86400s` (24h) | `RedisIdempotencyStore` | `RedisIdempotencyStore` | Single-use checkout/payment idempotency state (`in_progress` or response) |
| `beanbox:{env}:stats:cache_hits` | STRING (int) | `604800s` (7d) | `RedisCatalogCache` (`INCR`) | `/api/admin/cache-stats` | Cumulative catalog cache hit counter |
| `beanbox:{env}:stats:cache_misses` | STRING (int) | `604800s` (7d) | `RedisCatalogCache` (`INCR`) | `/api/admin/cache-stats` | Cumulative catalog cache miss counter |
| `beanbox:{env}:stats:ratelimit_blocks` | STRING (int) | `604800s` (7d) | `RedisRateLimiter` (`INCR`) | `/api/admin/cache-stats` | Cumulative 429 rate-limit block counter |
| `beanbox:{env}:stats:idempotent_replays` | STRING (int) | `604800s` (7d) | `RedisIdempotencyStore` (`INCR`) | `/api/admin/cache-stats` | Cumulative replayed idempotent checkout response counter |
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

PRODUCTS_LIST_TTL_SECONDS = 60
PRODUCTS_DETAIL_TTL_SECONDS = 300
CATALOG_VERSION_TTL_SECONDS = 7 * 86400
STAMPEDE_LOCK_TTL_SECONDS = 5
SESSION_ACTIVE_TTL_SECONDS = 30
IDEMPOTENCY_TTL_SECONDS = 86400
STATS_COUNTER_TTL_SECONDS = 7 * 86400


def key_prefix(app_env: str) -> str:
    return f"beanbox:{app_env}:"


def rate_limit_key(app_env: str, bucket: str, subject: str) -> str:
    return f"{key_prefix(app_env)}ratelimit:{bucket}:{subject}"


def products_version_key(app_env: str) -> str:
    return f"{key_prefix(app_env)}cache:products:ver"


def products_list_key(app_env: str, version: int, query_hash: str) -> str:
    return f"{key_prefix(app_env)}cache:products:list:v{version}:{query_hash}"


def products_detail_key(app_env: str, version: int, slug: str) -> str:
    return f"{key_prefix(app_env)}cache:products:detail:v{version}:{slug}"


def stampede_lock_key(app_env: str, target_key: str) -> str:
    digest = hashlib.sha256(target_key.encode("utf-8")).hexdigest()[:24]
    return f"{key_prefix(app_env)}lock:{digest}"


def session_active_key(app_env: str, session_id: str) -> str:
    return f"{key_prefix(app_env)}session:active:{session_id}"


def idempotency_key(app_env: str, user_id: str, route_tag: str, client_key: str) -> str:
    return f"{key_prefix(app_env)}idem:{user_id}:{route_tag}:{client_key}"


def stat_counter_key(app_env: str, metric: str) -> str:
    return f"{key_prefix(app_env)}stats:{metric}"


def hash_normalized_query(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
