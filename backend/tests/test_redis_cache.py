from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import fakeredis
import pyotp

from app.cache.keys import hash_normalized_query, key_prefix, rate_limit_key
from app.cache.rate_limiter import InMemoryRateLimiter, RedisRateLimiter
from app.main import create_app
from app.repositories import create_in_memory_repositories
from tests.conftest import (
    login_client,
    make_test_settings,
    new_client,
    signup_verified_client,
    sync_csrf,
)


def _make_fakeredis() -> fakeredis.FakeRedis:
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


def _create_address(client, name: str = "Redis Buyer") -> str:
    sync_csrf(client)
    res = client.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": name,
            "phone": "9811111111",
            "line1": "24 Church Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560001",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["address"]["id"]


def test_fakeredis_rate_limiter_sliding_window_headers_and_429() -> None:
    r = _make_fakeredis()
    app = create_app(
        settings=make_test_settings(
            RATE_LIMIT_LOGIN_MAX=3,
            RATE_LIMIT_WINDOW_SECONDS=60,
        ),
        redis_client=r,
    )
    client = new_client(app)

    for expected_rem in (2, 1, 0):
        res = client.post(
            "/api/auth/login",
            json={"email": "nobody@beanbox-test.in", "password": "WrongPassword@123!"},
        )
        assert res.status_code == 401
        assert res.headers["X-RateLimit-Limit"] == "3"
        assert res.headers["X-RateLimit-Remaining"] == str(expected_rem)
        assert int(res.headers["X-RateLimit-Reset"]) >= int(time.time())

    blocked = client.post(
        "/api/auth/login",
        json={"email": "nobody@beanbox-test.in", "password": "WrongPassword@123!"},
    )
    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Limit"] == "3"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert int(blocked.headers["Retry-After"]) >= 1

    # Verify ZSET key exists and has a positive TTL
    zset_key = rate_limit_key("test", "login", "testclient")
    assert r.zcard(zset_key) == 3
    assert r.ttl(zset_key) > 0


def test_fakeredis_catalog_cache_hit_miss_version_invalidation() -> None:
    r = _make_fakeredis()
    app = create_app(settings=make_test_settings(), redis_client=r)
    client = new_client(app)

    # First list request -> MISS; identical list (with different param order / whitespace) -> HIT
    r1 = client.get("/api/products?category=beans&page=1")
    assert r1.status_code == 200
    assert r1.headers["X-Cache"] == "MISS"

    r2 = client.get("/api/products?page=1&category=beans")
    assert r2.status_code == 200
    assert r2.headers["X-Cache"] == "HIT"
    assert r2.json() == r1.json()

    # Detail MISS -> HIT
    d1 = client.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert d1.status_code == 200
    assert d1.headers["X-Cache"] == "MISS"

    d2 = client.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert d2.status_code == 200
    assert d2.headers["X-Cache"] == "HIT"

    # Admin updates variant inventory -> increments namespace version -> next read is MISS with fresh price/stock
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin)
    upd = admin.patch(
        "/api/admin/inventory/prod-chikmagalur-arabica/chik-250-wb",
        json={"stock": 42, "pricePaise": 52500},
    )
    assert upd.status_code == 200

    d3 = client.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert d3.status_code == 200
    assert d3.headers["X-Cache"] == "MISS"
    updated_var = next(
        v for v in d3.json()["data"]["product"]["variants"] if v["id"] == "chik-250-wb"
    )
    assert updated_var["stock"] == 42
    assert updated_var["pricePaise"] == 52500

    # Order creation + cancel both bump cache version so stock stays fresh
    buyer = signup_verified_client(
        app, "Cache Buyer", "cache-buyer@beanbox-test.in", "CacheBuyer@123!"
    )
    addr_id = _create_address(buyer, "Cache Buyer")
    assert (
        buyer.post(
            "/api/cart/items",
            json={
                "productId": "prod-chikmagalur-arabica",
                "variantId": "chik-250-wb",
                "quantity": 2,
            },
        ).status_code
        == 201
    )
    order_res = buyer.post("/api/orders", json={"addressId": addr_id})
    assert order_res.status_code == 201
    d4 = client.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert d4.headers["X-Cache"] == "MISS"
    assert (
        next(
            v for v in d4.json()["data"]["product"]["variants"] if v["id"] == "chik-250-wb"
        )["stock"]
        == 40
    )

    order_id = order_res.json()["data"]["order"]["id"]
    assert buyer.post(f"/api/orders/{order_id}/cancel", json={}).status_code == 200
    d5 = client.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert d5.headers["X-Cache"] == "MISS"
    assert (
        next(
            v for v in d5.json()["data"]["product"]["variants"] if v["id"] == "chik-250-wb"
        )["stock"]
        == 42
    )


