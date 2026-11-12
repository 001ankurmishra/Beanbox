from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import bcrypt
import jwt
import pyotp

from app.services.google_oauth_service import (
    GoogleOAuthClient,
    GoogleVerifiedIdentity,
    pkce_code_challenge,
)
from app.utils.errors import UnauthorizedError
from app.utils.security import sha256_hex
from tests.conftest import (
    create_test_app,
    enable_2fa_for_logged_in_client,
    extract_email_token,
    login_client,
    make_test_settings,
    new_client,
    sync_csrf,
)


class MockGoogleOAuthClient(GoogleOAuthClient):
    def __init__(self, identity: GoogleVerifiedIdentity, fail_nonce: bool = False):
        self.identity = identity
        self.fail_nonce = fail_nonce
        self.last_code_challenge: str | None = None
        self.last_nonce: str | None = None
        self.last_verified_code_verifier: str | None = None

    def build_authorization_url(
        self, state: str, nonce: str, code_challenge: str
    ) -> str:
        self.last_code_challenge = code_challenge
        self.last_nonce = nonce
        return (
            "https://accounts.google.com/o/oauth2/v2/auth"
            f"?state={state}&nonce={nonce}&code_challenge={code_challenge}&code_challenge_method=S256"
        )

    def exchange_code_and_verify(
        self, code: str, code_verifier: str, expected_nonce: str
    ) -> GoogleVerifiedIdentity:
        self.last_verified_code_verifier = code_verifier
        assert self.last_code_challenge == pkce_code_challenge(code_verifier)
        if self.fail_nonce or expected_nonce != self.last_nonce:
            raise UnauthorizedError("Invalid OAuth nonce", code="OAUTH_INVALID_NONCE")
        if code != "valid-google-code":
            raise UnauthorizedError("Invalid auth code", code="OAUTH_EXCHANGE_FAILED")
        return self.identity


def test_access_token_claims_expiry_and_production_cookie_flags():
    settings = make_test_settings(APP_ENV="production", COOKIE_SECURE="auto")
    app = create_test_app(settings=settings)

    # Simulate HTTPS production client so Secure cookies round-trip cleanly
    from fastapi.testclient import TestClient

    client = TestClient(app, base_url="https://api.beanbox.in")
    client.headers["Origin"] = settings.frontend_url
    res = client.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    )
    assert res.status_code == 200

    access_jwt = res.cookies.get("beanbox_access")
    refresh_raw = res.cookies.get("beanbox_refresh")
    csrf_tok = res.cookies.get("beanbox_csrf")
    assert access_jwt and refresh_raw and csrf_tok

    decoded = jwt.decode(access_jwt, settings.jwt_secret, algorithms=["HS256"])
    assert decoded["sub"] == "22222222-2222-4222-8222-222222222222"
    assert decoded["role"] == "customer"
    assert decoded["typ"] == "access"
    assert decoded["sid"]
    assert decoded["jti"]
    assert decoded["exp"] - decoded["iat"] == 900  # 15 minutes

    set_cookie_all = ", ".join(res.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie_all
    assert "Secure" in set_cookie_all
    assert "SameSite=lax" in set_cookie_all
    assert "Path=/api/auth" in set_cookie_all

    # Stored refresh token in DB is SHA-256 hash, never raw secret
    session = app.state.repos.sessions.find_by_id(decoded["sid"])
    assert session is not None
    assert session.refresh_token_hash == sha256_hex(refresh_raw)
    assert session.refresh_token_hash != refresh_raw

    # Expired access token must be rejected
    expired_payload = {**decoded, "exp": int((datetime.now(timezone.utc) - timedelta(seconds=5)).timestamp())}
    expired_jwt = jwt.encode(expired_payload, settings.jwt_secret, algorithm="HS256")
    anon = new_client(app)
    exp_res = anon.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_jwt}"})
    assert exp_res.status_code == 401


