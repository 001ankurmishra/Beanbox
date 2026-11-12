from __future__ import annotations

import json
from pathlib import Path

import psycopg

from app.seed.seed_data import create_seed_data


def seed_supabase_database(database_url: str, apply_schema: bool = False) -> dict[str, int]:
    """Idempotently applies schema (if requested) and seeds initial BeanBox data into Supabase."""
    dataset = create_seed_data()
    schema_path = Path(__file__).resolve().parents[2] / "supabase" / "schema.sql"

    with psycopg.connect(database_url) as conn:
        if apply_schema and schema_path.exists():
            conn.execute(schema_path.read_text(encoding="utf-8"))
            conn.commit()

        with conn.transaction():
            for u in dataset.users:
                conn.execute(
                    """
                    INSERT INTO users (
                        id, name, email, phone, password_hash, role,
                        email_verified, email_verified_at, totp_enabled, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email) DO NOTHING;
                    """,
                    (
                        u.id,
                        u.name,
                        u.email,
                        u.phone,
                        u.password_hash,
                        u.role,
                        u.email_verified,
                        u.email_verified_at,
                        u.totp_enabled,
                        u.created_at,
                        u.updated_at,
                    ),
                )

            for p in dataset.products:
                conn.execute(
                    """
                    INSERT INTO products (
                      id, name, slug, short_description, description, category,
                      roast_level, origin, tasting_notes, images, is_featured,
                      is_active, rating_average, rating_count, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (slug) DO NOTHING;
                    """,
                    (
                        p.id,
                        p.name,
                        p.slug,
                        p.short_description,
                        p.description,
                        p.category,
                        p.roast_level,
                        p.origin,
                        p.tasting_notes,
                        p.images,
                        p.is_featured,
                        p.is_active,
                        p.rating_average,
                        p.rating_count,
                        p.created_at,
                        p.updated_at,
                    ),
                )
                for v in p.variants:
                    conn.execute(
                        """
                        INSERT INTO product_variants (
                          id, product_id, sku, size, grind, label, price_paise, compare_at_paise, stock
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sku) DO NOTHING;
                        """,
                        (
                            v.id,
                            p.id,
                            v.sku,
                            v.size,
                            v.grind,
                            v.label,
                            v.price_paise,
                            v.compare_at_paise,
                            v.stock,
                        ),
                    )

            for c in dataset.coupons:
                conn.execute(
                    """
                    INSERT INTO coupons (
                      id, code, description, type, value, min_order_paise,
                      max_discount_paise, expires_at, usage_limit, used_count,
                      is_active, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (code) DO NOTHING;
                    """,
                    (
                        c.id,
                        c.code,
                        c.description,
                        c.type,
                        c.value,
                        c.min_order_paise,
                        c.max_discount_paise,
                        c.expires_at,
                        c.usage_limit,
                        c.used_count,
                        c.is_active,
                        c.created_at,
                        c.updated_at,
                    ),
                )

            for a in dataset.addresses:
                conn.execute(
                    """
                    INSERT INTO addresses (
                      id, user_id, label, full_name, phone, line1, line2,
                      city, state, postal_code, country, is_default, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    (
                        a.id,
                        a.user_id,
                        a.label,
                        a.full_name,
                        a.phone,
                        a.line1,
                        a.line2,
                        a.city,
                        a.state,
                        a.postal_code,
                        a.country,
                        a.is_default,
                        a.created_at,
                        a.updated_at,
                    ),
                )

            for o in dataset.orders:
                conn.execute(
                    """
                    INSERT INTO orders (
                      id, order_number, user_id, shipping_address, coupon_code, coupon_id,
                      pricing, status, payment_status, payment_provider, payment_session_id,
                      payment_intent_id, stock_released, cancel_reason, created_at, updated_at,
                      paid_at, shipped_at, delivered_at, cancelled_at
                    )
                    VALUES (
                      %s, %s, %s, %s::jsonb, %s, %s,
                      %s::jsonb, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s
                    )
                    ON CONFLICT (order_number) DO NOTHING;
                    """,
                    (
                        o.id,
                        o.order_number,
                        o.user_id,
                        json.dumps(o.shipping_address.model_dump(mode="json")),
                        o.coupon_code,
                        o.coupon_id,
                        json.dumps(o.pricing.model_dump(mode="json")),
                        o.status,
                        o.payment_status,
                        o.payment_provider,
                        o.payment_session_id,
                        o.payment_intent_id,
                        o.stock_released,
                        o.cancel_reason,
                        o.created_at,
                        o.updated_at,
                        o.paid_at,
                        o.shipped_at,
                        o.delivered_at,
                        o.cancelled_at,
                    ),
                )
                exists_item = conn.execute(
                    "SELECT 1 FROM order_items WHERE order_id = %s LIMIT 1;",
                    (o.id,),
                ).fetchone()
                if not exists_item:
                    for item in o.items:
                        conn.execute(
                            """
                            INSERT INTO order_items (
                              order_id, product_id, variant_id, sku, product_name,
                              product_slug, variant_label, image, unit_price_paise,
                              quantity, line_total_paise
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (
                                o.id,
                                item.product_id,
                                item.variant_id,
                                item.sku,
                                item.product_name,
                                item.product_slug,
                                item.variant_label,
                                item.image,
                                item.unit_price_paise,
                                item.quantity,
                                item.line_total_paise,
                            ),
                        )

            for r in dataset.reviews:
                conn.execute(
                    """
                    INSERT INTO reviews (
                      id, product_id, user_id, user_name, rating, title, comment,
                      verified_purchase, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, product_id) DO NOTHING;
                    """,
                    (
                        r.id,
                        r.product_id,
                        r.user_id,
                        r.user_name,
                        r.rating,
                        r.title,
                        r.comment,
                        r.verified_purchase,
                        r.created_at,
                        r.updated_at,
                    ),
                )

            for w in dataset.wishlist:
                conn.execute(
                    """
                    INSERT INTO wishlist_items (id, user_id, product_id, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id, product_id) DO NOTHING;
                    """,
                    (w.id, w.user_id, w.product_id, w.created_at),
                )

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products;")
            prod_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users;")
            user_cnt = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM coupons;")
            coupon_cnt = cur.fetchone()[0]

    return {
        "products": int(prod_cnt),
        "users": int(user_cnt),
        "coupons": int(coupon_cnt),
    }
