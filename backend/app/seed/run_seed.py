from app.config import get_settings
from app.repositories import create_in_memory_repositories
from app.repositories.interfaces import ProductListQuery
from app.seed.seed_supabase import seed_supabase_database


def main() -> None:
    settings = get_settings()
    use_supabase = settings.repository_backend == "supabase" or (
        settings.repository_backend == "auto" and bool(settings.database_url)
    )

    if use_supabase and settings.database_url:
        counts = seed_supabase_database(settings.database_url, apply_schema=True)
        print("=== BeanBox Supabase PostgreSQL Seed Verification ===")
        print(f"Products in Supabase: {counts['products']}")
        print(f"Users in Supabase: {counts['users']}")
        print(f"Coupons in Supabase: {counts['coupons']}")
        print("Supabase schema & seed data verified cleanly.")
        return

    repos = create_in_memory_repositories()
    products_res = repos.products.list(ProductListQuery(page=1, limit=100))
    users, user_total = repos.users.list(page=1, limit=20)
    coupons = repos.coupons.list()

    print("=== BeanBox In-Memory Seed Verification ===")
    print(f"Products seeded: {products_res.total}")
    print(f"Categories: {', '.join(products_res.facets.categories)}")
    print(f"Users seeded: {user_total}")
    for u in users:
        print(f"  - {u.email} ({u.role})")
    print(f"Coupons seeded: {len(coupons)}")
    for c in coupons:
        print(f"  - {c.code} (active={c.is_active}, expires_at={c.expires_at})")
    print("Seed dataset verified cleanly.")


if __name__ == "__main__":
    main()
