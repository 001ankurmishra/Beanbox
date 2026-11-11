from __future__ import annotations

import math

from app.models.domain import Product
from app.repositories.interfaces import ProductListQuery, ProductRepository
from app.schemas.common import PaginationMeta
from app.utils.errors import NotFoundError


class ProductService:
    def __init__(self, product_repo: ProductRepository) -> None:
        self._product_repo = product_repo

    def list(self, query: ProductListQuery) -> dict:
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

    def get_by_slug(self, slug: str) -> Product:
        product = self._product_repo.find_by_slug(slug)
        if not product or not product.is_active:
            raise NotFoundError("Product not found")
        return product

    def get_related_by_slug(self, slug: str, limit: int = 4) -> list[Product]:
        product = self.get_by_slug(slug)
        return self._product_repo.find_related(product, limit)
