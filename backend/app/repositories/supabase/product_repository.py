from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.models.domain import Product, ProductCategory, ProductVariant, RoastLevel
from app.repositories.interfaces import (
    CreateProductInput,
    LowStockVariantEntry,
    ProductFacets,
    ProductListQuery,
    ProductListResult,
    ProductRepository,
    StockReservationFailure,
    StockReservationItem,
    StockReservationResult,
    UpdateProductInput,
)
from app.repositories.supabase.db import iso_str, map_pg_conflict


def _row_to_variant(row: dict[str, Any]) -> ProductVariant:
    return ProductVariant(
        id=row["id"],
        sku=row["sku"],
        size=row["size"],
        grind=row["grind"],
        label=row["label"],
        price_paise=int(row["price_paise"]),
        compare_at_paise=(
            int(row["compare_at_paise"])
            if row["compare_at_paise"] is not None
            else None
        ),
        stock=int(row["stock"]),
        is_active=bool(row.get("is_active", True)),
    )


def _row_to_product(
    row: dict[str, Any], variants: list[ProductVariant]
) -> Product:
    return Product(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        short_description=row["short_description"],
        description=row["description"],
        category=row["category"],
        roast_level=row["roast_level"],
        origin=row["origin"],
        tasting_notes=list(row["tasting_notes"] or []),
        images=list(row["images"] or []),
        variants=variants,
        is_featured=bool(row["is_featured"]),
        is_active=bool(row["is_active"]),
        rating_average=float(row["rating_average"]),
        rating_count=int(row["rating_count"]),
        created_at=iso_str(row["created_at"]) or "",
        updated_at=iso_str(row["updated_at"]) or "",
    )


