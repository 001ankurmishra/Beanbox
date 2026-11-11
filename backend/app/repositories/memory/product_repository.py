from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from typing import Optional
from uuid import uuid4

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _min_variant_price(product: Product) -> int:
    if not product.variants:
        return 0
    return min(v.price_paise for v in product.variants)


class InMemoryProductRepository(ProductRepository):
    def __init__(self, initial_products: Optional[list[Product]] = None) -> None:
        self._lock = RLock()
        self._products: list[Product] = [
            p.model_copy(deep=True) for p in (initial_products or [])
        ]

    def list(self, query: ProductListQuery) -> ProductListResult:
        with self._lock:
            base = (
                list(self._products)
                if query.include_inactive
                else [p for p in self._products if p.is_active]
            )

            origins = sorted({p.origin for p in base})
            categories: list[ProductCategory] = list(dict.fromkeys(p.category for p in base))
            roast_levels: list[RoastLevel] = list(
                dict.fromkeys(p.roast_level for p in base if p.roast_level != "na")
            )

            filtered = list(base)
            if query.search:
                term = query.search.strip().lower()
                filtered = [
                    p
                    for p in filtered
                    if term in p.name.lower()
                    or term in p.short_description.lower()
                    or term in p.description.lower()
                    or term in p.origin.lower()
                    or any(term in note.lower() for note in p.tasting_notes)
                ]

            if query.category:
                filtered = [p for p in filtered if p.category == query.category]

            if query.roast:
                filtered = [p for p in filtered if p.roast_level == query.roast]

            if query.origin:
                orig_term = query.origin.strip().lower()
                filtered = [p for p in filtered if orig_term in p.origin.lower()]

            if query.featured_only:
                filtered = [p for p in filtered if p.is_featured]

            if query.in_stock_only:
                filtered = [p for p in filtered if any(v.stock > 0 for v in p.variants)]

            if query.min_price_paise is not None:
                filtered = [
                    p
                    for p in filtered
                    if any(v.price_paise >= query.min_price_paise for v in p.variants)
                ]

            if query.max_price_paise is not None:
                filtered = [
                    p
                    for p in filtered
                    if any(v.price_paise <= query.max_price_paise for v in p.variants)
                ]

            if query.sort == "price_asc":
                filtered.sort(key=_min_variant_price)
            elif query.sort == "price_desc":
                filtered.sort(key=_min_variant_price, reverse=True)
            elif query.sort == "rating_desc":
                filtered.sort(
                    key=lambda p: (p.rating_average, p.rating_count), reverse=True
                )
            elif query.sort == "newest":
                filtered.sort(key=lambda p: p.created_at, reverse=True)
            else:
                filtered.sort(
                    key=lambda p: (int(p.is_featured), p.rating_count, p.rating_average),
                    reverse=True,
                )

            total = len(filtered)
            start = (query.page - 1) * query.limit
            items = [p.model_copy(deep=True) for p in filtered[start : start + query.limit]]

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
        with self._lock:
            for p in self._products:
                if p.id == product_id:
                    return p.model_copy(deep=True)
            return None

    def find_by_slug(self, slug: str) -> Optional[Product]:
        with self._lock:
            for p in self._products:
                if p.slug == slug:
                    return p.model_copy(deep=True)
            return None

    def find_variant_by_id(
        self, product_id: str, variant_id: str
    ) -> Optional[tuple[Product, ProductVariant]]:
        with self._lock:
            for p in self._products:
                if p.id == product_id:
                    for v in p.variants:
                        if v.id == variant_id:
                            return p.model_copy(deep=True), v.model_copy(deep=True)
            return None

    def find_related(self, product: Product, limit: int) -> list[Product]:
        with self._lock:
            candidates = [
                p for p in self._products if p.is_active and p.id != product.id
            ]
            candidates.sort(
                key=lambda c: (
                    (2 if c.category == product.category else 0)
                    + (2 if c.origin == product.origin else 0)
                    + (1 if c.roast_level == product.roast_level else 0),
                    c.rating_average,
                ),
                reverse=True,
            )
            return [p.model_copy(deep=True) for p in candidates[:limit]]

    def create(self, data: CreateProductInput) -> Product:
        now = _now_iso()
        variants = [
            ProductVariant(
                id=v.id or str(uuid4()),
                sku=v.sku,
                size=v.size,
                grind=v.grind,
                label=v.label,
                price_paise=v.price_paise,
                compare_at_paise=v.compare_at_paise,
                stock=v.stock,
            )
            for v in data.variants
        ]
        product = Product(
            id=str(uuid4()),
            name=data.name,
            slug=data.slug,
            short_description=data.short_description,
            description=data.description,
            category=data.category,
            roast_level=data.roast_level,
            origin=data.origin,
            tasting_notes=list(data.tasting_notes),
            images=list(data.images),
            variants=variants,
            is_featured=data.is_featured,
            is_active=data.is_active,
            rating_average=0.0,
            rating_count=0,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._products.append(product.model_copy(deep=True))
        return product

    def update(self, product_id: str, data: UpdateProductInput) -> Optional[Product]:
        with self._lock:
            for idx, existing in enumerate(self._products):
                if existing.id == product_id:
                    updated = existing.model_copy(deep=True)
                    patch = data.model_dump(exclude_unset=True)
                    if "variants" in patch and data.variants is not None:
                        updated.variants = [
                            ProductVariant(
                                id=v.id or str(uuid4()),
                                sku=v.sku,
                                size=v.size,
                                grind=v.grind,
                                label=v.label,
                                price_paise=v.price_paise,
                                compare_at_paise=v.compare_at_paise,
                                stock=v.stock,
                            )
                            for v in data.variants
                        ]
                        del patch["variants"]
                    for k, val in patch.items():
                        setattr(updated, k, val)
                    updated.updated_at = _now_iso()
                    self._products[idx] = updated.model_copy(deep=True)
                    return updated
            return None

    def delete(self, product_id: str) -> bool:
        with self._lock:
            before = len(self._products)
            self._products = [p for p in self._products if p.id != product_id]
            return len(self._products) < before

    def update_variant_inventory(
        self,
        product_id: str,
        variant_id: str,
        stock: Optional[int] = None,
        price_paise: Optional[int] = None,
    ) -> Optional[ProductVariant]:
        with self._lock:
            for p in self._products:
                if p.id == product_id:
                    for v in p.variants:
                        if v.id == variant_id:
                            if stock is not None:
                                v.stock = stock
                            if price_paise is not None:
                                v.price_paise = price_paise
                            p.updated_at = _now_iso()
                            return v.model_copy(deep=True)
            return None

    def reserve_stock(
        self, items: list[StockReservationItem]
    ) -> StockReservationResult:
        aggregated: dict[tuple[str, str], int] = {}
        for item in items:
            key = (item.product_id, item.variant_id)
            aggregated[key] = aggregated.get(key, 0) + item.quantity

        with self._lock:
            failures: list[StockReservationFailure] = []
            targets: list[tuple[Product, ProductVariant, int]] = []

            for (product_id, variant_id), qty in aggregated.items():
                product = next(
                    (p for p in self._products if p.id == product_id and p.is_active),
                    None,
                )
                variant = (
                    next((v for v in product.variants if v.id == variant_id), None)
                    if product
                    else None
                )
                if not product or not variant:
                    failures.append(
                        StockReservationFailure(
                            product_id=product_id,
                            variant_id=variant_id,
                            product_name=product.name if product else "Unknown product",
                            variant_label=variant.label if variant else "Unknown variant",
                            requested=qty,
                            available=0,
                        )
                    )
                    continue

                if variant.stock < qty:
                    failures.append(
                        StockReservationFailure(
                            product_id=product.id,
                            variant_id=variant.id,
                            product_name=product.name,
                            variant_label=variant.label,
                            requested=qty,
                            available=variant.stock,
                        )
                    )
                    continue

                targets.append((product, variant, qty))

            if failures:
                return StockReservationResult(ok=False, failures=failures)

            now = _now_iso()
            for product, variant, qty in targets:
                variant.stock -= qty
                product.updated_at = now

            return StockReservationResult(ok=True, failures=[])

    def release_stock(self, items: list[StockReservationItem]) -> None:
        with self._lock:
            now = _now_iso()
            for item in items:
                product = next((p for p in self._products if p.id == item.product_id), None)
                if not product:
                    continue
                variant = next(
                    (v for v in product.variants if v.id == item.variant_id), None
                )
                if variant:
                    variant.stock += item.quantity
                    product.updated_at = now

    def list_low_stock(self, threshold: int) -> list[LowStockVariantEntry]:
        with self._lock:
            entries: list[LowStockVariantEntry] = []
            for p in self._products:
                if not p.is_active:
                    continue
                for v in p.variants:
                    if v.stock <= threshold:
                        entries.append(
                            LowStockVariantEntry(
                                product_id=p.id,
                                product_name=p.name,
                                product_slug=p.slug,
                                category=p.category,
                                variant=v.model_copy(deep=True),
                            )
                        )
            entries.sort(key=lambda e: e.variant.stock)
            return entries

    def update_rating_stats(
        self, product_id: str, rating_average: float, rating_count: int
    ) -> None:
        with self._lock:
            for p in self._products:
                if p.id == product_id:
                    p.rating_average = rating_average
                    p.rating_count = rating_count
                    p.updated_at = _now_iso()
                    return
