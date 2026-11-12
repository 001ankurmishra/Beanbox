from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest

from app.main import create_app
from app.services.google_oauth_service import (
    GoogleOAuthClient,
    GoogleVerifiedIdentity,
    pkce_code_challenge,
)
from app.utils.security import sha256_hex
from tests.conftest import (
    build_signed_webhook,
    create_test_app,
    enable_2fa_for_logged_in_client,
    extract_email_token,
    login_client,
    make_test_settings,
    new_client,
    signup_verified_client,
    sync_csrf,
)


class _StubGoogleOAuthClient(GoogleOAuthClient):
    def __init__(self, identity: GoogleVerifiedIdentity) -> None:
        self.identity = identity
        self._last_challenge: str | None = None

    def build_authorization_url(
        self, state: str, nonce: str, code_challenge: str
    ) -> str:
        self._last_challenge = code_challenge
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}&nonce={nonce}"

    def exchange_code_and_verify(
        self, code: str, code_verifier: str, expected_nonce: str
    ) -> GoogleVerifiedIdentity:
        assert self._last_challenge == pkce_code_challenge(code_verifier)
        return self.identity


def test_c01_oauth_pre_hijack_attacker_keeps_password_and_session():
    victim_email = "victim.oauth@beanbox-test.in"
    mock_google = _StubGoogleOAuthClient(
        GoogleVerifiedIdentity(
            provider_user_id="google-sub-victim-001",
            email=victim_email,
            email_verified=True,
            name="Victim User",
        )
    )
    settings = make_test_settings(
        GOOGLE_CLIENT_ID="test-google-client-id",
        GOOGLE_CLIENT_SECRET="test-google-client-secret",
    )
    app = create_test_app(settings=settings, google_oauth_client=mock_google)

    # Attacker pre-registers victim email with an attacker-known password & requests reset token
    attacker = new_client(app)
    attacker.headers["Origin"] = "http://localhost:3000"
    signup_res = attacker.post(
        "/api/auth/signup",
        json={
            "name": "Victim Stub",
            "email": victim_email,
            "password": "AttackerPassword@123!",
        },
    )
    assert signup_res.status_code == 201
    assert attacker.get("/api/auth/me").json()["data"]["user"]["emailVerified"] is False
    assert (
        new_client(app)
        .post("/api/auth/forgot-password", json={"email": victim_email})
        .status_code
        == 200
    )
    verify_email = next(
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "email_verification" and e.to == victim_email
    )
    reset_email = next(
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "password_reset" and e.to == victim_email
    )
    verify_tok = extract_email_token(verify_email.body)
    reset_tok = extract_email_token(reset_email.body)

    # Victim later logs in with verified Google OAuth for the same email
    victim = new_client(app)
    start = victim.get("/api/auth/google/start?next=/shop", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    cb = victim.get(
        f"/api/auth/google/callback?code=valid-code&state={state}",
        follow_redirects=False,
    )
    assert cb.status_code == 302

    # Attacker's pre-hijack session, refresh token, password, and unused tokens must all be dead
    assert attacker.get("/api/auth/me").status_code == 401
    sync_csrf(attacker)
    assert attacker.post("/api/auth/refresh").status_code == 401
    attacker_relogin = new_client(app).post(
        "/api/auth/login",
        json={"email": victim_email, "password": "AttackerPassword@123!"},
    )
    assert attacker_relogin.status_code == 401
    assert (
        app.state.repos.users.find_email_verification_token_by_hash(
            sha256_hex(verify_tok)
        )
        is None
    )
    assert (
        app.state.repos.users.find_password_reset_token_by_hash(sha256_hex(reset_tok))
        is None
    )


def test_h01_junk_bearer_header_bypasses_csrf_on_cookie_request():
    app = create_test_app()
    victim = signup_verified_client(
        app, "CSRF Victim", "csrf-bypass@beanbox-test.in", "CsrfVictim@123!"
    )
    access_cookie = victim.cookies.get("beanbox_access")
    assert access_cookie

    # Cross-origin cookie request WITHOUT X-CSRF-Token or beanbox_csrf, plus junk Bearer header -> 403 CSRF
    attacker_req = new_client(app)
    attacker_req.cookies.set("beanbox_access", access_cookie)
    attacker_req.headers["Origin"] = "https://evil-attacker.example"
    attacker_req.headers["Authorization"] = "Bearer totally-invalid-junk"

    res = attacker_req.post(
        "/api/addresses",
        json={
            "label": "Other",
            "fullName": "Attacker Drop",
            "phone": "9811111111",
            "line1": "99 Evil Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560001",
        },
    )
    assert res.status_code == 403

    # Also verify cookie vs Bearer never mix on GET: junk Bearer + valid cookie -> 401
    mixed = new_client(app)
    mixed.cookies.set("beanbox_access", access_cookie)
    mixed.headers["Authorization"] = "Bearer totally-invalid-junk"
    assert mixed.get("/api/auth/me").status_code == 401


def test_h02_mock_payment_active_in_production_without_stripe_key():
    # 1. Production refuses to boot with auto/mock or empty Stripe key
    for bad_overrides in (
        {"APP_ENV": "production", "PAYMENT_PROVIDER": "auto", "STRIPE_SECRET_KEY": ""},
        {"APP_ENV": "production", "PAYMENT_PROVIDER": "mock", "STRIPE_SECRET_KEY": "sk_test_x", "STRIPE_WEBHOOK_SECRET": "whsec_x"},
        {"APP_ENV": "production", "PAYMENT_PROVIDER": "stripe", "STRIPE_SECRET_KEY": "", "STRIPE_WEBHOOK_SECRET": "whsec_x"},
    ):
        with pytest.raises(RuntimeError):
            create_test_app(settings=make_test_settings(**bad_overrides))

    # 2. Properly configured production app returns 404 on /api/payments/mock/trigger
    prod_settings = make_test_settings(
        APP_ENV="production",
        COOKIE_SECURE="false",
        PAYMENT_PROVIDER="stripe",
        STRIPE_SECRET_KEY="sk_test_valid_prod",
        STRIPE_WEBHOOK_SECRET="whsec_valid_prod",
    )
    app = create_test_app(settings=prod_settings)
    buyer = signup_verified_client(
        app, "Free Buyer", "free-buyer@beanbox-test.in", "FreeBuyer@123!"
    )
    sync_csrf(buyer)
    mock_pay = buyer.post(
        "/api/payments/mock/trigger",
        json={"orderId": "any-order-id", "outcome": "success"},
    )
    assert mock_pay.status_code == 404


def test_h03_parallel_totp_same_code_race_allows_replay():
    app = create_test_app()
    user_client = signup_verified_client(
        app, "TOTP Race User", "totp-race@beanbox-test.in", "TotpRace@123!"
    )
    secret, _ = enable_2fa_for_logged_in_client(user_client)

    # Two concurrent password logins produce two separate challengeTokens
    c1 = new_client(app).post(
        "/api/auth/login",
        json={"email": "totp-race@beanbox-test.in", "password": "TotpRace@123!"},
    ).json()["data"]["challengeToken"]
    c2 = new_client(app).post(
        "/api/auth/login",
        json={"email": "totp-race@beanbox-test.in", "password": "TotpRace@123!"},
    ).json()["data"]["challengeToken"]

    # Force both threads to read last_used_timestep before either writes
    two_factor_repo = app.state.repos.two_factor
    orig_get = two_factor_repo.get_totp_secret
    barrier = Barrier(2, timeout=3)

    def synchronized_get(user_id: str):
        rec = orig_get(user_id)
        barrier.wait()
        return rec

    two_factor_repo.get_totp_secret = synchronized_get
    # Use +1 timestep (accepted by +-1 window skew) so enable_2fa's current step isn't already spent
    code = pyotp.TOTP(secret).at(datetime.now(timezone.utc) + timedelta(seconds=30))

    def verify(tok: str) -> int:
        res = new_client(app).post(
            "/api/auth/2fa/verify-login",
            json={"challengeToken": tok, "code": code},
        )
        return res.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(verify, c1)
        f2 = pool.submit(verify, c2)
        statuses = [f1.result(), f2.result()]

    assert statuses.count(200) == 1


def test_h04_xff_spoofing_bypasses_ip_rate_limit_and_lockout():
    settings = make_test_settings(
        TRUSTED_PROXY_COUNT=1,
        RATE_LIMIT_LOGIN_MAX=3,
    )
    app = create_test_app(settings=settings)
    client = new_client(app)

    statuses = []
    for idx in range(6):
        res = client.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": f"198.51.100.{idx + 1}, 127.0.0.1"},
            json={
                "email": f"nonexistent{idx}@beanbox-test.in",
                "password": "WrongPassword@123!",
            },
        )
        statuses.append(res.status_code)

    assert 429 in statuses