def test_refresh_rotation_and_reuse_detection_revokes_family():
    app = create_test_app()
    client = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    r1 = client.cookies.get("beanbox_refresh")
    a1 = client.cookies.get("beanbox_access")
    assert r1 and a1

    # Rotation 1: R1 -> R2
    ref1 = client.post("/api/auth/refresh")
    assert ref1.status_code == 200
    sync_csrf(client)
    r2 = client.cookies.get("beanbox_refresh")
    a2 = client.cookies.get("beanbox_access")
    assert r2 and r2 != r1
    assert a2 and a2 != a1

    # Rotation 2: R2 -> R3
    ref2 = client.post("/api/auth/refresh")
    assert ref2.status_code == 200
    sync_csrf(client)
    r3 = client.cookies.get("beanbox_refresh")
    a3 = client.cookies.get("beanbox_access")
    assert r3 and r3 != r2

    # Attacker replays old rotated R1 -> triggers reuse detection and revokes family!
    attacker = new_client(app)
    attacker.headers["Origin"] = "http://localhost:3000"
    attacker.headers["X-CSRF-Token"] = client.cookies.get("beanbox_csrf") or ""
    attacker.cookies.set("beanbox_csrf", client.cookies.get("beanbox_csrf") or "")
    attacker.cookies.set("beanbox_refresh", r1)

    reuse_res = attacker.post("/api/auth/refresh")
    assert reuse_res.status_code == 401
    assert reuse_res.json()["error"]["code"] == "REFRESH_TOKEN_REUSE_DETECTED"

    # Victim's newest R3 and A3 are immediately dead because family was revoked
    assert client.get("/api/auth/me").status_code == 401
    assert (
        new_client(app)
        .get("/api/auth/me", headers={"Authorization": f"Bearer {a3}"})
        .status_code
        == 401
    )
    dead_ref = client.post("/api/auth/refresh")
    assert dead_ref.status_code == 401

    logs, _ = app.state.repos.audit_logs.list(
        page=1, limit=20, event_type="refresh_reuse_detected"
    )
    assert len(logs) >= 1
    assert logs[0].user_id == "22222222-2222-4222-8222-222222222222"


def test_brute_force_lockout_exponential_backoff_and_no_enumeration():
    app = create_test_app()
    client = new_client(app)

    # Identical forgot-password response whether email exists or not
    f_real = client.post("/api/auth/forgot-password", json={"email": "arjun@beanbox.in"})
    f_fake = client.post("/api/auth/forgot-password", json={"email": "missing@example.in"})
    assert f_real.status_code == 200
    assert f_fake.status_code == 200
    assert f_real.json() == f_fake.json()

    # 5 failed attempts on Arjun -> generic Invalid credentials each time
    for _ in range(5):
        r = client.post(
            "/api/auth/login",
            json={"email": "arjun@beanbox.in", "password": "WrongPassword99"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["message"] == "Invalid credentials"

    # 6th attempt even with CORRECT password must be locked
    locked = client.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    )
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"

    # Simulate expiry of first 15-min lock, then fail once more -> exponential backoff doubles to 30 min
    rec = app.state.repos.login_attempts.get_by_key("acct:arjun@beanbox.in")
    assert rec is not None and rec.lockout_level == 1
    past_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    app.state.repos.login_attempts._records["acct:arjun@beanbox.in"].locked_until = past_iso
    app.state.repos.login_attempts._records["ip:testclient"].locked_until = past_iso

    fail6 = client.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "WrongPassword99"},
    )
    assert fail6.status_code == 401
    rec2 = app.state.repos.login_attempts.get_by_key("acct:arjun@beanbox.in")
    assert rec2 is not None and rec2.lockout_level == 2
    lock_dt = datetime.fromisoformat(rec2.locked_until.replace("Z", "+00:00"))
    # Lockout duration grew to ~30 minutes
    assert (lock_dt - datetime.now(timezone.utc)).total_seconds() > 25 * 60


