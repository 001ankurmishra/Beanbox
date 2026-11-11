from typing import Optional

from app.repositories.interfaces import Repositories
from app.repositories.memory import (
    InMemoryAddressRepository,
    InMemoryCartRepository,
    InMemoryCouponRepository,
    InMemoryOrderRepository,
    InMemoryPaymentEventRepository,
    InMemoryProductRepository,
    InMemoryReviewRepository,
    InMemoryUserRepository,
    InMemoryWishlistRepository,
)
from app.repositories.supabase import (
    SupabaseAddressRepository,
    SupabaseCartRepository,
    SupabaseCouponRepository,
    SupabaseOrderRepository,
    SupabasePaymentEventRepository,
    SupabaseProductRepository,
    SupabaseReviewRepository,
    SupabaseUserRepository,
    SupabaseWishlistRepository,
    create_pg_pool,
)
from app.seed.seed_data import SeedDataset, create_seed_data


def create_in_memory_repositories(seed: Optional[SeedDataset] = None) -> Repositories:
    data = seed or create_seed_data()
    return Repositories(
        users=InMemoryUserRepository(data.users),
        products=InMemoryProductRepository(data.products),
        carts=InMemoryCartRepository(),
        coupons=InMemoryCouponRepository(data.coupons),
        addresses=InMemoryAddressRepository(data.addresses),
        orders=InMemoryOrderRepository(data.orders),
        reviews=InMemoryReviewRepository(data.reviews),
        wishlist=InMemoryWishlistRepository(data.wishlist),
        payment_events=InMemoryPaymentEventRepository(),
    )


def create_supabase_repositories(database_url: str) -> tuple[Repositories, object]:
    """Creates Supabase Postgres repositories backed by a shared ConnectionPool."""
    pool = create_pg_pool(database_url)
    repos = Repositories(
        users=SupabaseUserRepository(pool),
        products=SupabaseProductRepository(pool),
        carts=SupabaseCartRepository(pool),
        coupons=SupabaseCouponRepository(pool),
        addresses=SupabaseAddressRepository(pool),
        orders=SupabaseOrderRepository(pool),
        reviews=SupabaseReviewRepository(pool),
        wishlist=SupabaseWishlistRepository(pool),
        payment_events=SupabasePaymentEventRepository(pool),
    )
    return repos, pool
