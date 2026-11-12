import re
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator, model_validator

from app.models.domain import (
    CamelModel,
    CouponType,
    OrderStatus,
    ProductCategory,
    RoastLevel,
    UserRole,
    VariantGrind,
    VariantSize,
)

SLUG_RE = re.compile(r"^[a-z0-9-]+$")
COUPON_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class AdminVariantRequest(CamelModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=120)
    sku: str = Field(min_length=2, max_length=40)
    size: VariantSize
    grind: VariantGrind
    label: str = Field(min_length=2, max_length=80)
    price_paise: int = Field(ge=100, le=50_000_000)
    compare_at_paise: Optional[int] = Field(default=None, ge=100, le=50_000_000)
    stock: int = Field(ge=0, le=100_000)


class AdminCreateProductRequest(CamelModel):
    name: str = Field(min_length=3, max_length=120)
    slug: str = Field(min_length=3, max_length=140)
    short_description: str = Field(min_length=10, max_length=220)
    description: str = Field(min_length=10, max_length=2000)
    category: ProductCategory
    roast_level: RoastLevel
    origin: str = Field(min_length=2, max_length=100)
    tasting_notes: list[str] = Field(min_length=1, max_length=8)
    images: list[str] = Field(min_length=1, max_length=6)
    variants: list[AdminVariantRequest] = Field(min_length=1, max_length=12)
    is_featured: bool = False
    is_active: bool = True

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: str) -> str:
        s = v.strip()
        if not SLUG_RE.match(s):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return s


class AdminUpdateProductRequest(CamelModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=3, max_length=140)
    short_description: Optional[str] = Field(default=None, min_length=10, max_length=220)
    description: Optional[str] = Field(default=None, min_length=10, max_length=2000)
    category: Optional[ProductCategory] = None
    roast_level: Optional[RoastLevel] = None
    origin: Optional[str] = Field(default=None, min_length=2, max_length=100)
    tasting_notes: Optional[list[str]] = Field(default=None, min_length=1, max_length=8)
    images: Optional[list[str]] = Field(default=None, min_length=1, max_length=6)
    variants: Optional[list[AdminVariantRequest]] = Field(
        default=None, min_length=1, max_length=12
    )
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("slug")
    @classmethod
    def check_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not SLUG_RE.match(s):
            raise ValueError("Slug must be lowercase alphanumeric with hyphens")
        return s


class AdminInventoryUpdateRequest(CamelModel):
    stock: Optional[int] = Field(default=None, ge=0, le=100_000)
    price_paise: Optional[int] = Field(default=None, ge=100, le=50_000_000)

    @model_validator(mode="after")
    def require_one_field(self) -> "AdminInventoryUpdateRequest":
        if self.stock is None and self.price_paise is None:
            raise ValueError("Provide at least stock or pricePaise to update")
        return self


class AdminUpdateOrderStatusRequest(CamelModel):
    status: OrderStatus
    reason: Optional[str] = Field(default=None, max_length=250)


class AdminCreateCouponRequest(CamelModel):
    code: str = Field(min_length=3, max_length=30)
    description: str = Field(min_length=3, max_length=200)
    type: CouponType
    value: int = Field(ge=1)
    min_order_paise: int = Field(default=0, ge=0)
    max_discount_paise: Optional[int] = Field(default=None, ge=100)
    expires_at: datetime
    usage_limit: int = Field(ge=1, le=100_000)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def check_code(cls, v: str) -> str:
        s = v.strip()
        if not COUPON_RE.match(s):
            raise ValueError("Coupon code can contain letters, numbers, _ and -")
        return s.upper()

    @model_validator(mode="after")
    def check_type_bounds(self) -> "AdminCreateCouponRequest":
        if self.type == "percent" and self.value > 90:
            raise ValueError("Percent coupon cannot exceed 90%")
        if self.type == "flat" and self.value < 100:
            raise ValueError("Flat discount is in paise and must be at least 100 (₹1)")
        return self


class AdminUpdateCouponRequest(CamelModel):
    code: Optional[str] = Field(default=None, min_length=3, max_length=30)
    description: Optional[str] = Field(default=None, min_length=3, max_length=200)
    type: Optional[CouponType] = None
    value: Optional[int] = Field(default=None, ge=1)
    min_order_paise: Optional[int] = Field(default=None, ge=0)
    max_discount_paise: Optional[int] = Field(default=None, ge=100)
    expires_at: Optional[datetime] = None
    usage_limit: Optional[int] = Field(default=None, ge=1, le=100_000)
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def check_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        if not COUPON_RE.match(s):
            raise ValueError("Coupon code can contain letters, numbers, _ and -")
        return s.upper()


class AdminUpdateUserRoleRequest(CamelModel):
    role: UserRole