def test_fakeredis_stampede_protection_collapses_20_parallel_misses() -> None:
    r = _make_fakeredis()
    repos = create_in_memory_repositories()
    db_calls = 0
    orig_find_by_slug = repos.products.find_by_slug

    def counting_find_by_slug(slug: str):
        nonlocal db_calls
        db_calls += 1
        time.sleep(0.15)
        return orig_find_by_slug(slug)

    repos.products.find_by_slug = counting_find_by_slug
    app = create_app(settings=make_test_settings(), repos=repos, redis_client=r)

    barrier = Barrier(20, timeout=10)

    def fetch_detail(_idx: int) -> tuple[int, str]:
        c = new_client(app)
        barrier.wait()
        res = c.get("/api/products/chikmagalur-baba-budangiri-arabica")
        return res.status_code, res.headers["X-Cache"]

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(fetch_detail, range(20)))

    assert all(code == 200 for code, _ in results)
    assert db_calls == 1
    assert [xcache for _, xcache in results].count("MISS") == 1
    assert [xcache for _, xcache in results].count("HIT") == 19


def test_fakeredis_session_validity_cache_and_immediate_revocation() -> None:
    r = _make_fakeredis()
    repos = create_in_memory_repositories()
    session_db_lookups = 0
    orig_find_session = repos.sessions.find_by_id

    def tracked_find_session(session_id: str):
        nonlocal session_db_lookups
        session_db_lookups += 1
        return orig_find_session(session_id)

    repos.sessions.find_by_id = tracked_find_session
    app = create_app(settings=make_test_settings(), repos=repos, redis_client=r)

    buyer = signup_verified_client(
        app, "Sess Cache User", "sess-cache@beanbox-test.in", "SessCache@123!"
    )
    session_db_lookups = 0

    # First /me fills session cache (1 DB lookup); next 4 /me calls hit Redis (0 additional DB lookups!)
    for _ in range(5):
        assert buyer.get("/api/auth/me").status_code == 200
    assert session_db_lookups == 1

    # Logout immediately deletes session key -> access token is rejected immediately
    sync_csrf(buyer)
    access_cookie = buyer.cookies.get("beanbox_access")
    assert buyer.post("/api/auth/logout").status_code == 200
    replay = new_client(app)
    assert (
        replay.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access_cookie}"}
        ).status_code
        == 401
    )

    # Admin role demotion invalidates session cache & requires immediate DB role check
    u2 = signup_verified_client(
        app, "Promoted Admin", "promoted@beanbox-test.in", "Promoted@1234!"
    )
    u2_id = u2.get("/api/auth/me").json()["data"]["user"]["id"]
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin)
    assert (
        admin.patch(f"/api/admin/users/{u2_id}/role", json={"role": "admin"}).status_code
        == 200
    )

    u2_admin = login_client(app, "promoted@beanbox-test.in", "Promoted@1234!")
    assert u2_admin.get("/api/admin/stats").status_code == 200  # caches session active!
    u2_token = u2_admin.cookies.get("beanbox_access")

    assert (
        admin.patch(
            f"/api/admin/users/{u2_id}/role", json={"role": "customer"}
        ).status_code
        == 200
    )
    assert (
        new_client(app)
        .get("/api/admin/stats", headers={"Authorization": f"Bearer {u2_token}"})
        .status_code
        == 401
    )


