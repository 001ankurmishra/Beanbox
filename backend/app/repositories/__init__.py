from typing import Optional

from app.repositories.interfaces import Repositories
from app.repositories.memory import (
    InMemoryAddressRepository,
    InMemoryAuditLogRepository,
    InMemoryCartRepository,
    InMemoryCouponRepository,
    InMemoryFailedJobRepository,
    InMemoryLoginAttemptRepository,
    InMemoryOAuthAccountRepository,
    InMemoryOrderRepository,
    InMemoryPaymentEventRepository,
    InMemoryProductRepository,
    InMemoryReviewRepository,
    InMemorySessionRepository,
    InMemoryTwoFactorRepository,
    InMemoryUserRepository,
    InMemoryWishlistRepository,
)
from app.repositories.supabase import (
    SupabaseAddressRepository,
    SupabaseAuditLogRepository,
    SupabaseCartRepository,
    SupabaseCouponRepository,
    SupabaseFailedJobRepository,
    SupabaseLoginAttemptRepository,
    SupabaseOAuthAccountRepository,
    SupabaseOrderRepository,
    SupabasePaymentEventRepository,
    SupabaseProductRepository,
    SupabaseReviewRepository,
    SupabaseSessionRepository,
    SupabaseTwoFactorRepository,
    SupabaseUserRepository,
    SupabaseWishlistRepository,
    create_pg_pool,
)
from app.seed.seed_data import SeedDataset, create_seed_data


def create_in_memory_repositories(seed: Optional[SeedDataset] = None) -> Repositories:
    data = seed or create_seed_data()
    return Repositories(
        users=InMemoryUserRepository(data.users),
        sessions=InMemorySessionRepository(),
        oauth_accounts=InMemoryOAuthAccountRepository(),
        two_factor=InMemoryTwoFactorRepository(),
        login_attempts=InMemoryLoginAttemptRepository(),
        audit_logs=InMemoryAuditLogRepository(),
        products=InMemoryProductRepository(data.products),
        carts=InMemoryCartRepository(),
        coupons=InMemoryCouponRepository(data.coupons),
        addresses=InMemoryAddressRepository(data.addresses),
        orders=InMemoryOrderRepository(data.orders),
        reviews=InMemoryReviewRepository(data.reviews),
        wishlist=InMemoryWishlistRepository(data.wishlist),
        payment_events=InMemoryPaymentEventRepository(),
        failed_jobs=InMemoryFailedJobRepository(),
    )


def create_supabase_repositories(
    database_url: str, pool: Optional[object] = None
) -> tuple[Repositories, object]:
    """Creates Supabase Postgres repositories backed by a shared ConnectionPool."""
    active_pool = pool or create_pg_pool(database_url)
    repos = Repositories(
        users=SupabaseUserRepository(active_pool),  # type: ignore[arg-type]
        sessions=SupabaseSessionRepository(active_pool),  # type: ignore[arg-type]
        oauth_accounts=SupabaseOAuthAccountRepository(active_pool),  # type: ignore[arg-type]
        two_factor=SupabaseTwoFactorRepository(active_pool),  # type: ignore[arg-type]
        login_attempts=SupabaseLoginAttemptRepository(active_pool),  # type: ignore[arg-type]
        audit_logs=SupabaseAuditLogRepository(active_pool),  # type: ignore[arg-type]
        products=SupabaseProductRepository(active_pool),  # type: ignore[arg-type]
        carts=SupabaseCartRepository(active_pool),  # type: ignore[arg-type]
        coupons=SupabaseCouponRepository(active_pool),  # type: ignore[arg-type]
        addresses=SupabaseAddressRepository(active_pool),  # type: ignore[arg-type]
        orders=SupabaseOrderRepository(active_pool),  # type: ignore[arg-type]
        reviews=SupabaseReviewRepository(active_pool),  # type: ignore[arg-type]
        wishlist=SupabaseWishlistRepository(active_pool),  # type: ignore[arg-type]
        payment_events=SupabasePaymentEventRepository(active_pool),  # type: ignore[arg-type]
        failed_jobs=SupabaseFailedJobRepository(active_pool),  # type: ignore[arg-type]
    )
    return repos, active_pool
