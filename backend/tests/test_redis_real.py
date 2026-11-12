from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Iterator

import pytest
import redis

from app.cache.keys import key_prefix
from app.cache.rate_limiter import RedisRateLimiter
from app.main import create_app
from app.repositories import create_in_memory_repositories
from tests.conftest import (
    make_test_settings,
    new_client,
    signup_verified_client,
    sync_csrf,
)

pytestmark = pytest.mark.redis


@pytest.fixture
def real_redis() -> Iterator[redis.Redis]:
    url = os.environ.get("REDIS_URL_TEST", "").strip()
    if not url:
        pytest.skip("REDIS_URL_TEST is not set; skipping real-Redis tests")

    client = redis.Redis.from_url(
        url,
        socket_timeout=2,
        socket_connect_timeout=2,
        health_check_interval=30,
        decode_responses=True,
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        pytest.fail(f"REDIS_URL_TEST is set ({url}) but ping failed: {exc}")

    # Clean only the beanbox:test:* namespace before and after each test
    for k in client.scan_iter(match=f"{key_prefix('test')}*", count=200):
        client.delete(k)
    try:
        yield client
    finally:
        for k in client.scan_iter(match=f"{key_prefix('test')}*", count=200):
            client.delete(k)
        client.close()


def _create_address(client) -> str:
    sync_csrf(client)
    res = client.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": "Real Redis Buyer",
            "phone": "9811111111",
            "line1": "24 Church Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560001",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["address"]["id"]


def test_real_redis_sliding_window_50_parallel_threads_and_lua_atomicity(
    real_redis: redis.Redis,
) -> None:
    limiter = RedisRateLimiter(real_redis, app_env="test")
    barrier = Barrier(50, timeout=5)

    def hit(_idx: int) -> bool:
        barrier.wait()
        return limiter.check("login:parallel-ip", limit=15, window_seconds=60).allowed

    with ThreadPoolExecutor(max_workers=50) as pool:
        results = list(pool.map(hit, range(50)))

    assert results.count(True) == 15
    assert results.count(False) == 35


def test_real_redis_cache_version_invalidation_and_stampede_lock(
    real_redis: redis.Redis,
) -> None:
    repos = create_in_memory_repositories()
    db_calls = 0
    orig_find = repos.products.find_by_slug

    def slow_find(slug: str):
        nonlocal db_calls
        db_calls += 1
        time.sleep(0.15)
        return orig_find(slug)

    repos.products.find_by_slug = slow_find
    app = create_app(
        settings=make_test_settings(REDIS_URL_TEST=os.environ["REDIS_URL_TEST"]),
        repos=repos,
    )

    barrier = Barrier(20, timeout=10)

    def fetch(_idx: int) -> tuple[int, str]:
        c = new_client(app)
        barrier.wait()
        res = c.get("/api/products/chikmagalur-baba-budangiri-arabica")
        return res.status_code, res.headers["X-Cache"]

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(fetch, range(20)))

    assert all(code == 200 for code, _ in results)
    assert db_calls == 1
    assert [xc for _, xc in results].count("MISS") == 1
    assert [xc for _, xc in results].count("HIT") == 19

    # Bumping version invalidates cached detail immediately
    ver_before = int(real_redis.get(f"{key_prefix('test')}cache:products:ver") or "1")
    app.state.cache.catalog_cache.invalidate_catalog("real_redis_test")
    ver_after = int(real_redis.get(f"{key_prefix('test')}cache:products:ver") or "0")
    assert ver_after == ver_before + 1
    assert new_client(app).get(
        "/api/products/chikmagalur-baba-budangiri-arabica"
    ).headers["X-Cache"] == "MISS"


def test_real_redis_session_revocation_parallel_idempotency_and_ttls(
    real_redis: redis.Redis,
) -> None:
    app = create_app(
        settings=make_test_settings(REDIS_URL_TEST=os.environ["REDIS_URL_TEST"])
    )
    buyer = signup_verified_client(
        app, "Real Redis User", "real-redis@beanbox-test.in", "RealRedis@123!"
    )
    addr_id = _create_address(buyer)
    assert (
        buyer.post(
            "/api/cart/items",
            json={
                "productId": "prod-chikmagalur-arabica",
                "variantId": "chik-250-wb",
                "quantity": 1,
            },
        ).status_code
        == 201
    )

    # Parallel same-key order creation creates exactly 1 order
    idem_key = "real-redis-idem-001"
    barrier = Barrier(8, timeout=5)

    def submit_order(_idx: int) -> int:
        c = new_client(app)
        c.cookies.update(buyer.cookies)
        sync_csrf(c)
        barrier.wait()
        return c.post(
            "/api/orders",
            headers={"Idempotency-Key": idem_key},
            json={"addressId": addr_id},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(submit_order, range(8)))

    assert statuses.count(201) >= 1
    assert all(s in (201, 409) for s in statuses)
    orders_list = buyer.get("/api/orders").json()["data"]["items"]
    assert len(orders_list) == 1

    # Session cache hit then immediate delete on logout
    assert buyer.get("/api/auth/me").status_code == 200
    token = buyer.cookies.get("beanbox_access")
    sync_csrf(buyer)
    assert buyer.post("/api/auth/logout").status_code == 200
    assert (
        new_client(app)
        .get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        .status_code
        == 401
    )

    # Every key in Redis under beanbox:test:* must have TTL > 0
    all_keys = list(real_redis.scan_iter(match=f"{key_prefix('test')}*", count=200))
    assert all_keys
    for k in all_keys:
        assert real_redis.ttl(k) > 0, f"Key {k} has no TTL!"
