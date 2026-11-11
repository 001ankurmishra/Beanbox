from dataclasses import dataclass
from typing import Optional

from app.config import Settings
from app.repositories.interfaces import Repositories
from app.services.address_service import AddressService
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.cart_service import CartService
from app.services.email_service import ConsoleEmailService, EmailService
from app.services.order_service import OrderService
from app.services.payment_service import PaymentProvider, create_payment_provider
from app.services.product_service import ProductService
from app.services.review_service import ReviewService
from app.services.wishlist_service import WishlistService


@dataclass
class Services:
    email_service: EmailService
    payment_provider: PaymentProvider
    auth_service: AuthService
    product_service: ProductService
    cart_service: CartService
    address_service: AddressService
    order_service: OrderService
    review_service: ReviewService
    wishlist_service: WishlistService
    admin_service: AdminService


def create_services(
    repos: Repositories,
    settings: Settings,
    email_service: Optional[EmailService] = None,
    payment_provider: Optional[PaymentProvider] = None,
) -> Services:
    email = email_service or ConsoleEmailService(quiet=settings.app_env == "test")
    provider = payment_provider or create_payment_provider(settings)

    auth = AuthService(repos.users, email, settings)
    products = ProductService(repos.products)
    cart = CartService(repos.carts, repos.products)
    addresses = AddressService(repos.addresses)
    orders = OrderService(
        repos.orders,
        repos.carts,
        repos.products,
        repos.coupons,
        repos.addresses,
        repos.users,
        repos.payment_events,
        provider,
        email,
        settings,
    )
    reviews = ReviewService(repos.reviews, repos.products, repos.orders, repos.users)
    wishlist = WishlistService(repos.wishlist, repos.products)
    admin = AdminService(
        repos.products,
        repos.orders,
        repos.coupons,
        repos.users,
        orders,
        provider,
        email,
    )

    return Services(
        email_service=email,
        payment_provider=provider,
        auth_service=auth,
        product_service=products,
        cart_service=cart,
        address_service=addresses,
        order_service=orders,
        review_service=reviews,
        wishlist_service=wishlist,
        admin_service=admin,
    )
