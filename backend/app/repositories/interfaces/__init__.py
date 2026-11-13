from dataclasses import dataclass

from .address_repository import AddressRepository, CreateAddressInput, UpdateAddressInput
from .audit_log_repository import AuditLogRepository, CreateAuditLogInput
from .cart_repository import CartRepository
from .coupon_repository import CouponRepository, CreateCouponInput, UpdateCouponInput
from .failed_job_repository import CreateFailedJobInput, FailedJobRepository
from .login_attempt_repository import LoginAttemptRepository
from .oauth_repository import CreateOAuthAccountInput, OAuthAccountRepository
from .order_repository import (
    CreateOrderInput,
    OrderDashboardStats,
    OrderRepository,
    OrderUpdateFields,
    TopProductStat,
)
from .payment_event_repository import PaymentEventRepository
from .product_repository import (
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
    VariantInput,
)
from .review_repository import CreateReviewInput, ReviewRepository, ReviewStats
from .session_repository import CreateSessionInput, SessionRepository
from .two_factor_repository import TwoFactorRepository
from .user_repository import CreateUserInput, UpdateUserInput, UserRepository
from .wishlist_repository import WishlistRepository


@dataclass
class Repositories:
    users: UserRepository
    sessions: SessionRepository
    oauth_accounts: OAuthAccountRepository
    two_factor: TwoFactorRepository
    login_attempts: LoginAttemptRepository
    audit_logs: AuditLogRepository
    products: ProductRepository
    carts: CartRepository
    coupons: CouponRepository
    addresses: AddressRepository
    orders: OrderRepository
    reviews: ReviewRepository
    wishlist: WishlistRepository
    payment_events: PaymentEventRepository
    failed_jobs: FailedJobRepository


__all__ = [
    "AddressRepository",
    "AuditLogRepository",
    "CartRepository",
    "CouponRepository",
    "CreateAddressInput",
    "CreateAuditLogInput",
    "CreateCouponInput",
    "CreateFailedJobInput",
    "CreateOAuthAccountInput",
    "CreateOrderInput",
    "CreateProductInput",
    "CreateReviewInput",
    "CreateSessionInput",
    "CreateUserInput",
    "FailedJobRepository",
    "LoginAttemptRepository",
    "LowStockVariantEntry",
    "OAuthAccountRepository",
    "OrderDashboardStats",
    "OrderRepository",
    "OrderUpdateFields",
    "PaymentEventRepository",
    "ProductFacets",
    "ProductListQuery",
    "ProductListResult",
    "ProductRepository",
    "Repositories",
    "ReviewRepository",
    "ReviewStats",
    "SessionRepository",
    "StockReservationFailure",
    "StockReservationItem",
    "StockReservationResult",
    "TopProductStat",
    "TwoFactorRepository",
    "UpdateAddressInput",
    "UpdateCouponInput",
    "UpdateProductInput",
    "UpdateUserInput",
    "UserRepository",
    "VariantInput",
    "WishlistRepository",
]
