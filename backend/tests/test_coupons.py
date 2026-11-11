from datetime import datetime, timedelta, timezone

from tests.conftest import create_test_app, login_client, new_client


def test_coupon_discount_gst_and_shipping_calculations():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    # 2 × ₹499 = ₹998 (99,800 paise)
    arjun.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 2,
        },
    )

    preview = arjun.post(
        "/api/checkout/preview",
        json={"addressId": "addr-arjun-home", "couponCode": "WELCOME10"},
    )
    assert preview.status_code == 200
    p = preview.json()["data"]["preview"]["pricing"]
    assert p["itemsSubtotalPaise"] == 99800
    assert p["discountPaise"] == 9980
    assert p["taxableAmountPaise"] == 89820
    assert p["gstPaise"] == 4491
    assert p["shippingPaise"] == 7900
    assert p["totalPaise"] == 89820 + 4491 + 7900

    # FLAT150 min order ₹999 fails at ₹998
    fail_min = arjun.post(
        "/api/checkout/preview", json={"couponCode": "FLAT150"}
    )
    assert fail_min.status_code == 400
    assert fail_min.json()["error"]["code"] == "COUPON_MIN_ORDER_NOT_MET"

    # Expired coupon rejected
    fail_exp = arjun.post(
        "/api/checkout/preview", json={"couponCode": "EXPIRED50"}
    )
    assert fail_exp.status_code == 400
    assert fail_exp.json()["error"]["code"] == "COUPON_EXPIRED"


def test_coupon_usage_limit_and_rollback_on_cancel():
    app = create_test_app()
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")

    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    create_res = admin.post(
        "/api/admin/coupons",
        json={
            "code": "ONEUSE100",
            "description": "Single use ₹100 off",
            "type": "flat",
            "value": 10000,
            "minOrderPaise": 30000,
            "expiresAt": future,
            "usageLimit": 1,
            "isActive": True,
        },
    )
    assert create_res.status_code == 201

    arjun.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 1,
        },
    )
    ord1 = arjun.post(
        "/api/orders",
        json={"addressId": "addr-arjun-home", "couponCode": "ONEUSE100"},
    )
    assert ord1.status_code == 201

    user2 = new_client(app)
    user2.post(
        "/api/auth/signup",
        json={
            "name": "Neha Rao",
            "email": "neha@example.in",
            "password": "Password@123",
        },
    )
    addr2_id = user2.post(
        "/api/addresses",
        json={
            "label": "Work",
            "fullName": "Neha Rao",
            "phone": "9900112233",
            "line1": "MG Road",
            "city": "Pune",
            "state": "Maharashtra",
            "postalCode": "411001",
        },
    ).json()["data"]["address"]["id"]

    user2.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 1,
        },
    )
    ord2_fail = user2.post(
        "/api/orders",
        json={"addressId": addr2_id, "couponCode": "ONEUSE100"},
    )
    assert ord2_fail.status_code == 400
    assert ord2_fail.json()["error"]["code"] == "COUPON_LIMIT_REACHED"

    # Arjun cancels -> coupon slot restored -> User 2 succeeds
    arjun.post(f"/api/orders/{ord1.json()['data']['order']['id']}/cancel", json={})
    ord2_ok = user2.post(
        "/api/orders",
        json={"addressId": addr2_id, "couponCode": "ONEUSE100"},
    )
    assert ord2_ok.status_code == 201
