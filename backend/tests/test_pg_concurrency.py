from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import psycopg
import pyotp
import pytest
from fastapi import FastAPI

from tests.conftest import (
    build_signed_webhook,
    enable_2fa_for_logged_in_client,
    login_client,
    new_client,
    signup_verified_client,
    sync_csrf,
)

pytestmark = pytest.mark.pg


def _create_address(client, name: str = "PG Buyer") -> str:
    sync_csrf(client)
    res = client.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": name,
            "phone": "9811111111",
            "line1": "100 Indiranagar Main",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560038",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["address"]["id"]


def test_pg_concurrent_cancel(pg_app: FastAPI) -> None:
    buyer = signup_verified_client(
        pg_app, "PG Cancel Buyer", "pg-cancel@beanbox-test.in", "PgCancel@123!"
    )
    addr_id = _create_address(buyer, "PG Cancel Buyer")

    prod_before = buyer.get("/api/products/chikmagalur-baba-budangiri-arabica").json()[
        "data"
    ]["product"]
    initial_stock = next(
        v for v in prod_before["variants"] if v["id"] == "chik-250-wb"
    )["stock"]

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
    order_id = buyer.post(
        "/api/orders",
        json={"addressId": addr_id, "couponCode": "WELCOME10"},
    ).json()["data"]["order"]["id"]

    barrier = Barrier(2, timeout=5)

    def do_cancel() -> int:
        c = new_client(pg_app)
        c.cookies.update(buyer.cookies)
        sync_csrf(c)
        barrier.wait()
        return c.post(
            f"/api/orders/{order_id}/cancel", json={"reason": "Parallel cancel"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(do_cancel)
        f2 = pool.submit(do_cancel)
        statuses = [f1.result(), f2.result()]

    assert sorted(statuses) == [200, 409]
    prod_after = buyer.get("/api/products/chikmagalur-baba-budangiri-arabica").json()[
        "data"
    ]["product"]
    after_stock = next(
        v for v in prod_after["variants"] if v["id"] == "chik-250-wb"
    )["stock"]
    assert after_stock == initial_stock


def test_pg_duplicate_webhook_delivery(pg_app: FastAPI) -> None:
    buyer = signup_verified_client(
        pg_app, "PG Webhook Buyer", "pg-webhook@beanbox-test.in", "PgWebhook@123!"
    )
    addr_id = _create_address(buyer, "PG Webhook Buyer")
    prod_before = buyer.get("/api/products/chikmagalur-baba-budangiri-arabica").json()[
        "data"
    ]["product"]
    initial_stock = next(
        v for v in prod_before["variants"] if v["id"] == "chik-250-wb"
    )["stock"]

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
    order_id = buyer.post("/api/orders", json={"addressId": addr_id}).json()["data"][
        "order"
    ]["id"]

    raw_wh, sig_wh = build_signed_webhook(
        pg_app.state.settings.mock_webhook_secret,
        {
            "id": "evt_pg_dup_001",
            "type": "payment_intent.payment_failed",
            "data": {"orderId": order_id},
        },
    )
    barrier = Barrier(2, timeout=5)

    def fire_webhook() -> dict:
        c = new_client(pg_app)
        barrier.wait()
        r = c.post(
            "/api/payments/webhook",
            content=raw_wh,
            headers={"x-mock-signature": sig_wh, "content-type": "application/json"},
        )
        assert r.status_code == 200, r.text
        return r.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(fire_webhook).result(), pool.submit(fire_webhook).result()]

    assert sorted([bool(r["duplicate"]) for r in results]) == [False, True]
    prod_after = buyer.get("/api/products/chikmagalur-baba-budangiri-arabica").json()[
        "data"
    ]["product"]
    after_stock = next(
        v for v in prod_after["variants"] if v["id"] == "chik-250-wb"
    )["stock"]
    assert after_stock == initial_stock


def test_pg_concurrent_same_code_totp(pg_app: FastAPI) -> None:
    user_client = signup_verified_client(
        pg_app, "PG TOTP User", "pg-totp@beanbox-test.in", "PgTotp@123!"
    )
    secret, _ = enable_2fa_for_logged_in_client(user_client)

    c1 = (
        new_client(pg_app)
        .post(
            "/api/auth/login",
            json={"email": "pg-totp@beanbox-test.in", "password": "PgTotp@123!"},
        )
        .json()["data"]["challengeToken"]
    )
    c2 = (
        new_client(pg_app)
        .post(
            "/api/auth/login",
            json={"email": "pg-totp@beanbox-test.in", "password": "PgTotp@123!"},
        )
        .json()["data"]["challengeToken"]
    )

    code = pyotp.TOTP(secret).at(datetime.now(timezone.utc) + timedelta(seconds=30))
    barrier = Barrier(2, timeout=5)

    def verify(tok: str) -> int:
        c = new_client(pg_app)
        barrier.wait()
        return c.post(
            "/api/auth/2fa/verify-login",
            json={"challengeToken": tok, "code": code},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(verify, c1)
        f2 = pool.submit(verify, c2)
        statuses = [f1.result(), f2.result()]

    assert sorted(statuses) == [200, 401]


def test_pg_concurrent_refresh_rotation_and_grace_limit(pg_app: FastAPI) -> None:
    client = login_client(pg_app, "arjun@beanbox.in", "Coffee@1234")
    r0 = client.cookies.get("beanbox_refresh")
    csrf0 = client.cookies.get("beanbox_csrf")
    assert r0 and csrf0

    barrier = Barrier(2, timeout=5)

    def tab_refresh() -> tuple[int, str | None]:
        tab = new_client(pg_app)
        tab.headers["Origin"] = "http://localhost:3000"
        tab.cookies.set("beanbox_refresh", r0)
        tab.cookies.set("beanbox_csrf", csrf0)
        tab.headers["X-CSRF-Token"] = csrf0
        barrier.wait()
        r = tab.post("/api/auth/refresh")
        return r.status_code, r.cookies.get("beanbox_refresh")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(tab_refresh)
        f2 = pool.submit(tab_refresh)
        res = [f1.result(), f2.result()]

    # 1st rotates (sets new cookie), 2nd hits grace (keeps existing); both 200 (1 grace use spent -> 2 remain)
    assert [r[0] for r in res] == [200, 200]
    rotated_tokens = [r[1] for r in res if r[1] and r[1] != r0]
    assert len(rotated_tokens) == 1

    # Spend remaining 2 grace hits, then 4th total grace replay triggers family revocation
    for idx in range(3):
        rep = new_client(pg_app)
        rep.headers["Origin"] = "http://localhost:3000"
        rep.cookies.set("beanbox_refresh", r0)
        rep.cookies.set("beanbox_csrf", csrf0)
        rep.headers["X-CSRF-Token"] = csrf0
        code = rep.post("/api/auth/refresh").status_code
        assert code == (200 if idx < 2 else 401)


def test_pg_concurrent_duplicate_signup_returns_409(pg_app: FastAPI) -> None:
    barrier = Barrier(2, timeout=5)

    def do_signup(idx: int) -> int:
        c = new_client(pg_app)
        barrier.wait()
        return c.post(
            "/api/auth/signup",
            json={
                "name": f"PG Dup {idx}",
                "email": "pg-dup@beanbox-test.in",
                "password": "PgDupPassword@123!",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(do_signup, 1)
        f2 = pool.submit(do_signup, 2)
        statuses = [f1.result(), f2.result()]

    assert sorted(statuses) == [201, 409]


def test_pg_variant_update_on_ordered_product(pg_app: FastAPI) -> None:
    admin = login_client(pg_app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin)
    created = admin.post(
        "/api/admin/products",
        json={
            "name": "PG Variant Diff Roast",
            "slug": "pg-variant-diff-roast",
            "shortDescription": "Testing ordered variant soft-inactivation in Postgres.",
            "description": "Ordered variants cannot be deleted via FK and must be marked is_active=false.",
            "category": "beans",
            "roastLevel": "medium",
            "origin": "Coorg, Karnataka",
            "tastingNotes": ["Caramel"],
            "images": ["/images/products/beans-medium.svg"],
            "variants": [
                {
                    "sku": "PG-DIFF-V1",
                    "size": "250g",
                    "grind": "whole_bean",
                    "label": "250g · Whole Bean",
                    "pricePaise": 59900,
                    "stock": 10,
                },
                {
                    "sku": "PG-DIFF-V2",
                    "size": "500g",
                    "grind": "filter",
                    "label": "500g · Filter",
                    "pricePaise": 99900,
                    "stock": 5,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    product = created.json()["data"]["product"]
    prod_id = product["id"]
    v1 = next(v for v in product["variants"] if v["sku"] == "PG-DIFF-V1")
    v2 = next(v for v in product["variants"] if v["sku"] == "PG-DIFF-V2")

    buyer = signup_verified_client(
        pg_app, "PG Variant Buyer", "pg-var-buyer@beanbox-test.in", "PgVarBuyer@123!"
    )
    addr_id = _create_address(buyer, "PG Variant Buyer")
    assert (
        buyer.post(
            "/api/cart/items",
            json={"productId": prod_id, "variantId": v1["id"], "quantity": 1},
        ).status_code
        == 201
    )
    order_res = buyer.post("/api/orders", json={"addressId": addr_id})
    assert order_res.status_code == 201, order_res.text

    # Admin updates product removing BOTH V1 (ordered) & V2 (unordered), adding V3
    upd = admin.put(
        f"/api/admin/products/{prod_id}",
        json={
            "variants": [
                {
                    "sku": "PG-DIFF-V3",
                    "size": "1kg",
                    "grind": "whole_bean",
                    "label": "1kg · Whole Bean",
                    "pricePaise": 179900,
                    "stock": 8,
                }
            ]
        },
    )
    assert upd.status_code == 200, upd.text
    test_dsn = os.environ["DATABASE_URL_TEST"]
    with psycopg.connect(test_dsn) as conn:
        rows = conn.execute(
            "SELECT id, sku, is_active, stock FROM product_variants WHERE product_id = %s;",
            (prod_id,),
        ).fetchall()
    by_sku = {r[1]: r for r in rows}
    assert v1["sku"] in by_sku
    assert by_sku[v1["sku"]][2] is False and by_sku[v1["sku"]][3] == 0
    assert v2["sku"] not in by_sku
    assert "PG-DIFF-V3" in by_sku and by_sku["PG-DIFF-V3"][2] is True


def test_pg_last_admin_demotion_race(pg_app: FastAPI) -> None:
    second = signup_verified_client(
        pg_app, "PG Second Admin", "pg-admin2@beanbox-test.in", "PgAdmin2@123!"
    )
    second_id = second.get("/api/auth/me").json()["data"]["user"]["id"]
    admin1 = login_client(pg_app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin1)
    assert (
        admin1.patch(
            f"/api/admin/users/{second_id}/role", json={"role": "admin"}
        ).status_code
        == 200
    )

    admin2 = login_client(pg_app, "pg-admin2@beanbox-test.in", "PgAdmin2@123!")
    sync_csrf(admin2)
    admin1_id = admin1.get("/api/auth/me").json()["data"]["user"]["id"]

    barrier = Barrier(2, timeout=5)

    def demote(cli, target_id: str) -> int:
        barrier.wait()
        return cli.patch(
            f"/api/admin/users/{target_id}/role", json={"role": "customer"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(demote, admin1, second_id)
        f2 = pool.submit(demote, admin2, admin1_id)
        statuses = [f1.result(), f2.result()]

    assert 200 in statuses
    assert any(s in (401, 403, 409) for s in statuses)

    test_dsn = os.environ["DATABASE_URL_TEST"]
    with psycopg.connect(test_dsn) as conn:
        admin_cnt = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin';"
        ).fetchone()[0]
    assert admin_cnt == 1


def test_pg_oversell_last_unit_with_20_parallel_orders(pg_app: FastAPI) -> None:
    admin = login_client(pg_app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin)
    created = admin.post(
        "/api/admin/products",
        json={
            "name": "PG Limited Reserve Micro-Lot",
            "slug": "pg-limited-reserve-lot",
            "shortDescription": "Single bag limited release to verify atomic Postgres reservation.",
            "description": "Only 1 bag available; 20 concurrent checkouts must never oversell.",
            "category": "beans",
            "roastLevel": "light",
            "origin": "Ratnagiri Estate, Chikmagalur",
            "tastingNotes": ["Bergamot"],
            "images": ["/images/products/beans-light.svg"],
            "variants": [
                {
                    "sku": "PG-SOLO-1",
                    "size": "250g",
                    "grind": "whole_bean",
                    "label": "250g · Whole Bean",
                    "pricePaise": 79900,
                    "stock": 1,
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    prod = created.json()["data"]["product"]
    prod_id = prod["id"]
    var_id = prod["variants"][0]["id"]

    buyers = []
    for idx in range(20):
        b = signup_verified_client(
            pg_app, f"Rush Buyer {idx}", f"rush-{idx}@beanbox-test.in", "RushBuyer@123!"
        )
        addr_id = _create_address(b, f"Rush Buyer {idx}")
        assert (
            b.post(
                "/api/cart/items",
                json={"productId": prod_id, "variantId": var_id, "quantity": 1},
            ).status_code
            == 201
        )
        buyers.append((b, addr_id))

    barrier = Barrier(20, timeout=10)

    def place_order(b_and_addr: tuple) -> int:
        b, addr_id = b_and_addr
        c = new_client(pg_app)
        c.cookies.update(b.cookies)
        sync_csrf(c)
        barrier.wait()
        return c.post("/api/orders", json={"addressId": addr_id}).status_code

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(place_order, buyers))

    assert statuses.count(201) == 1
    assert statuses.count(409) == 19

    test_dsn = os.environ["DATABASE_URL_TEST"]
    with psycopg.connect(test_dsn) as conn:
        final_stock = conn.execute(
            "SELECT stock FROM product_variants WHERE id = %s;",
            (var_id,),
        ).fetchone()[0]
    assert final_stock == 0
