from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


UserRole = Literal["customer", "admin"]
ProductCategory = Literal["beans", "ground", "cold_brew", "equipment", "gift_sets"]
RoastLevel = Literal["light", "medium_light", "medium", "medium_dark", "dark", "na"]
VariantSize = Literal["250g", "500g", "1kg", "standard"]
VariantGrind = Literal["whole_bean", "espresso", "filter", "french_press", "na"]
CouponType = Literal["percent", "flat"]
AddressLabel = Literal["Home", "Work", "Other"]
OrderStatus = Literal[
    "pending",
    "paid",
    "processing",
    "shipped",
    "delivered",
    "cancelled",
    "refunded",
]
PaymentStatus = Literal["unpaid", "paid", "failed", "expired", "refunded"]


class User(CamelModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    password_hash: str
    role: UserRole
    email_verified: bool = False
    email_verified_at: Optional[str] = None
    totp_enabled: bool = False
    created_at: str
    updated_at: str


class PublicUser(CamelModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: UserRole
    email_verified: bool = False
    email_verified_at: Optional[str] = None
    totp_enabled: bool = False
    created_at: str
    updated_at: str


class PasswordResetToken(CamelModel):
    id: str
    user_id: str
    token_hash: str
    expires_at: str
    used_at: Optional[str] = None
    created_at: str


class EmailVerificationToken(CamelModel):
    id: str
    user_id: str
    token_hash: str
    expires_at: str
    used_at: Optional[str] = None
    created_at: str


class Session(CamelModel):
    id: str
    user_id: str
    refresh_token_hash: str
    previous_refresh_hashes: list[str] = []
    grace_refresh_hash: Optional[str] = None
    grace_expires_at: Optional[str] = None
    grace_uses_remaining: int = 3
    family_id: str
    user_agent: str
    ip: str
    created_at: str
    last_used_at: str
    expires_at: str
    revoked_at: Optional[str] = None


class PublicSession(CamelModel):
    id: str
    user_agent: str
    ip: str
    created_at: str
    last_used_at: str
    expires_at: str
    is_current: bool = False


OAuthProvider = Literal["google"]


class OAuthAccount(CamelModel):
    id: str
    user_id: str
    provider: OAuthProvider
    provider_user_id: str
    provider_email: str
    created_at: str
    updated_at: str


class TotpSecret(CamelModel):
    id: str
    user_id: str
    encrypted_secret: str
    is_enabled: bool = False
    last_used_timestep: Optional[int] = None
    verified_at: Optional[str] = None
    created_at: str
    updated_at: str


class RecoveryCode(CamelModel):
    id: str
    user_id: str
    code_hash: str
    used_at: Optional[str] = None
    created_at: str


LoginAttemptKeyType = Literal["account", "ip", "2fa"]


class LoginAttemptRecord(CamelModel):
    id: str
    key: str
    key_type: LoginAttemptKeyType
    failed_count: int = 0
    lockout_level: int = 0
    first_failed_at: str
    last_failed_at: str
    locked_until: Optional[str] = None


AuditOutcome = Literal["success", "failure", "warning"]


class AuditLogEntry(CamelModel):
    id: str
    user_id: Optional[str] = None
    event_type: str
    outcome: AuditOutcome
    target_id: Optional[str] = None
    ip: str
    user_agent: str
    request_id: str
    metadata: dict[str, Any] = {}
    created_at: str


class ProductVariant(CamelModel):
    id: str
    sku: str
    size: VariantSize
    grind: VariantGrind
    label: str
    price_paise: int
    compare_at_paise: Optional[int] = None
    stock: int
    is_active: bool = True


class Product(CamelModel):
    id: str
    name: str
    slug: str
    short_description: str
    description: str
    category: ProductCategory
    roast_level: RoastLevel
    origin: str
    tasting_notes: list[str]
    images: list[str]
    variants: list[ProductVariant]
    is_featured: bool
    is_active: bool
    rating_average: float
    rating_count: int
    created_at: str
    updated_at: str


class CartItem(CamelModel):
    product_id: str
    variant_id: str
    quantity: int
    added_at: str


class Cart(CamelModel):
    id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    items: list[CartItem]
    updated_at: str


class Coupon(CamelModel):
    id: str
    code: str
    description: str
    type: CouponType
    value: int
    min_order_paise: int
    max_discount_paise: Optional[int] = None
    expires_at: str
    usage_limit: int
    used_count: int
    is_active: bool
    created_at: str
    updated_at: str


class Address(CamelModel):
    id: str
    user_id: str
    label: AddressLabel
    full_name: str
    phone: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: Literal["India"] = "India"
    is_default: bool
    created_at: str
    updated_at: str


class OrderItem(CamelModel):
    product_id: str
    variant_id: str
    sku: str
    product_name: str
    product_slug: str
    variant_label: str
    image: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int


class OrderAddressSnapshot(CamelModel):
    label: AddressLabel
    full_name: str
    phone: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: Literal["India"] = "India"


class OrderPricing(CamelModel):
    items_subtotal_paise: int
    discount_paise: int
    taxable_amount_paise: int
    gst_rate: float
    gst_paise: int
    cgst_paise: int
    sgst_paise: int
    shipping_paise: int
    total_paise: int
    currency: Literal["INR"] = "INR"


class Order(CamelModel):
    id: str
    order_number: str
    user_id: str
    items: list[OrderItem]
    shipping_address: OrderAddressSnapshot
    coupon_code: Optional[str] = None
    coupon_id: Optional[str] = None
    pricing: OrderPricing
    status: OrderStatus
    payment_status: PaymentStatus
    payment_provider: Optional[Literal["stripe", "mock"]] = None
    payment_session_id: Optional[str] = None
    payment_intent_id: Optional[str] = None
    stock_released: bool = False
    cancel_reason: Optional[str] = None
    created_at: str
    updated_at: str
    paid_at: Optional[str] = None
    shipped_at: Optional[str] = None
    delivered_at: Optional[str] = None
    cancelled_at: Optional[str] = None


class PaymentEvent(CamelModel):
    id: str
    event_id: str
    provider: Literal["stripe", "mock"]
    event_type: str
    order_id: Optional[str] = None
    processed_at: str


class Review(CamelModel):
    id: str
    product_id: str
    user_id: str
    user_name: str
    rating: int
    title: str
    comment: str
    verified_purchase: bool
    created_at: str
    updated_at: str


class WishlistItem(CamelModel):
    id: str
    user_id: str
    product_id: str
    created_at: str


class FailedJob(CamelModel):
    id: str
    task_name: str
    args_json: Any
    error_message: str
    traceback: str
    attempts: int = 1
    queue: str = "default"
    created_at: str
    resolved_at: Optional[str] = None
