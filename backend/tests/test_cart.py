from tests.conftest import create_test_app, new_client


def test_guest_cart_server_pricing_and_stock_enforcement():
    app = create_test_app()
    guest = new_client(app)

    # Attempt client price tampering — backend must ignore and compute from ProductRepository
    add_res = guest.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 2,
            "unitPricePaise": 1,
            "price": 0,
        },
    )
    assert add_res.status_code == 201
    cart = add_res.json()["data"]["cart"]
    assert cart["itemCount"] == 2
    assert cart["items"][0]["unitPricePaise"] == 49900
    assert cart["itemsSubtotalPaise"] == 99800
    assert cart["estimatedShippingPaise"] == 7900

    # Update to 3 units -> ₹1,497 -> Free shipping
    patch_res = guest.patch(
        "/api/cart/items/chik-250-wb", json={"quantity": 3}
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()["data"]["cart"]
    assert updated["itemsSubtotalPaise"] == 149700
    assert updated["estimatedShippingPaise"] == 0
    assert updated["estimatedGstPaise"] == round(149700 * 0.05)

    # Stock overflow rejected (Valencia cold brew has 2 units in stock)
    exceed = guest.post(
        "/api/cart/items",
        json={
            "productId": "prod-citrus-cold-brew",
            "variantId": "cborg-250",
            "quantity": 5,
        },
    )
    assert exceed.status_code == 409
    assert exceed.json()["error"]["code"] == "INSUFFICIENT_STOCK"


def test_guest_cart_merges_into_user_cart_on_login():
    app = create_test_app()
    client = new_client(app)

    add_res = client.post(
        "/api/cart/items",
        json={
            "productId": "prod-chikmagalur-arabica",
            "variantId": "chik-250-wb",
            "quantity": 2,
        },
    )
    assert add_res.status_code == 201

    login_res = client.post(
        "/api/auth/login",
        json={"email": "arjun@beanbox.in", "password": "Coffee@1234"},
    )
    assert login_res.status_code == 200

    cart_res = client.get("/api/cart")
    assert cart_res.status_code == 200
    assert cart_res.json()["data"]["cart"]["itemCount"] == 2
    assert cart_res.json()["data"]["cart"]["items"][0]["variantId"] == "chik-250-wb"