def test_password_policy_argon2_rehash_and_change_password():
    app = create_test_app()
    client = new_client(app)

    # Policy checks on signup
    assert (
        client.post(
            "/api/auth/signup",
            json={"name": "Short Pw", "email": "s@example.in", "password": "short"},
        ).status_code
        == 400
    )
    common_res = client.post(
        "/api/auth/signup",
        json={"name": "Common Pw", "email": "c@example.in", "password": "password1234"},
    )
    assert common_res.status_code == 400
    assert common_res.json()["error"]["code"] == "COMMON_PASSWORD"

    contains_email = client.post(
        "/api/auth/signup",
        json={
            "name": "Email Pw",
            "email": "roast@example.in",
            "password": "My-roast@example.in-secret",
        },
    )
    assert contains_email.status_code == 400
    assert contains_email.json()["error"]["code"] == "PASSWORD_CONTAINS_EMAIL"

    # Transparent bcrypt -> argon2id rehash on login
    old_bcrypt = bcrypt.hashpw(b"LegacyCoffee@123", bcrypt.gensalt(rounds=4)).decode()
    from app.repositories.interfaces import CreateUserInput

    legacy_user = app.state.repos.users.create(
        CreateUserInput(
            name="Legacy Roaster",
            email="legacy@beanbox.in",
            password_hash=old_bcrypt,
            role="customer",
            email_verified=True,
        )
    )
    assert legacy_user.password_hash.startswith("$2b$")

    leg_session1 = login_client(app, "legacy@beanbox.in", "LegacyCoffee@123")
    upgraded_user = app.state.repos.users.find_by_id(legacy_user.id)
    assert upgraded_user is not None
    assert upgraded_user.password_hash.startswith("$argon2id$")

    # Second concurrent session
    leg_session2 = login_client(app, "legacy@beanbox.in", "LegacyCoffee@123")

    # Wrong current password rejected
    bad_chg = leg_session1.post(
        "/api/auth/change-password",
        json={"currentPassword": "Wrong", "newPassword": "EvenStronger@2026"},
    )
    assert bad_chg.status_code == 401

    # Change password succeeds and revokes OTHER session (leg_session2)
    chg = leg_session1.post(
        "/api/auth/change-password",
        json={
            "currentPassword": "LegacyCoffee@123",
            "newPassword": "EvenStronger@2026",
        },
    )
    assert chg.status_code == 200
    assert chg.json()["data"]["revokedOtherSessions"] == 1
    assert leg_session1.get("/api/auth/me").status_code == 200
    assert leg_session2.get("/api/auth/me").status_code == 401


def test_email_verification_blocks_checkout_and_resend_cooldown():
    app = create_test_app()
    client = new_client(app)
    client.headers["Origin"] = "http://localhost:3000"

    s_res = client.post(
        "/api/auth/signup",
        json={
            "name": "Kabir Verma",
            "email": "kabir@example.in",
            "password": "StrongCoffee@2026",
        },
    )
    assert s_res.status_code == 201
    sync_csrf(client)

    # Unverified user CAN browse, add to cart, save address, and preview checkout
    assert client.get("/api/products").status_code == 200
    assert (
        client.post(
            "/api/cart/items",
            json={
                "productId": "prod-chikmagalur-arabica",
                "variantId": "chik-250-wb",
                "quantity": 1,
            },
        ).status_code
        == 201
    )
    addr_res = client.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": "Kabir Verma",
            "phone": "9812345678",
            "line1": "24 Connaught Place",
            "city": "New Delhi",
            "state": "Delhi",
            "postalCode": "110001",
        },
    )
    assert addr_res.status_code == 201
    addr_id = addr_res.json()["data"]["address"]["id"]
    assert client.post("/api/checkout/preview", json={"addressId": addr_id}).status_code == 200

    # Unverified user CANNOT place order
    ord_blocked = client.post("/api/orders", json={"addressId": addr_id})
    assert ord_blocked.status_code == 403
    assert ord_blocked.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"

    # Immediate resend hits 60s cooldown
    resend_cool = client.post("/api/auth/verify-email/resend")
    assert resend_cool.status_code == 429
    assert resend_cool.json()["error"]["code"] == "VERIFICATION_RESEND_COOLDOWN"

    # Verify via emailed token (single-use)
    v_email = next(
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "email_verification" and e.to == "kabir@example.in"
    )
    token = extract_email_token(v_email.body)
    v_res = client.post("/api/auth/verify-email", json={"token": token})
    assert v_res.status_code == 200
    assert v_res.json()["data"]["user"]["emailVerified"] is True

    # Token cannot be reused
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 400

    # Now order placement succeeds
    ord_ok = client.post("/api/orders", json={"addressId": addr_id})
    assert ord_ok.status_code == 201


