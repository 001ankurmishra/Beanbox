from tests.conftest import build_signed_webhook, create_test_app, login_client, new_client


def test_webhook_signature_idempotency_and_paid_transition():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    arjun.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 1,
        },
    )
    order = arjun.post("/api/orders", json={"addressId": "addr-arjun-home"}).json()[
        "data"
    ]["order"]

    sess_res = arjun.post(
        "/api/payments/checkout-session", json={"orderId": order["id"]}
    )
    assert sess_res.status_code == 201
    session = sess_res.json()["data"]["session"]
    assert session["provider"] == "mock"
    assert "/checkout/mock-pay" in session["checkoutUrl"]

    raw_body, sig = build_signed_webhook(
        app.state.settings.mock_webhook_secret,
        {
            "id": "evt_test_paid_1",
            "type": "checkout.session.completed",
            "data": {
                "orderId": order["id"],
                "sessionId": session["sessionId"],
                "paymentIntentId": "mock_pi_999",
                "amountPaise": order["pricing"]["totalPaise"],
                "currency": "INR",
            },
        },
    )

    anon = new_client(app)
    bad_sig = anon.post(
        "/api/payments/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "x-mock-signature": "v1=deadbeef",
        },
    )
    assert bad_sig.status_code == 400
    assert bad_sig.json()["error"]["code"] == "INVALID_SIGNATURE"

    first = anon.post(
        "/api/payments/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "x-mock-signature": sig},
    )
    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert first.json()["status"] == "paid"

    second = anon.post(
        "/api/payments/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "x-mock-signature": sig},
    )
    assert second.status_code == 200
    assert second.json()["duplicate"] is True

    order_check = arjun.get(f"/api/orders/{order['id']}").json()["data"]["order"]
    assert order_check["status"] == "paid"
    assert order_check["paymentStatus"] == "paid"

    confirm_emails = [
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "order_confirmation"
    ]
    assert len(confirm_emails) == 1


def test_webhook_expired_or_failed_releases_reserved_stock():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    _, before = app.state.repos.products.find_variant_by_id(
        "prod-citrus-cold-brew", "cborg-250"
    )
    assert before.stock == 2

    arjun.post(
        "/api/cart/items",
        json={
            "productId": "prod-citrus-cold-brew",
            "variantId": "cborg-250",
            "quantity": 2,
        },
    )
    order = arjun.post("/api/orders", json={"addressId": "addr-arjun-home"}).json()[
        "data"
    ]["order"]

    _, during = app.state.repos.products.find_variant_by_id(
        "prod-citrus-cold-brew", "cborg-250"
    )
    assert during.stock == 0

    raw_body, sig = build_signed_webhook(
        app.state.settings.mock_webhook_secret,
        {
            "id": "evt_test_expired_1",
            "type": "checkout.session.expired",
            "data": {"orderId": order["id"]},
        },
    )
    hook = new_client(app).post(
        "/api/payments/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "x-mock-signature": sig},
    )
    assert hook.status_code == 200
    assert hook.json()["status"] == "cancelled"

    _, after = app.state.repos.products.find_variant_by_id(
        "prod-citrus-cold-brew", "cborg-250"
    )
    assert after.stock == 2

    order_after = arjun.get(f"/api/orders/{order['id']}").json()["data"]["order"]
    assert order_after["status"] == "cancelled"
    assert order_after["paymentStatus"] == "expired"