def test_fakeredis_idempotency_orders_and_payment_sessions() -> None:
    r = _make_fakeredis()
    app = create_app(settings=make_test_settings(), redis_client=r)
    buyer = signup_verified_client(
        app, "Idem Buyer", "idem-buyer@beanbox-test.in", "IdemBuyer@123!"
    )
    addr_id = _create_address(buyer, "Idem Buyer")
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

    idem_key = "11111111-2222-4333-8444-555555555555"
    first = buyer.post(
        "/api/orders",
        headers={"Idempotency-Key": idem_key},
        json={"addressId": addr_id},
    )
    assert first.status_code == 201
    assert "Idempotent-Replay" not in first.headers

    # Same key + same body -> replayed stored 201 response with Idempotent-Replay: true
    replay = buyer.post(
        "/api/orders",
        headers={"Idempotency-Key": idem_key},
        json={"addressId": addr_id},
    )
    assert replay.status_code == 201
    assert replay.headers.get("Idempotent-Replay") == "true"
    assert replay.json() == first.json()

    # Same key + DIFFERENT body -> 422
    conflict = buyer.post(
        "/api/orders",
        headers={"Idempotency-Key": idem_key},
        json={"addressId": addr_id, "couponCode": "WELCOME10"},
    )
    assert conflict.status_code == 422

    # Concurrent in-progress key check
    r.set(
        f"beanbox:test:idem:{buyer.get('/api/auth/me').json()['data']['user']['id']}:orders:create:inprog-key",
        f'{{"state":"in_progress","bodyHash":"{hash_normalized_query({"addressId": addr_id, "couponCode": None})}"}}',
        ex=60,
    )
    in_prog = buyer.post(
        "/api/orders",
        headers={"Idempotency-Key": "inprog-key"},
        json={"addressId": addr_id},
    )
    assert in_prog.status_code == 409

    # Concurrent same-key requests create exactly 1 order (others get 409 in-progress)
    buyer2 = signup_verified_client(
        app, "Parallel Idem", "idem-parallel@beanbox-test.in", "IdemPara@123!"
    )
    addr2 = _create_address(buyer2, "Parallel Idem")
    assert (
        buyer2.post(
            "/api/cart/items",
            json={
                "productId": "prod-chikmagalur-arabica",
                "variantId": "chik-250-wb",
                "quantity": 1,
            },
        ).status_code
        == 201
    )
    para_key = "22222222-3333-4444-8555-666666666666"
    para_barrier = Barrier(5, timeout=5)

    def race_order(_idx: int) -> int:
        c = new_client(app)
        c.cookies.update(buyer2.cookies)
        sync_csrf(c)
        para_barrier.wait()
        return c.post(
            "/api/orders",
            headers={"Idempotency-Key": para_key},
            json={"addressId": addr2},
        ).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        race_statuses = list(pool.map(race_order, range(5)))

    assert race_statuses.count(201) >= 1
    assert all(s in (201, 409) for s in race_statuses)
    assert len(buyer2.get("/api/orders").json()["data"]["items"]) == 1

    # Checkout session idempotency
    order_id = first.json()["data"]["order"]["id"]
    sess_key = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    p1 = buyer.post(
        "/api/payments/checkout-session",
        headers={"Idempotency-Key": sess_key},
        json={"orderId": order_id},
    )
    assert p1.status_code == 201
    p2 = buyer.post(
        "/api/payments/checkout-session",
        headers={"Idempotency-Key": sess_key},
        json={"orderId": order_id},
    )
    assert p2.status_code == 201
    assert p2.headers.get("Idempotent-Replay") == "true"
    assert p2.json() == p1.json()


