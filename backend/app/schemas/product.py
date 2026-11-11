from typing import Literal, Optional

from pydantic import Field

from app.models.domain import CamelModel, ProductCategory, RoastLevel


class ListProductsQuery(CamelModel):
    search: Optional[str] = Field(default=None, max_length=100)
    category: Optional[ProductCategory] = None
    roast: Optional[RoastLevel] = None
    origin: Optional[str] = Field(default=None, max_length=80)
    min_price: Optional[float] = Field(default=None, ge=0, le=100000)
    max_price: Optional[float] = Field(default=None, ge=0, le=100000)
    in_stock: Optional[bool] = None
    featured: Optional[bool] = None
    sort: Literal["newest", "price_asc", "price_desc", "rating_desc", "popular"] = "popular"
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=12, ge=1, le=48)