def test_h05_un2fa_admin_can_read_other_users_invoice_and_delete_review():
    app = create_test_app()
    customer = signup_verified_client(
        app, "Victim Buyer", "invoice-victim@beanbox-test.in", "VictimBuy@123!"
    )
    sync_csrf(customer)
    addr_id = customer.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": "Victim Buyer",
            "phone": "9811111111",
            "line1": "22 Indiranagar 100ft Rd",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560038",
        },
    ).json()["data"]["address"]["id"]
    assert (
        customer.post(
            "/api/cart/items",
            json={
                "productId": "prod-chikmagalur-arabica",
                "variantId": "chik-250-wb",
                "quantity": 1,
            },
        ).status_code
        == 201
    )
    order_id = customer.post("/api/orders", json={"addressId": addr_id}).json()[
        "data"
    ]["order"]["id"]
    assert (
        customer.post(
            "/api/payments/mock/trigger",
            json={"orderId": order_id, "outcome": "success"},
        ).status_code
        == 200
    )

    # Create a review to test review deletion enforcement too
    review_id = customer.post(
        "/api/products/chikmagalur-baba-budangiri-arabica/reviews",
        json={"rating": 5, "title": "Great", "comment": "Smooth cup!"},
    ).json()["data"]["review"]["id"]

    # Admin logs in WITHOUT enabling 2FA
    admin_no_2fa = login_client(
        app, "admin@beanbox.in", "Admin@1234", enable_admin_2fa=False
    )
    assert admin_no_2fa.get("/api/admin/orders").status_code == 403

    order_res = admin_no_2fa.get(f"/api/orders/{order_id}")
    assert order_res.status_code == 403
    assert order_res.json()["error"]["code"] == "ADMIN_2FA_REQUIRED"

    invoice_res = admin_no_2fa.get(f"/api/orders/{order_id}/invoice")
    assert invoice_res.status_code == 403
    assert invoice_res.json()["error"]["code"] == "ADMIN_2FA_REQUIRED"

    sync_csrf(admin_no_2fa)
    del_rev_res = admin_no_2fa.delete(f"/api/reviews/{review_id}")
    assert del_rev_res.status_code == 403
    assert del_rev_res.json()["error"]["code"] == "ADMIN_2FA_REQUIRED"


