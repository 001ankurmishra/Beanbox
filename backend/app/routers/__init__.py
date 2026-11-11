from .addresses import router as addresses_router
from .admin import router as admin_router
from .auth import router as auth_router
from .cart import router as cart_router
from .orders import checkout_router, orders_router
from .payments import router as payments_router
from .products import products_router, reviews_router
from .wishlist import router as wishlist_router

__all__ = [
    "addresses_router",
    "admin_router",
    "auth_router",
    "cart_router",
    "checkout_router",
    "orders_router",
    "payments_router",
    "products_router",
    "reviews_router",
    "wishlist_router",
]