def test_csrf_double_submit_and_origin_enforcement():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    valid_csrf = arjun.cookies.get("beanbox_csrf")
    access_jwt = arjun.cookies.get("beanbox_access")

    # 1. Missing X-CSRF-Token header rejected
    no_csrf = new_client(app)
    no_csrf.cookies.update(arjun.cookies)
    no_csrf.headers["Origin"] = "http://localhost:3000"
    r1 = no_csrf.post("/api/wishlist/prod-araku-organic")
    assert r1.status_code == 403
    assert r1.json()["error"]["code"] == "CSRF_TOKEN_INVALID"

    # 2. Mismatched X-CSRF-Token rejected
    bad_csrf = new_client(app)
    bad_csrf.cookies.update(arjun.cookies)
    bad_csrf.headers["Origin"] = "http://localhost:3000"
    bad_csrf.headers["X-CSRF-Token"] = "tampered-token-value-123456"
    assert bad_csrf.post("/api/wishlist/prod-araku-organic").status_code == 403

    # 3. Evil Origin rejected even with matching CSRF token
    evil_origin = new_client(app)
    evil_origin.cookies.update(arjun.cookies)
    evil_origin.headers["X-CSRF-Token"] = valid_csrf or ""
    evil_origin.headers["Origin"] = "https://evil-phishing.example"
    r3 = evil_origin.post("/api/wishlist/prod-araku-organic")
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"

    # 4. Missing both Origin and Referer rejected
    no_origin = new_client(app)
    no_origin.cookies.update(arjun.cookies)
    no_origin.headers["X-CSRF-Token"] = valid_csrf or ""
    r4 = no_origin.post("/api/wishlist/prod-araku-organic")
    assert r4.status_code == 403
    assert r4.json()["error"]["code"] == "CSRF_ORIGIN_MISSING"

    # 5. Valid Referer fallback works when Origin omitted
    referer_ok = new_client(app)
    referer_ok.cookies.update(arjun.cookies)
    referer_ok.headers["X-CSRF-Token"] = valid_csrf or ""
    referer_ok.headers["Referer"] = "http://localhost:3000/shop"
    assert referer_ok.post("/api/wishlist/prod-araku-organic").status_code == 201

    # 6. Bearer token API calls without cookies bypass CSRF check
    bearer = new_client(app)
    assert (
        bearer.delete(
            "/api/wishlist/prod-araku-organic",
            headers={"Authorization": f"Bearer {access_jwt}"},
        ).status_code
        == 200
    )


def test_sessions_list_revoke_one_and_logout_all():
    app = create_test_app()
    desktop = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    mobile = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    sess_list = desktop.get("/api/auth/sessions").json()["data"]["items"]
    assert len(sess_list) == 2
    assert sum(1 for s in sess_list if s["isCurrent"]) == 1
    assert all("refreshTokenHash" not in s for s in sess_list)

    mobile_sid = next(s["id"] for s in sess_list if not s["isCurrent"])
    rev_res = desktop.delete(f"/api/auth/sessions/{mobile_sid}")
    assert rev_res.status_code == 200

    # Revoked device's access token AND refresh token fail immediately
    assert mobile.get("/api/auth/me").status_code == 401
    assert mobile.post("/api/auth/refresh").status_code == 401
    assert desktop.get("/api/auth/me").status_code == 200

    # Log out all devices
    assert desktop.post("/api/auth/logout-all").status_code == 200
    assert desktop.get("/api/auth/me").status_code == 401


