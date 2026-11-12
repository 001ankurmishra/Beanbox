from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.utils.security import sha256_hex
from tests.conftest import (
    create_test_app,
    enable_2fa_for_logged_in_client,
    extract_email_token,
    login_client,
    make_test_settings,
    new_client,
    signup_verified_client,
    sync_csrf,
)


def _create_address(client: TestClient, label: str = "Home") -> str:
    sync_csrf(client)
    res = client.post(
        "/api/addresses",
        json={
            "label": label,
            "fullName": "User One",
            "phone": "9811111111",
            "line1": "12 MG Road, Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560038",
            "isDefault": True,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["address"]["id"]


def _add_item_to_cart(
    client: TestClient,
    product_id: str = "prod-chikmagalur-arabica",
    variant_id: str = "chik-250-wb",
    quantity: int = 1,
) -> None:
    sync_csrf(client)
    res = client.post(
        "/api/cart/items",
        json={
            "productId": product_id,
            "variantId": variant_id,
            "quantity": quantity,
        },
    )
    assert res.status_code == 201, res.text


def _create_verified_order(
    client: TestClient,
    address_id: str,
    product_id: str = "prod-chikmagalur-arabica",
    variant_id: str = "chik-250-wb",
) -> str:
    _add_item_to_cart(client, product_id=product_id, variant_id=variant_id, quantity=1)
    sync_csrf(client)
    order_res = client.post("/api/orders", json={"addressId": address_id})
    assert order_res.status_code == 201, order_res.text
    return order_res.json()["data"]["order"]["id"]


def test_cross_user_idor_returns_404_across_all_resources():
    app = create_test_app()
    user_a = signup_verified_client(
        app, "User Alpha", "alpha@beanbox-test.in", "AlphaPass@123!"
    )
    user_b = signup_verified_client(
        app, "User Beta", "beta@beanbox-test.in", "BetaPass@123!"
    )
    user_b_id = user_b.get("/api/auth/me").json()["data"]["user"]["id"]

    # User B sets up address, order (and pays so they can leave a review), wishlist, cart, session
    b_addr_id = _create_address(user_b, "Home")
    b_order_id = _create_verified_order(user_b, b_addr_id)

    # B pays so review creation works, plus keep a separate pending order C for cancel/payment checks
    sync_csrf(user_b)
    sess_res = user_b.post(
        "/api/payments/checkout-session", json={"orderId": b_order_id}
    )
    assert sess_res.status_code == 201
    pay_res = user_b.post(
        "/api/payments/mock/trigger",
        json={"orderId": b_order_id, "outcome": "success"},
    )
    assert pay_res.status_code == 200

    # B creates a second pending order for payment-session / cancel IDOR checks
    b_pending_order_id = _create_verified_order(
        user_b, b_addr_id, product_id="prod-araku-organic", variant_id="arak-250-wb"
    )

    # B creates a review on purchased product
    sync_csrf(user_b)
    rev_res = user_b.post(
        "/api/products/chikmagalur-baba-budangiri-arabica/reviews",
        json={
            "rating": 5,
            "title": "Outstanding roast",
            "comment": "Balanced chocolate and bright fruit notes.",
        },
    )
    assert rev_res.status_code == 201, rev_res.text
    b_review_id = rev_res.json()["data"]["review"]["id"]

    # B adds wishlist item & cart item & inspects session id
    sync_csrf(user_b)
    assert user_b.post("/api/wishlist/prod-nilgiris-blue").status_code == 201
    _add_item_to_cart(user_b, product_id="prod-araku-organic", variant_id="arak-250-wb")
    b_sessions = user_b.get("/api/auth/sessions").json()["data"]["items"]
    b_session_id = b_sessions[0]["id"]

    # User A creates own session/cart item context
    a_user_id = user_a.get("/api/auth/me").json()["data"]["user"]["id"]
    sync_csrf(user_a)

    # 1. Orders & Invoices -> 404 (not 403)
    assert user_a.get(f"/api/orders/{b_order_id}").status_code == 404
    assert user_a.get(f"/api/orders/{b_order_id}/invoice").status_code == 404
    assert (
        user_a.post(
            f"/api/orders/{b_pending_order_id}/cancel", json={"reason": "hijack"}
        ).status_code
        == 404
    )
    assert user_b.get(f"/api/orders/{b_pending_order_id}").json()["data"]["order"]["status"] == "pending"

    # 2. Payments -> 404 (not 403)
    assert (
        user_a.post(
            "/api/payments/checkout-session", json={"orderId": b_pending_order_id}
        ).status_code
        == 404
    )
    assert (
        user_a.post(
            "/api/payments/mock/trigger",
            json={"orderId": b_pending_order_id, "outcome": "success"},
        ).status_code
        == 404
    )
    assert (
        user_b.get(f"/api/orders/{b_pending_order_id}")
        .json()["data"]["order"]["paymentStatus"]
        == "unpaid"
    )

    # 3. Addresses & checkout using B's addressId -> 404
    assert (
        user_a.patch(f"/api/addresses/{b_addr_id}", json={"city": "Mumbai"}).status_code
        == 404
    )
    assert user_a.delete(f"/api/addresses/{b_addr_id}").status_code == 404
    assert user_a.patch(f"/api/addresses/{b_addr_id}/default").status_code == 404
    _add_item_to_cart(user_a, product_id="prod-chikmagalur-arabica", variant_id="chik-250-wb")
    sync_csrf(user_a)
    assert (
        user_a.post(
            "/api/checkout/preview", json={"addressId": b_addr_id}
        ).status_code
        == 404
    )
    assert (
        user_a.post("/api/orders", json={"addressId": b_addr_id}).status_code == 404
    )
    assert len(user_b.get("/api/addresses").json()["data"]["items"]) == 1

    # 4. Reviews -> 404 (not 403), B's review intact
    assert user_a.delete(f"/api/reviews/{b_review_id}").status_code == 404
    revs = user_b.get(
        "/api/products/chikmagalur-baba-budangiri-arabica/reviews"
    ).json()["data"]["items"]
    assert any(r["id"] == b_review_id for r in revs)

    # 5. Sessions -> 404, B still authenticated
    assert user_a.delete(f"/api/auth/sessions/{b_session_id}").status_code == 404
    assert user_b.get("/api/auth/me").status_code == 200

    # 6. Wishlist item -> 404 when A removes product from B's wishlist, B's wishlist intact
    assert user_a.delete("/api/wishlist/prod-nilgiris-blue").status_code == 404
    b_wishlist = user_b.get("/api/wishlist").json()["data"]["items"]
    assert any(p["id"] == "prod-nilgiris-blue" for p in b_wishlist)

    # 7. Cart item -> A cannot modify/delete B's cart variant (404), B's cart intact
    assert (
        user_a.patch("/api/cart/items/arak-250-wb", json={"quantity": 5}).status_code
        == 404
    )
    assert user_a.delete("/api/cart/items/arak-250-wb").status_code == 404
    b_cart = user_b.get("/api/cart").json()["data"]["cart"]
    assert any(i["variantId"] == "arak-250-wb" for i in b_cart["items"])

    # 8. Repository layer directly enforces user_id scoping (defense-in-depth)
    repos = app.state.repos
    assert repos.orders.find_by_id_for_user(b_order_id, a_user_id) is None
    assert repos.orders.find_by_id_for_user(b_order_id, user_b_id) is not None
    assert repos.addresses.find_by_id_for_user(b_addr_id, a_user_id) is None
    assert repos.addresses.find_by_id_for_user(b_addr_id, user_b_id) is not None
    assert repos.reviews.find_by_id_for_user(b_review_id, a_user_id) is None
    assert repos.reviews.delete_for_user(b_review_id, a_user_id) is False


def test_customer_gets_403_on_every_admin_route():
    app = create_test_app()
    customer = signup_verified_client(
        app, "Customer", "cust-admin-check@beanbox-test.in", "CustomerPass@123!"
    )
    sync_csrf(customer)

    admin_calls = [
        ("GET", "/api/admin/stats", None),
        ("GET", "/api/admin/products", None),
        (
            "POST",
            "/api/admin/products",
            {
                "name": "Unauthorized Roast",
                "slug": "unauthorized-roast",
                "shortDescription": "Should never be created by customer.",
                "description": "Should never be created by a customer role.",
                "category": "beans",
                "roastLevel": "medium",
                "origin": "Coorg",
                "tastingNotes": ["Cocoa"],
                "images": ["/images/products/beans-medium.svg"],
                "variants": [
                    {
                        "sku": "UNAUTH-250",
                        "size": "250g",
                        "grind": "whole_bean",
                        "label": "250g · Whole Bean",
                        "pricePaise": 49900,
                        "stock": 5,
                    }
                ],
            },
        ),
        (
            "PATCH",
            "/api/admin/products/prod-chikmagalur-arabica",
            {"isFeatured": False},
        ),
        ("DELETE", "/api/admin/products/prod-chikmagalur-arabica", None),
        (
            "PATCH",
            "/api/admin/inventory/prod-chikmagalur-arabica/chik-250-wb",
            {"stock": 999},
        ),
        ("GET", "/api/admin/orders", None),
        (
            "PATCH",
            "/api/admin/orders/some-order-id/status",
            {"status": "shipped"},
        ),
        ("GET", "/api/admin/coupons", None),
        (
            "POST",
            "/api/admin/coupons",
            {
                "code": "FREEALL",
                "description": "Unauthorized coupon creation",
                "type": "percent",
                "value": 50,
                "minOrderPaise": 0,
                "expiresAt": "2030-01-01T00:00:00Z",
                "usageLimit": 100,
            },
        ),
        ("PATCH", "/api/admin/coupons/some-coupon", {"isActive": False}),
        ("DELETE", "/api/admin/coupons/some-coupon", None),
        ("GET", "/api/admin/users", None),
        (
            "PATCH",
            "/api/admin/users/22222222-2222-4222-8222-222222222222/role",
            {"role": "admin"},
        ),
        ("GET", "/api/admin/audit-logs", None),
    ]

    for method, path, payload in admin_calls:
        sync_csrf(customer)
        res = customer.request(method, path, json=payload)
        assert res.status_code == 403, (
            f"Expected 403 for {method} {path}, got {res.status_code}: {res.text}"
        )


def test_unverified_user_blocked_from_checkout_and_payment_session():
    app = create_test_app()
    client = new_client(app)
    client.headers["Origin"] = "http://localhost:3000"

    res = client.post(
        "/api/auth/signup",
        json={
            "name": "Unverified Buyer",
            "email": "unverified-checkout@beanbox-test.in",
            "password": "VerifyCheck@123!",
        },
    )
    assert res.status_code == 201
    sync_csrf(client)
    addr_id = _create_address(client)
    _add_item_to_cart(client)

    sync_csrf(client)
    order_res = client.post("/api/orders", json={"addressId": addr_id})
    assert order_res.status_code == 403
    assert order_res.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    pay_res = client.post(
        "/api/payments/checkout-session", json={"orderId": "nonexistent-order"}
    )
    assert pay_res.status_code == 403
    assert pay_res.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


def test_demoted_admin_old_token_and_refresh_rejected():
    app = create_test_app()
    root_admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    target = signup_verified_client(
        app, "Promoted User", "promo@beanbox-test.in", "PromoAdmin@123!"
    )
    target_id = target.get("/api/auth/me").json()["data"]["user"]["id"]

    # Root admin promotes target to admin
    sync_csrf(root_admin)
    promote_res = root_admin.patch(
        f"/api/admin/users/{target_id}/role", json={"role": "admin"}
    )
    assert promote_res.status_code == 200

    # Target logs in cleanly and enables 2FA for admin access
    promoted_client = login_client(
        app, "promo@beanbox-test.in", "PromoAdmin@123!", enable_admin_2fa=False
    )
    _, promo_recovery_codes = enable_2fa_for_logged_in_client(promoted_client)
    assert promoted_client.get("/api/admin/stats").status_code == 200
    old_access_jwt = promoted_client.cookies.get("beanbox_access")
    old_refresh = promoted_client.cookies.get("beanbox_refresh")
    assert old_access_jwt and old_refresh

    # Root admin demotes target back to customer -> sessions revoked + DB role updated
    sync_csrf(root_admin)
    demote_res = root_admin.patch(
        f"/api/admin/users/{target_id}/role", json={"role": "customer"}
    )
    assert demote_res.status_code == 200
    assert demote_res.json()["data"]["user"]["role"] == "customer"

    # 1. Old admin access token & old refresh token are immediately rejected
    stale_client = new_client(app)
    stale_client.headers["Origin"] = "http://localhost:3000"
    stale_admin_res = stale_client.get(
        "/api/admin/stats", headers={"Authorization": f"Bearer {old_access_jwt}"}
    )
    assert stale_admin_res.status_code == 401
    assert stale_admin_res.json()["error"]["code"] == "SESSION_REVOKED"

    promoted_client.cookies.set("beanbox_refresh", old_refresh)
    sync_csrf(promoted_client)
    assert promoted_client.post("/api/auth/refresh").status_code == 401

    # 2. Even with an un-revoked session whose JWT claim still carries role="admin",
    # require_role("admin") re-queries DB user role and rejects with 403
    fresh_client = new_client(app)
    fresh_client.headers["Origin"] = "http://localhost:3000"
    login_step = fresh_client.post(
        "/api/auth/login",
        json={"email": "promo@beanbox-test.in", "password": "PromoAdmin@123!"},
    )
    assert login_step.status_code == 200
    assert login_step.json()["data"]["requiresTwoFactor"] is True
    sync_csrf(fresh_client)
    step2 = fresh_client.post(
        "/api/auth/2fa/verify-login",
        json={
            "challengeToken": login_step.json()["data"]["challengeToken"],
            "code": promo_recovery_codes[0],
        },
    )
    assert step2.status_code == 200
    fresh_session_id = fresh_client.get("/api/auth/sessions").json()["data"]["items"][0][
        "id"
    ]
    forged_role_jwt = jwt.encode(
        {
            "sub": target_id,
            "role": "admin",
            "sid": fresh_session_id,
            "jti": "test-stale-admin-jti",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
            "typ": "access",
        },
        app.state.settings.jwt_secret,
        algorithm="HS256",
    )
    db_recheck_res = new_client(app).get(
        "/api/admin/stats", headers={"Authorization": f"Bearer {forged_role_jwt}"}
    )
    assert db_recheck_res.status_code == 403


def test_mass_assignment_privileged_fields_ignored():
    app = create_test_app()
    client = new_client(app)
    client.headers["Origin"] = "http://localhost:3000"

    # 1. Signup ignores role, emailVerified, totpEnabled, id
    signup_res = client.post(
        "/api/auth/signup",
        json={
            "name": "Mass Assign Tester",
            "email": "mass-assign@beanbox-test.in",
            "password": "MassAssign@123!",
            "role": "admin",
            "emailVerified": True,
            "totpEnabled": True,
            "id": "00000000-0000-4000-8000-000000000999",
        },
    )
    assert signup_res.status_code == 201, signup_res.text
    created_user = signup_res.json()["data"]["user"]
    assert created_user["role"] == "customer"
    assert created_user["emailVerified"] is False
    assert created_user["totpEnabled"] is False
    assert created_user["id"] != "00000000-0000-4000-8000-000000000999"

    # Verify email so checkout succeeds later
    verify_email = next(
        e
        for e in reversed(app.state.services.email_service.get_sent_emails())
        if e.type == "email_verification" and e.to == "mass-assign@beanbox-test.in"
    )
    sync_csrf(client)
    assert (
        client.post(
            "/api/auth/verify-email",
            json={"token": extract_email_token(verify_email.body)},
        ).status_code
        == 200
    )

    # 2. PATCH /api/auth/me ignores role, email, userId, totpEnabled
    sync_csrf(client)
    patch_me = client.patch(
        "/api/auth/me",
        json={
            "name": "Updated Tester",
            "role": "admin",
            "email": "admin@beanbox.in",
            "userId": "11111111-1111-4111-8111-111111111111",
            "totpEnabled": True,
        },
    )
    assert patch_me.status_code == 200
    patched_user = patch_me.json()["data"]["user"]
    assert patched_user["name"] == "Updated Tester"
    assert patched_user["role"] == "customer"
    assert patched_user["email"] == "mass-assign@beanbox-test.in"
    assert patched_user["totpEnabled"] is False
    assert client.get("/api/admin/stats").status_code == 403

    # 3. Address POST/PATCH ignores injected userId / id
    sync_csrf(client)
    addr_res = client.post(
        "/api/addresses",
        json={
            "id": "forged-address-id",
            "userId": "22222222-2222-4222-8222-222222222222",
            "label": "Home",
            "fullName": "Mass Assign Tester",
            "phone": "9811111111",
            "line1": "24 Church Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560001",
        },
    )
    assert addr_res.status_code == 201
    addr = addr_res.json()["data"]["address"]
    assert addr["userId"] == created_user["id"]
    assert addr["id"] != "forged-address-id"

    # 4. Order POST ignores injected userId, status, paymentStatus, pricing
    _add_item_to_cart(client)
    sync_csrf(client)
    order_res = client.post(
        "/api/orders",
        json={
            "addressId": addr["id"],
            "userId": "22222222-2222-4222-8222-222222222222",
            "status": "paid",
            "paymentStatus": "paid",
            "pricing": {"totalPaise": 1},
        },
    )
    assert order_res.status_code == 201
    order = order_res.json()["data"]["order"]
    assert order["userId"] == created_user["id"]
    assert order["status"] == "pending"
    assert order["paymentStatus"] == "unpaid"
    assert order["pricing"]["totalPaise"] >= 49900


def test_refresh_10s_grace_window_and_post_window_revocation():
    app = create_test_app()
    tab_a = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    r0 = tab_a.cookies.get("beanbox_refresh")
    csrf0 = tab_a.cookies.get("beanbox_csrf")
    assert r0 and csrf0

    # Prepare Tab B holding the same initial R0 (simulating two open tabs before rotation)
    tab_b = new_client(app)
    tab_b.headers["Origin"] = "http://localhost:3000"
    tab_b.cookies.set("beanbox_refresh", r0)
    tab_b.cookies.set("beanbox_csrf", csrf0)
    tab_b.headers["X-CSRF-Token"] = csrf0

    # Tab A rotates R0 -> R1
    ref_a = tab_a.post("/api/auth/refresh")
    assert ref_a.status_code == 200, ref_a.text
    sync_csrf(tab_a)
    r1 = tab_a.cookies.get("beanbox_refresh")
    assert r1 and r1 != r0

    # Tab B sends R0 inside the 10s grace window -> succeeds without revoking the session family!
    ref_b = tab_b.post("/api/auth/refresh")
    assert ref_b.status_code == 200, ref_b.text
    assert ref_b.cookies.get("beanbox_access")
    # Grace hit does not overwrite cookie jar with a stale/new refresh token
    assert "beanbox_refresh" not in ref_b.headers.get("set-cookie", "")

    # Tab A's rotated R1 is still valid and rotates R1 -> R2 cleanly
    ref_a2 = tab_a.post("/api/auth/refresh")
    assert ref_a2.status_code == 200, ref_a2.text
    sync_csrf(tab_a)
    r2 = tab_a.cookies.get("beanbox_refresh")
    assert r2 and r2 != r1
    assert tab_a.get("/api/auth/me").status_code == 200

    # Immediately previous token was updated from R0 to R1 during R1 -> R2;
    # replaying older R0 (even within 10s!) must trigger reuse detection and revoke family!
    stale_replay = new_client(app)
    stale_replay.headers["Origin"] = "http://localhost:3000"
    stale_replay.cookies.set("beanbox_refresh", r0)
    stale_replay.cookies.set("beanbox_csrf", csrf0)
    stale_replay.headers["X-CSRF-Token"] = csrf0
    res_old = stale_replay.post("/api/auth/refresh")
    assert res_old.status_code == 401
    assert res_old.json()["error"]["code"] == "REFRESH_TOKEN_REUSE_DETECTED"
    assert tab_a.get("/api/auth/me").status_code == 401

    # Now test expiry of grace window AFTER 10 seconds on a fresh session
    fresh = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    r_init = fresh.cookies.get("beanbox_refresh")
    csrf_fresh = fresh.cookies.get("beanbox_csrf")
    assert r_init and csrf_fresh
    assert fresh.post("/api/auth/refresh").status_code == 200
    sync_csrf(fresh)
    r_next = fresh.cookies.get("beanbox_refresh")
    assert r_next and r_next != r_init

    # Simulate elapsed > 10s by setting grace_expires_at in the past on the stored session
    sess_repo = app.state.repos.sessions
    sess = sess_repo.find_by_refresh_hash(sha256_hex(r_next))
    assert sess is not None and sess.grace_refresh_hash == sha256_hex(r_init)
    with sess_repo._lock:
        for stored in sess_repo._sessions:
            if stored.id == sess.id:
                stored.grace_expires_at = (
                    (datetime.now(timezone.utc) - timedelta(seconds=1))
                    .isoformat()
                    .replace("+00:00", "Z")
                )

    expired_grace = new_client(app)
    expired_grace.headers["Origin"] = "http://localhost:3000"
    expired_grace.cookies.set("beanbox_refresh", r_init)
    expired_grace.cookies.set("beanbox_csrf", csrf_fresh)
    expired_grace.headers["X-CSRF-Token"] = csrf_fresh
    after_window = expired_grace.post("/api/auth/refresh")
    assert after_window.status_code == 401
    assert after_window.json()["error"]["code"] == "REFRESH_TOKEN_REUSE_DETECTED"
    assert fresh.get("/api/auth/me").status_code == 401


def test_parallel_concurrent_tab_refresh_race_succeeds_without_revocation():
    app = create_test_app(settings=make_test_settings(REFRESH_GRACE_SECONDS=10))
    seed = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    r0 = seed.cookies.get("beanbox_refresh")
    csrf0 = seed.cookies.get("beanbox_csrf")
    assert r0 and csrf0

    def fire_refresh() -> tuple[int, str | None]:
        c = new_client(app)
        c.headers["Origin"] = "http://localhost:3000"
        c.cookies.set("beanbox_refresh", r0)
        c.cookies.set("beanbox_csrf", csrf0)
        c.headers["X-CSRF-Token"] = csrf0
        resp = c.post("/api/auth/refresh")
        return resp.status_code, resp.cookies.get("beanbox_refresh")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(fire_refresh)
        f2 = pool.submit(fire_refresh)
        results = [f1.result(), f2.result()]

    statuses = [r[0] for r in results]
    new_tokens = [r[1] for r in results if r[1]]
    assert statuses == [200, 200]
    assert len(new_tokens) == 1

    # Winning refresh token still works afterwards
    sync_csrf(seed)
    c_winner = new_client(app)
    c_winner.headers["Origin"] = "http://localhost:3000"
    c_winner.cookies.set("beanbox_refresh", new_tokens[0])
    c_winner.cookies.set("beanbox_csrf", csrf0)
    c_winner.headers["X-CSRF-Token"] = csrf0
    follow = c_winner.post("/api/auth/refresh")
    assert follow.status_code == 200


def test_security_notification_emails_sent_for_security_events():
    app = create_test_app()
    email_svc = app.state.services.email_service

    # 1. Signup on Device A should NOT send a new-device alert
    user_client = signup_verified_client(
        app, "Security Alerts User", "alerts@beanbox-test.in", "AlertPass@123!"
    )
    device_a = "BeanBoxTestDeviceA/1.0"
    user_client.headers["User-Agent"] = device_a

    # First explicit login with Device A UA -> user only had signup's "testclient" UA previously!
    # So switching from signup UA to Device A triggers one alert; logging in again from Device A does NOT.
    def _sec_emails():
        return [
            e
            for e in email_svc.get_sent_emails()
            if e.type == "security_notification" and e.to == "alerts@beanbox-test.in"
        ]

    # Log in once on Device B -> triggers new-device alert
    dev_b = new_client(app)
    dev_b.headers["Origin"] = "http://localhost:3000"
    dev_b.headers["User-Agent"] = "Mozilla/5.0 NewLaptop/99"
    before_login = len(_sec_emails())
    login_b = dev_b.post(
        "/api/auth/login",
        json={"email": "alerts@beanbox-test.in", "password": "AlertPass@123!"},
    )
    assert login_b.status_code == 200
    assert len(_sec_emails()) == before_login + 1
    assert "new device" in _sec_emails()[-1].subject.lower()
    assert "AlertPass@123!" not in _sec_emails()[-1].body

    # Same device login again does NOT send a duplicate alert
    dev_b_again = new_client(app)
    dev_b_again.headers["Origin"] = "http://localhost:3000"
    dev_b_again.headers["User-Agent"] = "Mozilla/5.0 NewLaptop/99"
    before_repeat = len(_sec_emails())
    assert (
        dev_b_again.post(
            "/api/auth/login",
            json={"email": "alerts@beanbox-test.in", "password": "AlertPass@123!"},
        ).status_code
        == 200
    )
    assert len(_sec_emails()) == before_repeat

    # 2. Password change triggers security notification email
    sync_csrf(user_client)
    before_pw = len(_sec_emails())
    ch = user_client.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "AlertPass@123!",
            "newPassword": "AlertPassChanged@456!",
        },
    )
    assert ch.status_code == 200
    assert len(_sec_emails()) == before_pw + 1
    assert "password was changed" in _sec_emails()[-1].subject.lower()
    assert "AlertPassChanged@456!" not in _sec_emails()[-1].body

    # 3. 2FA enable and disable trigger security notification emails
    before_2fa_en = len(_sec_emails())
    _, recovery_codes = enable_2fa_for_logged_in_client(user_client)
    assert len(_sec_emails()) == before_2fa_en + 1
    assert "enabled" in _sec_emails()[-1].subject.lower()

    before_2fa_dis = len(_sec_emails())
    sync_csrf(user_client)
    dis = user_client.post(
        "/api/auth/2fa/disable",
        json={
            "code": recovery_codes[0],
            "password": "AlertPassChanged@456!",
        },
    )
    assert dis.status_code == 200
    assert len(_sec_emails()) == before_2fa_dis + 1
    assert "disabled" in _sec_emails()[-1].subject.lower()
