from __future__ import annotations

import math
from typing import Optional

from app.cache.catalog_cache import InMemoryCatalogCache
from app.cache.interfaces import CatalogCache
from app.models.domain import Product
from app.repositories.interfaces import ProductListQuery, ProductRepository
from app.schemas.common import PaginationMeta
from app.utils.errors import NotFoundError


class ProductService:
    def __init__(
        self,
        product_repo: ProductRepository,
        catalog_cache: Optional[CatalogCache] = None,
    ) -> None:
        self._product_repo = product_repo
        self._catalog_cache: CatalogCache = catalog_cache or InMemoryCatalogCache(
            enabled=False
        )

    def _load_list_from_db(self, query: ProductListQuery) -> dict:
        result = self._product_repo.list(query)
        total_pages = max(1, math.ceil(result.total / query.limit))
        return {
            "items": result.items,
            "pagination": PaginationMeta(
                page=query.page,
                limit=query.limit,
                total_items=result.total,
                total_pages=total_pages,
                has_next=query.page < total_pages,
                has_prev=query.page > 1,
            ),
            "facets": result.facets,
        }

    def list_with_cache(
        self, query: ProductListQuery, request_id: str = "-"
    ) -> tuple[dict, bool]:
        return self._catalog_cache.get_or_set_list(
            query, lambda: self._load_list_from_db(query), request_id=request_id
        )

    def list(self, query: ProductListQuery) -> dict:
        data, _ = self.list_with_cache(query)
        return data

    def _load_by_slug_from_db(self, slug: str) -> Product:
        product = self._product_repo.find_by_slug(slug)
        if not product or not product.is_active:
            raise NotFoundError("Product not found")
        return product

    def get_by_slug_with_cache(
        self, slug: str, request_id: str = "-"
    ) -> tuple[Product, bool]:
        return self._catalog_cache.get_or_set_detail(
            slug, lambda: self._load_by_slug_from_db(slug), request_id=request_id
        )

    def get_by_slug(self, slug: str) -> Product:
        product, _ = self.get_by_slug_with_cache(slug)
        return product

    def get_related_by_slug(self, slug: str, limit: int = 4) -> list[Product]:
        product = self.get_by_slug(slug)
        return self._product_repo.find_related(product, limit)