def test_totp_2fa_flow_encrypted_at_rest_and_admin_required():
    app = create_test_app()

    # Admin without 2FA can sign in to configure 2FA, but /api/admin/* is blocked
    admin_no_2fa = login_client(
        app, "admin@beanbox.in", "Admin@1234", enable_admin_2fa=False
    )
    blocked = admin_no_2fa.get("/api/admin/stats")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "ADMIN_2FA_REQUIRED"

    # Setup 2FA -> stores encrypted secret at rest, returns QR SVG
    setup = admin_no_2fa.post("/api/auth/2fa/setup")
    assert setup.status_code == 200
    secret = setup.json()["data"]["secret"]
    qr_url = setup.json()["data"]["qrDataUrl"]
    assert qr_url.startswith("data:image/svg+xml;base64,")

    totp_row = app.state.repos.two_factor.get_totp_secret(
        "11111111-1111-4111-8111-111111111111"
    )
    assert totp_row is not None
    assert totp_row.encrypted_secret.startswith("v1:")
    assert secret not in totp_row.encrypted_secret

    # Invalid TOTP code rejected on enable
    assert (
        admin_no_2fa.post("/api/auth/2fa/enable", json={"code": "000000"}).status_code
        == 400
    )

    # Valid TOTP enables 2FA & returns 10 recovery codes
    enable = admin_no_2fa.post(
        "/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}
    )
    assert enable.status_code == 200
    recovery_codes = enable.json()["data"]["recoveryCodes"]
    assert len(recovery_codes) == 10

    # Admin route now works & disabling 2FA is forbidden for admin
    assert admin_no_2fa.get("/api/admin/stats").status_code == 200
    assert (
        admin_no_2fa.post(
            "/api/auth/2fa/disable",
            json={"code": recovery_codes[0], "password": "Admin@1234"},
        ).status_code
        == 403
    )

    # New admin login requires 2-step verification
    step1_client = new_client(app)
    step1_client.headers["Origin"] = "http://localhost:3000"
    s1 = step1_client.post(
        "/api/auth/login", json={"email": "admin@beanbox.in", "password": "Admin@1234"}
    )
    assert s1.status_code == 200
    assert s1.json()["data"]["requiresTwoFactor"] is True
    challenge = s1.json()["data"]["challengeToken"]
    assert "beanbox_access" not in s1.cookies

    # Wrong code fails
    assert (
        step1_client.post(
            "/api/auth/2fa/verify-login",
            json={"challengeToken": challenge, "code": "000000"},
        ).status_code
        == 401
    )

    # Single-use recovery code works for login step 2, then cannot be reused
    s2 = step1_client.post(
        "/api/auth/2fa/verify-login",
        json={"challengeToken": challenge, "code": recovery_codes[0]},
    )
    assert s2.status_code == 200
    sync_csrf(step1_client)
    assert step1_client.get("/api/admin/stats").status_code == 200

    # Replay of same challenge token rejected
    assert (
        step1_client.post(
            "/api/auth/2fa/verify-login",
            json={"challengeToken": challenge, "code": recovery_codes[1]},
        ).status_code
        == 401
    )

    # Customer can enable and then disable 2FA with password + recovery code
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    _, arjun_codes = enable_2fa_for_logged_in_client(arjun)
    dis = arjun.post(
        "/api/auth/2fa/disable",
        json={"code": arjun_codes[0], "password": "Coffee@1234"},
    )
    assert dis.status_code == 200
    assert dis.json()["data"]["totpEnabled"] is False