class SupabaseProductRepository(ProductRepository):
    def __init__(self, pool: ConnectionPool[Any]) -> None:
        self._pool = pool

    def _fetch_variants_map(
        self, conn: Any, product_ids: list[str]
    ) -> dict[str, list[ProductVariant]]:
        if not product_ids:
            return {}
        rows = conn.execute(
            """
            SELECT * FROM product_variants
            WHERE product_id = ANY(%s)
              AND is_active = true
            ORDER BY price_paise ASC, id ASC;
            """,
            (product_ids,),
        ).fetchall()
        grouped: dict[str, list[ProductVariant]] = defaultdict(list)
        for r in rows:
            grouped[r["product_id"]].append(_row_to_variant(r))
        return grouped

    def list(self, query: ProductListQuery) -> ProductListResult:
        where_clauses: list[str] = []
        params: list[Any] = []

        if not query.include_inactive:
            where_clauses.append("p.is_active = true")
        if query.search:
            term = f"%{query.search.strip()}%"
            where_clauses.append(
                "(p.name ILIKE %s OR p.short_description ILIKE %s OR p.description ILIKE %s OR p.origin ILIKE %s OR array_to_string(p.tasting_notes, ' ') ILIKE %s)"
            )
            params.extend([term, term, term, term, term])
        if query.category:
            where_clauses.append("p.category = %s")
            params.append(query.category)
        if query.roast:
            where_clauses.append("p.roast_level = %s")
            params.append(query.roast)
        if query.origin:
            where_clauses.append("p.origin ILIKE %s")
            params.append(f"%{query.origin.strip()}%")
        if query.featured_only:
            where_clauses.append("p.is_featured = true")
        if query.in_stock_only:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = p.id AND pv.is_active = true AND pv.stock > 0)"
            )
        if query.min_price_paise is not None:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = p.id AND pv.is_active = true AND pv.price_paise >= %s)"
            )
            params.append(query.min_price_paise)
        if query.max_price_paise is not None:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM product_variants pv WHERE pv.product_id = p.id AND pv.is_active = true AND pv.price_paise <= %s)"
            )
            params.append(query.max_price_paise)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        if query.sort == "price_asc":
            order_sql = "ORDER BY COALESCE((SELECT MIN(pv.price_paise) FROM product_variants pv WHERE pv.product_id = p.id AND pv.is_active = true), 0) ASC"
        elif query.sort == "price_desc":
            order_sql = "ORDER BY COALESCE((SELECT MIN(pv.price_paise) FROM product_variants pv WHERE pv.product_id = p.id AND pv.is_active = true), 0) DESC"
        elif query.sort == "rating_desc":
            order_sql = "ORDER BY p.rating_average DESC, p.rating_count DESC"
        elif query.sort == "newest":
            order_sql = "ORDER BY p.created_at DESC"
        else:
            order_sql = "ORDER BY p.is_featured DESC, p.rating_count DESC, p.rating_average DESC"

        offset = (query.page - 1) * query.limit
        facet_filter = "" if query.include_inactive else "WHERE is_active = true"

        with self._pool.connection() as conn:
            count_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM products p {where_sql};",
                tuple(params),
            ).fetchone()
            total = int(count_row["cnt"]) if count_row else 0

            prod_rows = conn.execute(
                f"SELECT p.* FROM products p {where_sql} {order_sql} LIMIT %s OFFSET %s;",
                tuple([*params, query.limit, offset]),
            ).fetchall()

            variants_map = self._fetch_variants_map(
                conn, [r["id"] for r in prod_rows]
            )
            items = [
                _row_to_product(r, variants_map.get(r["id"], []))
                for r in prod_rows
            ]

            origins_rows = conn.execute(
                f"SELECT DISTINCT origin FROM products {facet_filter} ORDER BY origin;"
            ).fetchall()
            cats_rows = conn.execute(
                f"SELECT DISTINCT category FROM products {facet_filter};"
            ).fetchall()
            roasts_rows = conn.execute(
                f"SELECT DISTINCT roast_level FROM products {facet_filter};"
            ).fetchall()

            origins = [r["origin"] for r in origins_rows]
            categories: list[ProductCategory] = [r["category"] for r in cats_rows]
            roast_levels: list[RoastLevel] = [
                r["roast_level"] for r in roasts_rows if r["roast_level"] != "na"
            ]

            return ProductListResult(
                items=items,
                total=total,
                facets=ProductFacets(
                    origins=origins,
                    categories=categories,
                    roast_levels=roast_levels,
                ),
            )

    def find_by_id(self, product_id: str) -> Optional[Product]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE id = %s;", (product_id,)
            ).fetchone()
            if not row:
                return None
            variants = self._fetch_variants_map(conn, [row["id"]]).get(row["id"], [])
            return _row_to_product(row, variants)

    def find_by_slug(self, slug: str) -> Optional[Product]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE slug = %s;", (slug,)
            ).fetchone()
            if not row:
                return None
            variants = self._fetch_variants_map(conn, [row["id"]]).get(row["id"], [])
            return _row_to_product(row, variants)

    def find_variant_by_id(
        self, product_id: str, variant_id: str
    ) -> Optional[tuple[Product, ProductVariant]]:
        product = self.find_by_id(product_id)
        if not product:
            return None
        variant = next((v for v in product.variants if v.id == variant_id), None)
        if not variant:
            return None
        return product, variant

    def find_related(self, product: Product, limit: int) -> list[Product]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM products
                WHERE is_active = true AND id <> %s
                ORDER BY
                  ((CASE WHEN category = %s THEN 2 ELSE 0 END)
                   + (CASE WHEN origin = %s THEN 2 ELSE 0 END)
                   + (CASE WHEN roast_level = %s THEN 1 ELSE 0 END)) DESC,
                  rating_average DESC
                LIMIT %s;
                """,
                (
                    product.id,
                    product.category,
                    product.origin,
                    product.roast_level,
                    limit,
                ),
            ).fetchall()
            variants_map = self._fetch_variants_map(conn, [r["id"] for r in rows])
            return [
                _row_to_product(r, variants_map.get(r["id"], [])) for r in rows
            ]

    def create(self, data: CreateProductInput) -> Product:
        product_id = str(uuid4())
        with self._pool.connection() as conn:
            try:
                with conn.transaction():
                    row = conn.execute(
                        """
                        INSERT INTO products (
                          id, name, slug, short_description, description, category,
                          roast_level, origin, tasting_notes, images, is_featured, is_active
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *;
                        """,
                        (
                            product_id,
                            data.name,
                            data.slug,
                            data.short_description,
                            data.description,
                            data.category,
                            data.roast_level,
                            data.origin,
                            data.tasting_notes,
                            data.images,
                            data.is_featured,
                            data.is_active,
                        ),
                    ).fetchone()
                    variants: list[ProductVariant] = []
                    for v in data.variants:
                        v_id = v.id or str(uuid4())
                        v_row = conn.execute(
                            """
                            INSERT INTO product_variants (
                              id, product_id, sku, size, grind, label, price_paise, compare_at_paise, stock, is_active
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING *;
                            """,
                            (
                                v_id,
                                product_id,
                                v.sku,
                                v.size,
                                v.grind,
                                v.label,
                                v.price_paise,
                                v.compare_at_paise,
                                v.stock,
                                v.is_active,
                            ),
                        ).fetchone()
                        if v_row:
                            variants.append(_row_to_variant(v_row))
                    assert row is not None
                    return _row_to_product(row, variants)
            except Exception as exc:
                map_pg_conflict(
                    exc,
                    unique_message="A product with this slug or variant SKU already exists",
                    unique_code="DUPLICATE_PRODUCT_OR_SKU",
                )
                raise

    def update(self, product_id: str, data: UpdateProductInput) -> Optional[Product]:
        patch = data.model_dump(exclude_unset=True)
        variants_data = patch.pop("variants", None)

        with self._pool.connection() as conn:
            try:
                with conn.transaction():
                    existing = conn.execute(
                        "SELECT * FROM products WHERE id = %s;", (product_id,)
                    ).fetchone()
                    if not existing:
                        return None

                    if patch:
                        sets = [f"{k} = %s" for k in patch.keys()]
                        sets.append("updated_at = now()")
                        params = [*patch.values(), product_id]
                        row = conn.execute(
                            f"UPDATE products SET {', '.join(sets)} WHERE id = %s RETURNING *;",
                            tuple(params),
                        ).fetchone()
                    else:
                        row = conn.execute(
                            "UPDATE products SET updated_at = now() WHERE id = %s RETURNING *;",
                            (product_id,),
                        ).fetchone()

                    if variants_data is not None and data.variants is not None:
                        existing_rows = conn.execute(
                            "SELECT id FROM product_variants WHERE product_id = %s FOR UPDATE;",
                            (product_id,),
                        ).fetchall()
                        existing_ids = {r["id"] for r in existing_rows}
                        referenced_ids: set[str] = set()
                        if existing_ids:
                            ref_rows = conn.execute(
                                "SELECT DISTINCT variant_id FROM order_items WHERE variant_id = ANY(%s);",
                                (list(existing_ids),),
                            ).fetchall()
                            referenced_ids = {r["variant_id"] for r in ref_rows}

                        kept_ids: set[str] = set()
                        for v in data.variants:
                            if v.id and v.id in existing_ids:
                                conn.execute(
                                    """
                                    UPDATE product_variants
                                    SET sku = %s, size = %s, grind = %s, label = %s,
                                        price_paise = %s, compare_at_paise = %s,
                                        stock = %s, is_active = %s
                                    WHERE id = %s AND product_id = %s;
                                    """,
                                    (
                                        v.sku,
                                        v.size,
                                        v.grind,
                                        v.label,
                                        v.price_paise,
                                        v.compare_at_paise,
                                        v.stock,
                                        v.is_active,
                                        v.id,
                                        product_id,
                                    ),
                                )
                                kept_ids.add(v.id)
                            else:
                                new_vid = v.id or str(uuid4())
                                conn.execute(
                                    """
                                    INSERT INTO product_variants (
                                      id, product_id, sku, size, grind, label, price_paise, compare_at_paise, stock, is_active
                                    )
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                                    """,
                                    (
                                        new_vid,
                                        product_id,
                                        v.sku,
                                        v.size,
                                        v.grind,
                                        v.label,
                                        v.price_paise,
                                        v.compare_at_paise,
                                        v.stock,
                                        v.is_active,
                                    ),
                                )
                                kept_ids.add(new_vid)

                        for removed_id in existing_ids - kept_ids:
                            if removed_id in referenced_ids:
                                conn.execute(
                                    """
                                    UPDATE product_variants
                                    SET is_active = false, stock = 0
                                    WHERE id = %s AND product_id = %s;
                                    """,
                                    (removed_id, product_id),
                                )
                            else:
                                conn.execute(
                                    "DELETE FROM product_variants WHERE id = %s AND product_id = %s;",
                                    (removed_id, product_id),
                                )

                    variants = self._fetch_variants_map(conn, [product_id]).get(
                        product_id, []
                    )
                    assert row is not None
                    return _row_to_product(row, variants)
            except Exception as exc:
                map_pg_conflict(
                    exc,
                    unique_message="A product with this slug or variant SKU already exists",
                    unique_code="DUPLICATE_PRODUCT_OR_SKU",
                    fk_message="Cannot delete product variant referenced by existing orders",
                )
                raise

    def delete(self, product_id: str) -> bool:
        with self._pool.connection() as conn:
            try:
                res = conn.execute("DELETE FROM products WHERE id = %s;", (product_id,))
                return res.rowcount > 0
            except Exception as exc:
                map_pg_conflict(
                    exc,
                    fk_message="Cannot delete product referenced by existing orders; set isActive=false instead",
                    fk_code="PRODUCT_IN_USE",
                )
                raise

    def update_variant_inventory(
        self,
        product_id: str,
        variant_id: str,
        stock: Optional[int] = None,
        price_paise: Optional[int] = None,
    ) -> Optional[ProductVariant]:
        sets: list[str] = []
        params: list[Any] = []
        if stock is not None:
            sets.append("stock = %s")
            params.append(stock)
        if price_paise is not None:
            sets.append("price_paise = %s")
            params.append(price_paise)
        if not sets:
            found = self.find_variant_by_id(product_id, variant_id)
            return found[1] if found else None

        params.extend([variant_id, product_id])
        with self._pool.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    f"UPDATE product_variants SET {', '.join(sets)} WHERE id = %s AND product_id = %s RETURNING *;",
                    tuple(params),
                ).fetchone()
                if not row:
                    return None
                conn.execute(
                    "UPDATE products SET updated_at = now() WHERE id = %s;",
                    (product_id,),
                )
                return _row_to_variant(row)

    def reserve_stock(
        self, items: list[StockReservationItem]
    ) -> StockReservationResult:
        if not items:
            return StockReservationResult(ok=True, failures=[])

        aggregated: dict[tuple[str, str], int] = {}
        for item in items:
            key = (item.product_id, item.variant_id)
            aggregated[key] = aggregated.get(key, 0) + item.quantity

        # Consistent sorted order avoids deadlocks under concurrent orders
        ordered_keys = sorted(aggregated.keys(), key=lambda k: k[1])
        variant_ids = [k[1] for k in ordered_keys]

        with self._pool.connection() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT pv.id, pv.product_id, pv.label, pv.stock, pv.is_active AS variant_active,
                           p.name AS product_name, p.is_active
                    FROM product_variants pv
                    JOIN products p ON p.id = pv.product_id
                    WHERE pv.id = ANY(%s)
                    ORDER BY pv.id
                    FOR UPDATE OF pv;
                    """,
                    (variant_ids,),
                ).fetchall()

                row_by_vid = {r["id"]: r for r in rows}
                failures: list[StockReservationFailure] = []

                for product_id, variant_id in ordered_keys:
                    qty = aggregated[(product_id, variant_id)]
                    r = row_by_vid.get(variant_id)
                    if (
                        not r
                        or r["product_id"] != product_id
                        or not r["is_active"]
                        or not r.get("variant_active", True)
                    ):
                        failures.append(
                            StockReservationFailure(
                                product_id=product_id,
                                variant_id=variant_id,
                                product_name=r["product_name"] if r else "Unknown product",
                                variant_label=r["label"] if r else "Unknown variant",
                                requested=qty,
                                available=0,
                            )
                        )
                    elif int(r["stock"]) < qty:
                        failures.append(
                            StockReservationFailure(
                                product_id=product_id,
                                variant_id=variant_id,
                                product_name=r["product_name"],
                                variant_label=r["label"],
                                requested=qty,
                                available=int(r["stock"]),
                            )
                        )

                if failures:
                    return StockReservationResult(ok=False, failures=failures)

                touched_products: set[str] = set()
                for product_id, variant_id in ordered_keys:
                    qty = aggregated[(product_id, variant_id)]
                    conn.execute(
                        "UPDATE product_variants SET stock = stock - %s WHERE id = %s;",
                        (qty, variant_id),
                    )
                    touched_products.add(product_id)

                conn.execute(
                    "UPDATE products SET updated_at = now() WHERE id = ANY(%s);",
                    (list(touched_products),),
                )
                return StockReservationResult(ok=True, failures=[])

    def release_stock(self, items: list[StockReservationItem]) -> None:
        if not items:
            return
        ordered = sorted(items, key=lambda i: i.variant_id)
        with self._pool.connection() as conn:
            with conn.transaction():
                for item in ordered:
                    conn.execute(
                        "UPDATE product_variants SET stock = stock + %s WHERE id = %s AND product_id = %s;",
                        (item.quantity, item.variant_id, item.product_id),
                    )
                conn.execute(
                    "UPDATE products SET updated_at = now() WHERE id = ANY(%s);",
                    (list({i.product_id for i in ordered}),),
                )

    def list_low_stock(self, threshold: int) -> list[LowStockVariantEntry]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT pv.*, p.name AS product_name, p.slug AS product_slug, p.category
                FROM product_variants pv
                JOIN products p ON p.id = pv.product_id
                WHERE p.is_active = true AND pv.is_active = true AND pv.stock <= %s
                ORDER BY pv.stock ASC;
                """,
                (threshold,),
            ).fetchall()
            return [
                LowStockVariantEntry(
                    product_id=r["product_id"],
                    product_name=r["product_name"],
                    product_slug=r["product_slug"],
                    category=r["category"],
                    variant=_row_to_variant(r),
                )
                for r in rows
            ]

    def update_rating_stats(
        self, product_id: str, rating_average: float, rating_count: int
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                UPDATE products
                SET rating_average = %s, rating_count = %s, updated_at = now()
                WHERE id = %s;
                """,
                (rating_average, rating_count, product_id),
            )
