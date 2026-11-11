import re

from tests.conftest import create_test_app, login_client, new_client


def test_signup_cookie_welcome_email_and_duplicate_conflict():
    app = create_test_app()
    client = new_client(app)

    res = client.post(
        "/api/auth/signup",
        json={
            "name": "Priya Menon",
            "email": "priya@example.in",
            "password": "Password@123",
            "phone": "9876543210",
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "priya@example.in"
    assert body["data"]["user"]["role"] == "customer"
    assert "passwordHash" not in body["data"]["user"]
    assert "beanbox_token" in res.cookies

    set_cookie_header = res.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header or "httponly" in set_cookie_header.lower()

    emails = [
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "welcome" and e.to == "priya@example.in"
    ]
    assert len(emails) == 1

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["data"]["user"]["email"] == "priya@example.in"

    dup_res = new_client(app).post(
        "/api/auth/signup",
        json={
            "name": "Priya Again",
            "email": "priya@example.in",
            "password": "Password@123",
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


def test_login_logout_and_admin_rbac():
    app = create_test_app()
    guest = new_client(app)

    bad = guest.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "WrongPassword"},
    )
    assert bad.status_code == 401

    customer = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    denied = customer.get("/api/admin/stats")
    assert denied.status_code == 403

    logout = customer.post("/api/auth/logout")
    assert logout.status_code == 200
    assert customer.get("/api/auth/me").status_code == 401

    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    stats = admin.get("/api/admin/stats")
    assert stats.status_code == 200
    assert stats.json()["data"]["stats"]["totalOrders"] >= 1


def test_forgot_and_single_use_reset_password():
    app = create_test_app()
    client = new_client(app)

    forgot = client.post(
        "/api/auth/forgot-password", json={"email": "arjun@beanbox.in"}
    )
    assert forgot.status_code == 200

    reset_email = next(
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "password_reset" and e.to == "arjun@beanbox.in"
    )
    match = re.search(r"Token: ([a-f0-9]+)", reset_email.body)
    assert match is not None
    token = match.group(1)

    reset_res = client.post(
        "/api/auth/reset-password",
        json={"token": token, "newPassword": "NewCoffeePassword@99"},
    )
    assert reset_res.status_code == 200

    login_client(app, "arjun@beanbox.in", "NewCoffeePassword@99")

    reuse_res = client.post(
        "/api/auth/reset-password",
        json={"token": token, "newPassword": "AnotherPassword@99"},
    )
    assert reuse_res.status_code == 400