def test_rbac_rechecks_db_role_and_audit_logs():
    app = create_test_app()
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")

    # Promote Arjun to admin, log him in cleanly & capture his 2FA secret so we can pass Step 2 later
    prom = admin.patch(
        "/api/admin/users/22222222-2222-4222-8222-222222222222/role",
        json={"role": "admin"},
    )
    assert prom.status_code == 200
    assert prom.json()["data"]["user"]["role"] == "admin"

    arjun_admin = login_client(
        app, "arjun@beanbox.in", "Coffee@1234", enable_admin_2fa=False
    )
    _, arjun_recovery = enable_2fa_for_logged_in_client(arjun_admin)
    assert arjun_admin.get("/api/admin/stats").status_code == 200
    arjun_admin_jwt = arjun_admin.cookies.get("beanbox_access")

    # Demote Arjun back to customer via original admin
    dem = admin.patch(
        "/api/admin/users/22222222-2222-4222-8222-222222222222/role",
        json={"role": "customer"},
    )
    assert dem.status_code == 200

    # Even if an old token existed, /api/admin/* must reject
    assert (
        new_client(app)
        .get("/api/admin/stats", headers={"Authorization": f"Bearer {arjun_admin_jwt}"})
        .status_code
        == 401
    )

    # Re-login Arjun as customer (completing 2FA Step 2) and test stale role="admin" JWT is blocked by DB role re-check
    arjun_new = new_client(app)
    arjun_new.headers["Origin"] = "http://localhost:3000"
    step1 = arjun_new.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    ).json()["data"]
    assert step1["requiresTwoFactor"] is True
    step2 = arjun_new.post(
        "/api/auth/2fa/verify-login",
        json={"challengeToken": step1["challengeToken"], "code": arjun_recovery[0]},
    )
    assert step2.status_code == 200
    sync_csrf(arjun_new)
    arjun_sid = arjun_new.get("/api/auth/sessions").json()["data"]["items"][0]["id"]

    # Simulate stale role="admin" JWT crafted before DB downgrade
    stale_admin_jwt = jwt.encode(
        {
            "sub": "22222222-2222-4222-8222-222222222222",
            "role": "admin",
            "sid": arjun_sid,
            "jti": "stale-jti",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp()),
            "typ": "access",
        },
        app.state.settings.jwt_secret,
        algorithm="HS256",
    )
    stale_res = new_client(app).get(
        "/api/admin/stats", headers={"Authorization": f"Bearer {stale_admin_jwt}"}
    )
    assert stale_res.status_code == 403

    # Admin audit logs endpoint works and never leaks sensitive fields
    audit_res = admin.get("/api/admin/audit-logs?limit=50")
    assert audit_res.status_code == 200
    events = audit_res.json()["data"]["items"]
    event_types = {e["eventType"] for e in events}
    assert "role_changed" in event_types
    assert "2fa_enabled" in event_types
    for e in events:
        assert "requestId" in e and e["requestId"]
        assert "ip" in e and e["ip"]
        assert "Admin@1234" not in str(e)


def test_google_oauth_pkce_state_nonce_and_graceful_disable():
    # Disabled cleanly when GOOGLE_CLIENT_ID/SECRET are blank
    disabled_app = create_test_app()
    c0 = new_client(disabled_app)
    assert c0.get("/api/auth/providers").json()["data"]["googleOAuthEnabled"] is False
    assert c0.get("/api/auth/google/start").status_code == 503

    # Enabled with MockGoogleOAuthClient for PKCE + state + nonce + account linking
    mock_google = MockGoogleOAuthClient(
        GoogleVerifiedIdentity(
            provider_user_id="google-sub-arjun-001",
            email="arjun@beanbox.in",
            email_verified=True,
            name="Arjun Sharma",
        )
    )
    settings = make_test_settings(
        GOOGLE_CLIENT_ID="test-google-client-id",
        GOOGLE_CLIENT_SECRET="test-google-client-secret",
    )
    app = create_test_app(settings=settings, google_oauth_client=mock_google)
    client = new_client(app)
    assert client.get("/api/auth/providers").json()["data"]["googleOAuthEnabled"] is True

    # Open redirect attempt '//evil.com' sanitized to '/'
    start = client.get(
        "/api/auth/google/start?next=//evil.com", follow_redirects=False
    )
    assert start.status_code == 302
    assert "beanbox_oauth_tx" in start.cookies
    location = start.headers["location"]
    qs = parse_qs(urlparse(location).query)
    state = qs["state"][0]
    assert qs["code_challenge_method"][0] == "S256"

    # Tampered state rejected
    bad_state = client.get(
        "/api/auth/google/callback?code=valid-google-code&state=wrong-state",
        follow_redirects=False,
    )
    assert bad_state.status_code == 400

    # Wrong nonce rejected
    mock_google.fail_nonce = True
    bad_nonce = client.get(
        f"/api/auth/google/callback?code=valid-google-code&state={state}",
        follow_redirects=False,
    )
    assert bad_nonce.status_code == 401
    assert bad_nonce.json()["error"]["code"] == "OAUTH_INVALID_NONCE"
    mock_google.fail_nonce = False

    # Valid callback links existing account & redirects to sanitized '/'
    ok = client.get(
        f"/api/auth/google/callback?code=valid-google-code&state={state}",
        follow_redirects=False,
    )
    assert ok.status_code == 302
    assert ok.headers["location"] == "http://localhost:3000/"
    assert "beanbox_access" in ok.cookies
    assert "beanbox_refresh" in ok.cookies
    assert (
        app.state.repos.oauth_accounts.find_by_provider_user(
            "google", "google-sub-arjun-001"
        )
        is not None
    )

    # New Google user creation
    mock_google.identity = GoogleVerifiedIdentity(
        provider_user_id="google-sub-new-999",
        email="new.google.user@example.in",
        email_verified=True,
        name="Divya Nair",
    )
    c2 = new_client(app)
    s2 = c2.get("/api/auth/google/start?next=/shop", follow_redirects=False)
    st2 = parse_qs(urlparse(s2.headers["location"]).query)["state"][0]
    ok2 = c2.get(
        f"/api/auth/google/callback?code=valid-google-code&state={st2}",
        follow_redirects=False,
    )
    assert ok2.status_code == 302
    assert ok2.headers["location"] == "http://localhost:3000/shop"
    created = app.state.repos.users.find_by_email("new.google.user@example.in")
    assert created is not None and created.email_verified is True