def test_fakeredis_every_key_has_ttl_and_observability_works() -> None:
    r = _make_fakeredis()
    app = create_app(
        settings=make_test_settings(RATE_LIMIT_LOGIN_MAX=3),
        redis_client=r,
    )
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    client = new_client(app)
    assert client.get("/api/products").headers["X-Cache"] == "MISS"
    assert client.get("/api/products").headers["X-Cache"] == "HIT"

    # Trigger 429 rate-limit block (admin used 1 slot; 3 wrong logins hit limit=3 -> 429)
    for _ in range(3):
        client.post(
            "/api/auth/login",
            json={"email": "ttlcheck@beanbox-test.in", "password": "WrongPassword@123!"},
        )

    # Also ensure customer is blocked from /api/admin/cache-stats
    cust = signup_verified_client(
        app, "No Stats Cust", "nostats@beanbox-test.in", "NoStats@1234!"
    )
    assert cust.get("/api/admin/cache-stats").status_code == 403

    # Test 50-thread concurrency on Lua sliding window with fakeredis too
    limiter = RedisRateLimiter(r, app_env="test")
    b50 = Barrier(50, timeout=5)

    def _hit(_idx: int) -> bool:
        b50.wait()
        return limiter.check("login:50threads", limit=15, window_seconds=60).allowed

    with ThreadPoolExecutor(max_workers=50) as pool:
        outcomes = list(pool.map(_hit, range(50)))
    assert outcomes.count(True) == 15
    assert outcomes.count(False) == 35

    health = client.get("/api/health").json()["data"]
    assert health["redis"]["enabled"] is True
    assert health["redis"]["connected"] is True
    assert health["redis"]["latencyMs"] is not None

    stats = admin.get("/api/admin/cache-stats")
    assert stats.status_code == 200
    body = stats.json()["data"]["stats"]
    assert body["hits"] >= 1
    assert body["misses"] >= 1
    assert body["rateLimitBlocks"] >= 1
    assert body["totalKeys"] >= 3
    assert "cache" in body["keysByDomain"]

    # Scan EVERY key created in Redis: every key MUST have ttl > 0
    all_keys = list(r.scan_iter(match=f"{key_prefix('test')}*"))
    assert all_keys
    for k in all_keys:
        assert r.ttl(k) > 0, f"Key {k} is missing TTL!"


def test_redis_down_dead_port_fallback_keeps_app_working() -> None:
    # Point to an unreachable port (port 1) with REDIS_ENABLED=true
    app = create_app(
        settings=make_test_settings(
            REDIS_ENABLED="true",
            REDIS_URL="redis://127.0.0.1:1/0",
            RATE_LIMIT_LOGIN_MAX=500,
        )
    )
    health = new_client(app).get("/api/health").json()["data"]
    assert health["redis"] == {"enabled": True, "connected": False, "latencyMs": None}

    # Public catalog bypasses dead Redis cleanly
    p = new_client(app).get("/api/products")
    assert p.status_code == 200
    assert p.headers["X-Cache"] == "MISS"

    # Auth, session validation, and idempotent order creation fallback seamlessly
    buyer = signup_verified_client(
        app, "Dead Redis User", "deadredis@beanbox-test.in", "DeadRedis@123!"
    )
    addr_id = _create_address(buyer, "Dead Redis User")
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
    order_res = buyer.post(
        "/api/orders",
        headers={"Idempotency-Key": "dead-redis-fallback-key"},
        json={"addressId": addr_id},
    )
    assert order_res.status_code == 201

    # Sliding window limiter falls back to in-memory limiter when Redis raises RedisError
    import redis as sync_redis

    r_dead = _make_fakeredis()
    rl = RedisRateLimiter(r_dead, "test", fallback=InMemoryRateLimiter())
    with patch.object(rl, "_script", side_effect=sync_redis.ConnectionError("dead port")):
        allowed, rem, _ = rl.check("login:1.2.3.4", 2, 60)
        assert allowed is True and rem == 1
        allowed2, rem2, _ = rl.check("login:1.2.3.4", 2, 60)
        assert allowed2 is True and rem2 == 0
        allowed3, _, _ = rl.check("login:1.2.3.4", 2, 60)
        assert allowed3 is False

    # OTP/TOTP & 2FA still generate valid challenges without Redis
    secret_client = signup_verified_client(
        app, "2FA Fallback", "2fafallback@beanbox-test.in", "TwoFaFall@123!"
    )
    sync_csrf(secret_client)
    sec = secret_client.post("/api/auth/2fa/setup").json()["data"]["secret"]
    assert (
        secret_client.post(
            "/api/auth/2fa/enable", json={"code": pyotp.TOTP(sec).now()}
        ).status_code
        == 200
    )
