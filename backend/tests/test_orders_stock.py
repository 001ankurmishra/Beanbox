from tests.conftest import create_test_app, login_client, new_client


def test_atomic_stock_reservation_oversell_prevention_and_cancel_release():
    app = create_test_app()
    user_a = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    user_b = new_client(app)
    user_b.post(
        "/api/auth/signup",
        json={
            "name": "Rohan Das",
            "email": "rohan@example.in",
            "password": "Password@123",
        },
    )
    addr_b = user_b.post(
        "/api/addresses",
        json={
            "label": "Home",
            "fullName": "Rohan Das",
            "phone": "9811122233",
            "line1": "12 Park Street",
            "city": "Kolkata",
            "state": "West Bengal",
            "postalCode": "700016",
        },
    ).json()["data"]["address"]["id"]

    # Valencia cold brew has 2 units in stock
    user_a.post(
        "/api/cart/items",
        json={
            "productId": "prod-citrus-cold-brew",
            "variantId": "cborg-250",
            "quantity": 2,
        },
    )
    user_b.post(
        "/api/cart/items",
        json={
            "productId": "prod-citrus-cold-brew",
            "variantId": "cborg-250",
            "quantity": 1,
        },
    )
    user_b.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 1,
        },
    )

    ord_a_res = user_a.post("/api/orders", json={"addressId": "addr-arjun-home"})
    assert ord_a_res.status_code == 201
    order_a = ord_a_res.json()["data"]["order"]
    assert order_a["status"] == "pending"
    assert order_a["pricing"]["itemsSubtotalPaise"] == 93800
    assert order_a["pricing"]["shippingPaise"] == 7900

    # User A cart cleared
    assert user_a.get("/api/cart").json()["data"]["cart"]["itemCount"] == 0

    # Stock is 0
    repos = app.state.repos
    _, citrus_after_a = repos.products.find_variant_by_id(
        "prod-citrus-cold-brew", "cborg-250"
    )
    assert citrus_after_a.stock == 0

    _, chik_before_b = repos.products.find_variant_by_id(
        "prod-chikmagalur-arabica", "chik-250-wb"
    )

    # User B oversell fails cleanly with zero partial decrement on Chikmagalur
    ord_b_res = user_b.post("/api/orders", json={"addressId": addr_b})
    assert ord_b_res.status_code == 409
    assert ord_b_res.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    _, chik_after_b = repos.products.find_variant_by_id(
        "prod-chikmagalur-arabica", "chik-250-wb"
    )
    assert chik_after_b.stock == chik_before_b.stock

    # Invoice endpoint returns GST invoice
    inv = user_a.get(f"/api/orders/{order_a['id']}/invoice")
    assert inv.status_code == 200
    assert inv.json()["data"]["invoice"]["seller"]["hsnSacCode"] == "0901"

    # Cancel before shipping restores stock to 2
    cancel_res = user_a.post(
        f"/api/orders/{order_a['id']}/cancel",
        json={"reason": "Changed grind choice"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["order"]["status"] == "cancelled"

    _, citrus_restored = repos.products.find_variant_by_id(
        "prod-citrus-cold-brew", "cborg-250"
    )
    assert citrus_restored.stock == 2


def test_cannot_cancel_after_shipped_and_verified_buyer_review_rules():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")

    arjun.post(
        "/api/cart/items",
        json={
            "productId": "prod-monsoon-malabar",
            "variantId": "mmal-250-wb",
            "quantity": 1,
        },
    )
    order_id = arjun.post(
        "/api/orders", json={"addressId": "addr-arjun-home"}
    ).json()["data"]["order"]["id"]

    assert (
        admin.patch(
            f"/api/admin/orders/{order_id}/status", json={"status": "paid"}
        ).status_code
        == 200
    )
    assert (
        admin.patch(
            f"/api/admin/orders/{order_id}/status", json={"status": "processing"}
        ).status_code
        == 200
    )
    assert (
        admin.patch(
            f"/api/admin/orders/{order_id}/status", json={"status": "shipped"}
        ).status_code
        == 200
    )

    shipped_emails = [
        e
        for e in app.state.services.email_service.get_sent_emails()
        if e.type == "order_shipped"
    ]
    assert len(shipped_emails) == 1

    # Customer cancel blocked once shipped
    cancel_after_ship = arjun.post(f"/api/orders/{order_id}/cancel", json={})
    assert cancel_after_ship.status_code == 409

    # Verified buyer review succeeds once
    rev1 = arjun.post(
        "/api/products/coorg-monsooned-malabar-aa/reviews",
        json={
            "rating": 4,
            "title": "Rich crema and smooth spice",
            "comment": "Really enjoyed the low acidity and dark cocoa notes.",
        },
    )
    assert rev1.status_code == 201

    # Duplicate review blocked
    rev_dup = arjun.post(
        "/api/products/coorg-monsooned-malabar-aa/reviews",
        json={
            "rating": 5,
            "title": "Second attempt",
            "comment": "Should be rejected as duplicate.",
        },
    )
    assert rev_dup.status_code == 409

    # Unpurchased product review blocked
    rev_unbought = arjun.post(
        "/api/products/araku-valley-tribal-organic/reviews",
        json={
            "rating": 5,
            "title": "Unverified buyer",
            "comment": "Should be rejected because not purchased.",
        },
    )
    assert rev_unbought.status_code == 403
