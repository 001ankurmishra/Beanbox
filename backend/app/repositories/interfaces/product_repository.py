from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional

from app.models.domain import (
    CamelModel,
    Product,
    ProductCategory,
    ProductVariant,
    RoastLevel,
    VariantGrind,
    VariantSize,
)


@dataclass
class ProductListQuery:
    search: Optional[str] = None
    category: Optional[ProductCategory] = None
    roast: Optional[RoastLevel] = None
    origin: Optional[str] = None
    min_price_paise: Optional[int] = None
    max_price_paise: Optional[int] = None
    in_stock_only: Optional[bool] = None
    featured_only: Optional[bool] = None
    include_inactive: bool = False
    sort: Literal["newest", "price_asc", "price_desc", "rating_desc", "popular"] = "popular"
    page: int = 1
    limit: int = 12


class ProductFacets(CamelModel):
    origins: list[str]
    categories: list[ProductCategory]
    roast_levels: list[RoastLevel]


class ProductListResult(CamelModel):
    items: list[Product]
    total: int
    facets: ProductFacets


@dataclass
class StockReservationItem:
    product_id: str
    variant_id: str
    quantity: int


class StockReservationFailure(CamelModel):
    product_id: str
    variant_id: str
    product_name: str
    variant_label: str
    requested: int
    available: int


class StockReservationResult(CamelModel):
    ok: bool
    failures: list[StockReservationFailure] = []


class VariantInput(CamelModel):
    id: Optional[str] = None
    sku: str
    size: VariantSize
    grind: VariantGrind
    label: str
    price_paise: int
    compare_at_paise: Optional[int] = None
    stock: int
    is_active: bool = True


class CreateProductInput(CamelModel):
    name: str
    slug: str
    short_description: str
    description: str
    category: ProductCategory
    roast_level: RoastLevel
    origin: str
    tasting_notes: list[str]
    images: list[str]
    variants: list[VariantInput]
    is_featured: bool = False
    is_active: bool = True


class UpdateProductInput(CamelModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    category: Optional[ProductCategory] = None
    roast_level: Optional[RoastLevel] = None
    origin: Optional[str] = None
    tasting_notes: Optional[list[str]] = None
    images: Optional[list[str]] = None
    variants: Optional[list[VariantInput]] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None


class LowStockVariantEntry(CamelModel):
    product_id: str
    product_name: str
    product_slug: str
    category: ProductCategory
    variant: ProductVariant


class ProductRepository(ABC):
    @abstractmethod
    def list(self, query: ProductListQuery) -> ProductListResult: ...

    @abstractmethod
    def find_by_id(self, product_id: str) -> Optional[Product]: ...

    @abstractmethod
    def find_by_slug(self, slug: str) -> Optional[Product]: ...

    @abstractmethod
    def find_variant_by_id(
        self, product_id: str, variant_id: str
    ) -> Optional[tuple[Product, ProductVariant]]: ...

    @abstractmethod
    def find_related(self, product: Product, limit: int) -> list[Product]: ...

    @abstractmethod
    def create(self, data: CreateProductInput) -> Product: ...

    @abstractmethod
    def update(self, product_id: str, data: UpdateProductInput) -> Optional[Product]: ...

    @abstractmethod
    def delete(self, product_id: str) -> bool: ...

    @abstractmethod
    def update_variant_inventory(
        self,
        product_id: str,
        variant_id: str,
        stock: Optional[int] = None,
        price_paise: Optional[int] = None,
    ) -> Optional[ProductVariant]: ...

    @abstractmethod
    def reserve_stock(
        self, items: list[StockReservationItem]
    ) -> StockReservationResult:
        """Atomically verifies and decrements stock for all items (all-or-nothing)."""
        ...

    @abstractmethod
    def release_stock(self, items: list[StockReservationItem]) -> None: ...

    @abstractmethod
    def list_low_stock(self, threshold: int) -> list[LowStockVariantEntry]: ...

    @abstractmethod
    def update_rating_stats(
        self, product_id: str, rating_average: float, rating_count: int
    ) -> None: ...