def test_h06_concurrent_cancel_order_double_releases_stock():
    app = create_test_app()
    buyer = signup_verified_client(
        app, "Race Buyer", "cancel-race@beanbox-test.in", "CancelRace@123!"
    )
    prod = buyer.get("/api/products/chikmagalur-baba-budangiri-arabica").json()[
        "data"
    ]["product"]
    variant = next(v for v in prod["variants"] if v["id"] == "chik-250-wb")
    initial_stock = variant["stock"]

    sync_csrf(buyer)
    addr_id = buyer.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": "Race Buyer",
            "phone": "9811111111",
            "line1": "14 Lavelle Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560001",
        },
    ).json()["data"]["address"]["id"]
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

    order_repo = app.state.repos.orders
    orig_find = order_repo.find_by_id_for_user
    barrier = Barrier(2, timeout=3)

    def barrier_find(oid: str, uid: str):
        order = orig_find(oid, uid)
        barrier.wait()
        return order

    order_repo.find_by_id_for_user = barrier_find

    access = buyer.cookies.get("beanbox_access")
    csrf = buyer.cookies.get("beanbox_csrf")
    assert access and csrf

    def fire_cancel() -> int:
        c = new_client(app)
        c.headers["Origin"] = "http://localhost:3000"
        c.cookies.set("beanbox_access", access)
        c.cookies.set("beanbox_csrf", csrf)
        c.headers["X-CSRF-Token"] = csrf
        return c.post(f"/api/orders/{order_id}/cancel", json={"reason": "race"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(fire_cancel)
        f2 = pool.submit(fire_cancel)
        statuses = [f1.result(), f2.result()]

    order_repo.find_by_id_for_user = orig_find
    assert sorted(statuses) == [200, 409]

    after_prod = new_client(app).get(
        "/api/products/chikmagalur-baba-budangiri-arabica"
    ).json()["data"]["product"]
    after_stock = next(v for v in after_prod["variants"] if v["id"] == "chik-250-wb")[
        "stock"
    ]
    assert after_stock == initial_stock

    # Concurrent duplicate webhook failure delivery must only claim & release stock once
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
    order2_id = buyer.post("/api/orders", json={"addressId": addr_id}).json()["data"][
        "order"
    ]["id"]
    raw_wh, sig_wh = build_signed_webhook(
        app.state.settings.mock_webhook_secret,
        {
            "id": "evt_dup_race_001",
            "type": "payment_intent.payment_failed",
            "data": {"orderId": order2_id},
        },
    )

    def fire_webhook() -> dict:
        r = new_client(app).post(
            "/api/payments/webhook",
            content=raw_wh,
            headers={"x-mock-signature": sig_wh, "content-type": "application/json"},
        )
        assert r.status_code == 200
        return r.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        w1 = pool.submit(fire_webhook)
        w2 = pool.submit(fire_webhook)
        wh_results = [w1.result(), w2.result()]

    assert sorted([bool(r["duplicate"]) for r in wh_results]) == [False, True]
    after_wh_prod = new_client(app).get(
        "/api/products/chikmagalur-baba-budangiri-arabica"
    ).json()["data"]["product"]
    after_wh_stock = next(
        v for v in after_wh_prod["variants"] if v["id"] == "chik-250-wb"
    )["stock"]
    assert after_wh_stock == initial_stock


def test_m01_grace_refresh_token_replayable_many_times_within_window():
    app = create_test_app()
    client = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    r0 = client.cookies.get("beanbox_refresh")
    csrf0 = client.cookies.get("beanbox_csrf")
    assert r0 and csrf0

    # Victim rotates R0 -> R1
    assert client.post("/api/auth/refresh").status_code == 200

    # Replay R0 5 times inside the 10s grace window: capped at 3 uses; 4th revokes family
    replay_statuses = []
    for _ in range(5):
        att = new_client(app)
        att.headers["Origin"] = "http://localhost:3000"
        att.cookies.set("beanbox_refresh", r0)
        att.cookies.set("beanbox_csrf", csrf0)
        att.headers["X-CSRF-Token"] = csrf0
        replay_statuses.append(att.post("/api/auth/refresh").status_code)

    assert replay_statuses == [200, 200, 200, 401, 401]
    # Victim's R1 is now revoked too because 4th replay triggered family revocation
    sync_csrf(client)
    assert client.post("/api/auth/refresh").status_code == 401


def test_m02_2fa_challenge_jti_reusable_across_second_worker_instance():
    worker_a = create_test_app()
    # Second worker sharing DB/repos & JWT secret
    worker_b = create_app(
        settings=worker_a.state.settings,
        repos=worker_a.state.repos,
    )

    user_client = signup_verified_client(
        worker_a, "Multi Worker User", "worker2fa@beanbox-test.in", "Worker2fa@123!"
    )
    _, recovery_codes = enable_2fa_for_logged_in_client(user_client)

    challenge = (
        new_client(worker_a)
        .post(
            "/api/auth/login",
            json={"email": "worker2fa@beanbox-test.in", "password": "Worker2fa@123!"},
        )
        .json()["data"]["challengeToken"]
    )

    # Challenge consumed on worker A
    r_a = new_client(worker_a).post(
        "/api/auth/2fa/verify-login",
        json={"challengeToken": challenge, "code": recovery_codes[0]},
    )
    assert r_a.status_code == 200

    # Replay EXACT same challengeToken on worker B with recovery_codes[1]
    r_b = new_client(worker_b).post(
        "/api/auth/2fa/verify-login",
        json={"challengeToken": challenge, "code": recovery_codes[1]},
    )
    assert r_b.status_code == 401


def test_m03_attacker_locks_victim_account_from_different_ip():
    settings = make_test_settings(
        TRUSTED_PROXY_COUNT=1,
        LOGIN_MAX_FAILURES=5,
        RATE_LIMIT_LOGIN_MAX=100,
    )
    app = create_test_app(settings=settings)

    attacker = new_client(app)
    for _ in range(5):
        res = attacker.post(
            "/api/auth/login",
            headers={"X-Forwarded-For": "203.0.113.77"},
            json={"email": "arjun@beanbox.in", "password": "WrongGuess@123!"},
        )
        assert res.status_code == 401

    # Victim attempts legitimate login with correct password from clean home IP -> succeeds and resets counters
    victim_res = new_client(app).post(
        "/api/auth/login",
        headers={"X-Forwarded-For": "198.51.100.42"},
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    )
    assert victim_res.status_code == 200
    assert app.state.repos.login_attempts.get_by_key("acct:arjun@beanbox.in") is None

    # Stale failures (> 15 min old) reset failed_count instead of accumulating toward lock
    for idx in range(4):
        new_client(app).post(
            "/api/auth/login",
            headers={"X-Forwarded-For": f"192.0.2.{idx + 1}"},
            json={"email": "arjun@beanbox.in", "password": "WrongGuess@123!"},
        )
    rec = app.state.repos.login_attempts._records["acct:arjun@beanbox.in"]
    assert rec.failed_count == 4
    rec.last_failed_at = (
        (datetime.now(timezone.utc) - timedelta(minutes=16))
        .isoformat()
        .replace("+00:00", "Z")
    )
    new_client(app).post(
        "/api/auth/login",
        headers={"X-Forwarded-For": "192.0.2.99"},
        json={"email": "arjun@beanbox.in", "password": "WrongGuess@123!"},
    )
    assert (
        app.state.repos.login_attempts.get_by_key("acct:arjun@beanbox.in").failed_count
        == 1
    )

    # Sustained distributed spray of 30 failures across IPs locks per-email threshold
    for idx in range(29):
        new_client(app).post(
            "/api/auth/login",
            headers={"X-Forwarded-For": f"198.51.101.{idx + 1}"},
            json={"email": "arjun@beanbox.in", "password": "WrongGuess@123!"},
        )
    blocked = new_client(app).post(
        "/api/auth/login",
        headers={"X-Forwarded-For": "198.51.100.43"},
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_m04_concurrent_signup_duplicate_email_and_duplicate_sku_in_memory():
    app = create_test_app()
    user_repo = app.state.repos.users
    orig_find = user_repo.find_by_email
    barrier = Barrier(2, timeout=3)

    def racing_find(email: str):
        found = orig_find(email)
        if email == "race-dup@beanbox-test.in":
            barrier.wait()
        return found

    user_repo.find_by_email = racing_find

    def do_signup(idx: int) -> int:
        res = new_client(app).post(
            "/api/auth/signup",
            json={
                "name": f"Race User {idx}",
                "email": "race-dup@beanbox-test.in",
                "password": "RacePassword@123!",
            },
        )
        return res.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(do_signup, 1)
        f2 = pool.submit(do_signup, 2)
        statuses = [f1.result(), f2.result()]

    user_repo.find_by_email = orig_find
    assert sorted(statuses) == [201, 409]

    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin)
    dup_sku = admin.post(
        "/api/admin/products",
        json={
            "name": "Duplicate SKU Coffee",
            "slug": "duplicate-sku-coffee",
            "shortDescription": "Testing SKU parity between memory and Postgres.",
            "description": "Postgres enforces UNIQUE(sku) while InMemoryProductRepository accepts duplicate SKUs.",
            "category": "beans",
            "roastLevel": "medium",
            "origin": "Coorg, Karnataka",
            "tastingNotes": ["Cocoa"],
            "images": ["/images/products/beans-medium.svg"],
            "variants": [
                {
                    "sku": "CHIK-250-WB",
                    "size": "250g",
                    "grind": "whole_bean",
                    "label": "250g · Whole Bean",
                    "pricePaise": 49900,
                    "stock": 10,
                }
            ],
        },
    )
    assert dup_sku.status_code == 409


def test_l01_prevent_last_admin_demotion_and_concurrent_race():
    app = create_test_app()
    second = signup_verified_client(
        app, "Second Admin", "second-admin@beanbox-test.in", "SecondAdmin@123!"
    )
    second_id = second.get("/api/auth/me").json()["data"]["user"]["id"]
    admin1 = login_client(app, "admin@beanbox.in", "Admin@1234")
    sync_csrf(admin1)

    # Promote second user to admin and enable 2FA for them
    assert (
        admin1.patch(
            f"/api/admin/users/{second_id}/role", json={"role": "admin"}
        ).status_code
        == 200
    )
    admin2 = login_client(app, "second-admin@beanbox-test.in", "SecondAdmin@123!")
    sync_csrf(admin2)
    admin1_id = admin1.get("/api/auth/me").json()["data"]["user"]["id"]

    # Synchronize right before update_role_safe so both requests pass require_admin & race atomically
    user_repo = app.state.repos.users
    orig_find = user_repo.find_by_id
    demote_barrier = Barrier(2, timeout=3)

    def sync_target_lookup(uid: str):
        return orig_find(uid)

    orig_update_role = user_repo.update_role_safe

    def synchronized_update_role(uid: str, next_role):
        if next_role == "customer":
            demote_barrier.wait()
        return orig_update_role(uid, next_role)

    user_repo.update_role_safe = synchronized_update_role

    def demote(client, target_id: str) -> tuple[int, str]:
        r = client.patch(
            f"/api/admin/users/{target_id}/role", json={"role": "customer"}
        )
        return r.status_code, r.text

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(demote, admin1, second_id)
        f2 = pool.submit(demote, admin2, admin1_id)
        results = [f1.result(), f2.result()]

    user_repo.update_role_safe = orig_update_role
    user_repo.find_by_id = orig_find
    statuses = [r[0] for r in results]
    assert sorted(statuses) == [200, 409], results
    users, _ = app.state.repos.users.list(1, 50)
    assert sum(1 for u in users if u.role == "admin") == 1


def test_l02_stripe_error_mapped_to_app_error_and_pg_pool_timeouts():
    from pathlib import Path

    import stripe

    from app.models.domain import OrderAddressSnapshot, OrderPricing
    from app.services.payment_service import (
        CreateCheckoutSessionInput,
        StripePaymentProvider,
    )
    from app.utils.errors import AppError

    provider = StripePaymentProvider("sk_test_dummy", "whsec_dummy")

    def boom(*args, **kwargs):
        raise stripe.APIConnectionError("Simulated network timeout")

    provider._client.v1.checkout.sessions.create = boom
    assert create_test_app().state.repos.orders is not None

    from app.models.domain import Order

    fake_order = Order(
        id="ord-1",
        order_number="BB-TEST-001",
        user_id="user-1",
        status="pending",
        payment_status="unpaid",
        payment_provider="stripe",
        shipping_address=OrderAddressSnapshot(
            label="Home",
            full_name="Test User",
            phone="9811111111",
            line1="100 MG Road",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
        ),
        pricing=OrderPricing(
            items_subtotal_paise=49900,
            discount_paise=0,
            taxable_amount_paise=49900,
            gst_rate=0.05,
            gst_paise=2495,
            cgst_paise=1247,
            sgst_paise=1248,
            shipping_paise=0,
            total_paise=52395,
        ),
        items=[],
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises(AppError) as exc_info:
        provider.create_checkout_session(
            CreateCheckoutSessionInput(
                order=fake_order,
                customer_email="u@example.com",
                success_url="http://localhost:3000/ok",
                cancel_url="http://localhost:3000/cancel",
            )
        )
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "PAYMENT_PROVIDER_ERROR"

    db_source = (
        Path(__file__).resolve().parents[1] / "app" / "repositories" / "supabase" / "db.py"
    ).read_text(encoding="utf-8")
    assert "timeout=10.0" in db_source
    assert "connect_timeout" in db_source
    assert "statement_timeout=10000" in db_source


def test_i02_explicit_cors_and_pinned_requirements():
    from pathlib import Path

    app = create_test_app()
    client = new_client(app)
    preflight = client.options(
        "/api/products",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token",
        },
    )
    assert preflight.status_code == 200
    assert "*" not in preflight.headers.get("access-control-allow-methods", "*")
    assert "*" not in preflight.headers.get("access-control-allow-headers", "*")

    req_lines = [
        line.strip()
        for line in (Path(__file__).resolve().parents[1] / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert req_lines
    assert all("==" in line for line in req_lines)