def test_strict_endpoint_rate_limits():
    settings = make_test_settings(
        RATE_LIMIT_LOGIN_MAX=3,
        RATE_LIMIT_SIGNUP_MAX=2,
        RATE_LIMIT_RESET_MAX=2,
        RATE_LIMIT_VERIFY_RESEND_MAX=1,
        RATE_LIMIT_REFRESH_MAX=2,
    )
    app = create_test_app(settings=settings)
    c = new_client(app)

    for _ in range(3):
        c.post("/api/auth/login", json={"email": "arjun@beanbox.in", "password": "wrong"})
    assert (
        c.post(
            "/api/auth/login",
            json={"email": "arjun@beanbox.in", "password": "wrong"},
        ).status_code
        == 429
    )

    for i in range(2):
        assert (
            c.post(
                "/api/auth/forgot-password", json={"email": f"u{i}@example.in"}
            ).status_code
            == 200
        )
    assert (
        c.post(
            "/api/auth/forgot-password", json={"email": "u2@example.in"}
        ).status_code
        == 429
    )

    for i in range(2):
        assert (
            new_client(app)
            .post(
                "/api/auth/signup",
                json={
                    "name": f"User {i}",
                    "email": f"user{i}@example.in",
                    "password": "StrongCoffee@2026",
                },
            )
            .status_code
            == 201
        )
    assert (
        new_client(app)
        .post(
            "/api/auth/signup",
            json={
                "name": "User 2",
                "email": "user2@example.in",
                "password": "StrongCoffee@2026",
            },
        )
        .status_code
        == 429
    )

    # Refresh + verify-resend limiters on a logged-in browser client
    app2 = create_test_app(
        settings=make_test_settings(
            RATE_LIMIT_VERIFY_RESEND_MAX=1,
            RATE_LIMIT_REFRESH_MAX=2,
        )
    )
    c2 = new_client(app2)
    assert (
        c2.post(
            "/api/auth/signup",
            json={
                "name": "Limit Tester",
                "email": "limiter@example.in",
                "password": "StrongCoffee@2026",
            },
        ).status_code
        == 201
    )
    sync_csrf(c2)
    assert c2.post("/api/auth/refresh").status_code == 200
    sync_csrf(c2)
    assert c2.post("/api/auth/refresh").status_code == 200
    sync_csrf(c2)
    assert c2.post("/api/auth/refresh").status_code == 429

    # 1st resend uses the 1-request IP budget (hits per-user cooldown), 2nd hits IP rate limiter
    r_resend_1 = c2.post("/api/auth/verify-email/resend")
    assert r_resend_1.status_code == 429
    r_resend_2 = c2.post("/api/auth/verify-email/resend")
    assert r_resend_2.status_code == 429
    assert r_resend_2.json()["error"]["code"] == "AUTH_RATE_LIMIT_EXCEEDED"
