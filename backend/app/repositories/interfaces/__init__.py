from dataclasses import dataclass

from .address_repository import AddressRepository, CreateAddressInput, UpdateAddressInput
from .cart_repository import CartRepository
from .coupon_repository import CouponRepository, CreateCouponInput, UpdateCouponInput
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
from .user_repository import CreateUserInput, UpdateUserInput, UserRepository
from .wishlist_repository import WishlistRepository


@dataclass
class Repositories:
    users: UserRepository
    products: ProductRepository
    carts: CartRepository
    coupons: CouponRepository
    addresses: AddressRepository
    orders: OrderRepository
    reviews: ReviewRepository
    wishlist: WishlistRepository
    payment_events: PaymentEventRepository


__all__ = [
    "AddressRepository",
    "CartRepository",
    "CouponRepository",
    "CreateAddressInput",
    "CreateCouponInput",
    "CreateOrderInput",
    "CreateProductInput",
    "CreateReviewInput",
    "CreateUserInput",
    "LowStockVariantEntry",
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
    "StockReservationFailure",
    "StockReservationItem",
    "StockReservationResult",
    "TopProductStat",
    "UpdateAddressInput",
    "UpdateCouponInput",
    "UpdateProductInput",
    "UpdateUserInput",
    "UserRepository",
    "VariantInput",
    "WishlistRepository",
]
