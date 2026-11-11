from tests.conftest import create_test_app, login_client, new_client


def test_products_filter_sort_pagination_detail_and_related():
    app = create_test_app()
    guest = new_client(app)

    res = guest.get(
        "/api/products?category=beans&roast=medium&sort=price_asc&page=1&limit=5"
    )
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    assert len(items) > 0
    assert all(p["category"] == "beans" for p in items)

    detail = guest.get("/api/products/chikmagalur-baba-budangiri-arabica")
    assert detail.status_code == 200
    assert len(detail.json()["data"]["product"]["variants"]) == 4

    related = guest.get(
        "/api/products/chikmagalur-baba-budangiri-arabica/related?limit=3"
    )
    assert related.status_code == 200
    assert len(related.json()["data"]["items"]) == 3


def test_wishlist_addresses_and_admin_catalog_apis():
    app = create_test_app()
    arjun = login_client(app, "arjun@beanbox.in", "Coffee@1234")
    admin = login_client(app, "admin@beanbox.in", "Admin@1234")

    wish_add = arjun.post("/api/wishlist/prod-araku-organic")
    assert wish_add.status_code == 201
    assert any(
        p["id"] == "prod-araku-organic" for p in wish_add.json()["data"]["items"]
    )

    wish_del = arjun.delete("/api/wishlist/prod-araku-organic")
    assert wish_del.status_code == 200
    assert all(
        p["id"] != "prod-araku-organic" for p in wish_del.json()["data"]["items"]
    )

    new_addr = arjun.post(
        "/api/addresses",
        json={
            "label": "Work",
            "fullName": "Arjun Sharma",
            "phone": "9820456789",
            "line1": "WeWork Galaxy, Residency Road",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postalCode": "560025",
            "isDefault": False,
        },
    )
    assert new_addr.status_code == 201
    addr_id = new_addr.json()["data"]["address"]["id"]

    set_def = arjun.patch(f"/api/addresses/{addr_id}/default")
    assert set_def.status_code == 200
    assert set_def.json()["data"]["address"]["isDefault"] is True

    create_prod = admin.post(
        "/api/admin/products",
        json={
            "name": "Sakleshpur Reserve Estate",
            "slug": "sakleshpur-reserve-estate",
            "shortDescription": "Small lot washed arabica from Sakleshpur hills.",
            "description": "Nutty milk chocolate and toasted spice roasted weekly.",
            "category": "beans",
            "roastLevel": "medium",
            "origin": "Sakleshpur, Karnataka",
            "tastingNotes": ["Caramel", "Almond"],
            "images": ["/images/products/beans-medium.svg"],
            "variants": [
                {
                    "sku": "SAKL-250-WB",
                    "size": "250g",
                    "grind": "whole_bean",
                    "label": "250g · Whole Bean",
                    "pricePaise": 52900,
                    "stock": 15,
                }
            ],
            "isFeatured": False,
            "isActive": True,
        },
    )
    assert create_prod.status_code == 201
    prod = create_prod.json()["data"]["product"]
    var_id = prod["variants"][0]["id"]

    inv = admin.patch(
        f"/api/admin/inventory/{prod['id']}/{var_id}",
        json={"stock": 3, "pricePaise": 54900},
    )
    assert inv.status_code == 200
    assert inv.json()["data"]["variant"]["stock"] == 3

    users = admin.get("/api/admin/users")
    assert users.status_code == 200
    assert len(users.json()["data"]["items"]) >= 2
