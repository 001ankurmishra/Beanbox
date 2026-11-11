'use client';

import React, { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Filter, Search, SlidersHorizontal, X } from 'lucide-react';
import { productsApi } from '@/lib/api/endpoints';
import { CATEGORY_LABELS, ROAST_LABELS } from '@/lib/format';
import { Product, ProductCategory, ProductListResponse, RoastLevel } from '@/types/api';
import { ProductCard } from '@/components/products/ProductCard';
import { ProductSkeletonGrid } from '@/components/products/ProductSkeleton';
import { EmptyState } from '@/components/ui/EmptyState';

const CATEGORIES: ProductCategory[] = [
  'beans',
  'ground',
  'cold_brew',
  'equipment',
  'gift_sets'
];
const ROASTS: RoastLevel[] = [
  'light',
  'medium_light',
  'medium',
  'medium_dark',
  'dark'
];

function ShopContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const search = searchParams.get('search') || '';
  const category = (searchParams.get('category') as ProductCategory) || undefined;
  const roast = (searchParams.get('roast') as RoastLevel) || undefined;
  const origin = searchParams.get('origin') || undefined;
  const minPrice = searchParams.get('minPrice') || '';
  const maxPrice = searchParams.get('maxPrice') || '';
  const sort =
    (searchParams.get('sort') as
      | 'popular'
      | 'newest'
      | 'price_asc'
      | 'price_desc'
      | 'rating_desc') || 'popular';
  const page = Math.max(1, Number(searchParams.get('page') || '1'));

  const [searchInput, setSearchInput] = useState(search);
  const [minInput, setMinInput] = useState(minPrice);
  const [maxInput, setMaxInput] = useState(maxPrice);
  const [data, setData] = useState<ProductListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showMobileFilters, setShowMobileFilters] = useState(false);

  useEffect(() => {
    setSearchInput(search);
    setMinInput(minPrice);
    setMaxInput(maxPrice);
  }, [search, minPrice, maxPrice]);

  const updateQuery = useCallback(
    (updates: Record<string, string | undefined>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(updates)) {
        if (!v) next.delete(k);
        else next.set(k, v);
      }
      if (!('page' in updates)) {
        next.set('page', '1');
      }
      router.push(`/shop?${next.toString()}`);
    },
    [router, searchParams]
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    productsApi
      .list({
        search: search || undefined,
        category,
        roast,
        origin,
        minPrice: minPrice ? Number(minPrice) : undefined,
        maxPrice: maxPrice ? Number(maxPrice) : undefined,
        sort,
        page,
        limit: 9
      })
      .then((res) => {
        if (active) setData(res);
      })
      .catch(() => {
        if (active) setData(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [search, category, roast, origin, minPrice, maxPrice, sort, page]);

  const clearAll = () => {
    setSearchInput('');
    setMinInput('');
    setMaxInput('');
    router.push('/shop');
  };

  const hasFilters = Boolean(
    search || category || roast || origin || minPrice || maxPrice
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
      {/* Header & Search */}
      <div className="flex flex-col gap-6 border-b border-espresso-200 pb-8 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-caramel-dark">
            BeanBox Roastery Catalog
          </p>
          <h1 className="mt-1 font-serif text-3xl font-bold text-espresso-900 sm:text-4xl">
            Specialty Coffees & Gear
          </h1>
          <p className="mt-2 text-sm text-espresso-600">
            Roasted weekly in small batches. Filter by brew style, roast profile,
            or estate origin.
          </p>
        </div>

        <search className="w-full md:w-80">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateQuery({ search: searchInput.trim() || undefined });
            }}
            className="flex gap-2"
          >
            <div className="relative flex-1">
              <label htmlFor="shop-search" className="sr-only">
                Search coffees
              </label>
              <input
                id="shop-search"
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search tasting notes, origin…"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                className="h-11 w-full rounded-xl border border-espresso-200 bg-white pl-3.5 pr-9 text-sm text-espresso-900"
              />
              <Search
                className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-espresso-500"
                aria-hidden="true"
              />
            </div>
            <button
              type="submit"
              className="min-h-[44px] rounded-xl bg-espresso-900 px-4 text-sm font-semibold text-white hover:bg-espresso-800"
            >
              Search
            </button>
          </form>
        </search>
      </div>

      {/* Category Pills */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => updateQuery({ category: undefined })}
            className={`min-h-[40px] rounded-full px-4 text-xs font-semibold transition ${
              !category
                ? 'bg-espresso-900 text-white'
                : 'border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100'
            }`}
          >
            All Items
          </button>
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() =>
                updateQuery({ category: category === cat ? undefined : cat })
              }
              className={`min-h-[40px] rounded-full px-4 text-xs font-semibold transition ${
                category === cat
                  ? 'bg-espresso-900 text-white'
                  : 'border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100'
              }`}
            >
              {CATEGORY_LABELS[cat]}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setShowMobileFilters((v) => !v)}
            className="inline-flex min-h-[40px] items-center gap-1.5 rounded-xl border border-espresso-200 bg-white px-3.5 text-xs font-semibold lg:hidden"
          >
            <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
            Filters
          </button>

          <div className="flex items-center gap-2">
            <label htmlFor="shop-sort" className="text-xs font-medium text-espresso-600">
              Sort:
            </label>
            <select
              id="shop-sort"
              value={sort}
              onChange={(e) => updateQuery({ sort: e.target.value })}
              className="h-10 rounded-xl border border-espresso-200 bg-white px-3 text-xs font-semibold text-espresso-900"
            >
              <option value="popular">Featured & Popular</option>
              <option value="price_asc">Price: Low to High</option>
              <option value="price_desc">Price: High to Low</option>
              <option value="rating_desc">Highest Rated</option>
              <option value="newest">Newest Roasts</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Grid with Sidebar */}
      <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-12">
        <aside
          className={`${
            showMobileFilters ? 'block' : 'hidden'
          } lg:block lg:col-span-3 space-y-6`}
        >
          <div className="rounded-2xl border border-espresso-200 bg-white p-5 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-serif text-base font-bold text-espresso-900">
                <Filter className="h-4 w-4 text-caramel" aria-hidden="true" />
                Refine Roasts
              </h2>
              {hasFilters && (
                <button
                  type="button"
                  onClick={clearAll}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-caramel-dark hover:underline"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                  Clear all
                </button>
              )}
            </div>

            {/* Roast Level */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-espresso-600">
                Roast Level
              </h3>
              <div className="mt-2.5 space-y-1.5">
                {ROASTS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() =>
                      updateQuery({ roast: roast === r ? undefined : r })
                    }
                    className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-xs font-medium transition ${
                      roast === r
                        ? 'bg-espresso-900 text-white'
                        : 'text-espresso-700 hover:bg-espresso-100'
                    }`}
                  >
                    <span>{ROAST_LABELS[r]}</span>
                    {roast === r && <span>✓</span>}
                  </button>
                ))}
              </div>
            </div>

            {/* Origin */}
            {data?.facets?.origins && data.facets.origins.length > 0 && (
              <div>
                <label
                  htmlFor="filter-origin"
                  className="block text-xs font-semibold uppercase tracking-wider text-espresso-600"
                >
                  Estate / Origin
                </label>
                <select
                  id="filter-origin"
                  value={origin || ''}
                  onChange={(e) =>
                    updateQuery({ origin: e.target.value || undefined })
                  }
                  className="mt-2 h-10 w-full rounded-xl border border-espresso-200 bg-espresso-50 px-3 text-xs font-medium text-espresso-900"
                >
                  <option value="">All Origins</option>
                  {data.facets.origins.map((orig) => (
                    <option key={orig} value={orig}>
                      {orig}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Price Range */}
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-espresso-600">
                Price Range (INR ₹)
              </h3>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateQuery({
                    minPrice: minInput.trim() || undefined,
                    maxPrice: maxInput.trim() || undefined
                  });
                }}
                className="mt-2.5 space-y-2.5"
              >
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label htmlFor="min-inr" className="sr-only">
                      Minimum INR
                    </label>
                    <input
                      id="min-inr"
                      type="text"
                      inputMode="numeric"
                      value={minInput}
                      onChange={(e) => setMinInput(e.target.value)}
                      placeholder="Min ₹"
                      className="h-10 w-full rounded-xl border border-espresso-200 px-3 text-xs"
                    />
                  </div>
                  <div>
                    <label htmlFor="max-inr" className="sr-only">
                      Maximum INR
                    </label>
                    <input
                      id="max-inr"
                      type="text"
                      inputMode="numeric"
                      value={maxInput}
                      onChange={(e) => setMaxInput(e.target.value)}
                      placeholder="Max ₹"
                      className="h-10 w-full rounded-xl border border-espresso-200 px-3 text-xs"
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  className="w-full min-h-[38px] rounded-xl border border-espresso-300 bg-espresso-50 text-xs font-semibold text-espresso-900 hover:bg-espresso-100"
                >
                  Apply Price Filter
                </button>
              </form>
            </div>
          </div>
        </aside>

        <div className="lg:col-span-9">
          {loading ? (
            <ProductSkeletonGrid count={6} />
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              title="No coffees matched those filters"
              description="Try clearing your search or broadening your roast and price filters."
              actionLabel="Reset All Filters"
              onAction={clearAll}
            />
          ) : (
            <>
              <div className="mb-4 flex items-center justify-between text-xs text-espresso-600">
                <span>
                  Showing <strong>{data.items.length}</strong> of{' '}
                  <strong>{data.pagination.totalItems}</strong> item(s)
                </span>
                <span>
                  Page {data.pagination.page} of {data.pagination.totalPages}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-3">
                {data.items.map((product: Product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>

              {/* Pagination */}
              {data.pagination.totalPages > 1 && (
                <nav
                  aria-label="Pagination"
                  className="mt-10 flex items-center justify-center gap-2"
                >
                  <button
                    type="button"
                    disabled={!data.pagination.hasPrev}
                    onClick={() => updateQuery({ page: String(page - 1) })}
                    className="min-h-[42px] rounded-xl border border-espresso-200 bg-white px-4 text-sm font-medium disabled:opacity-40"
                  >
                    Previous
                  </button>
                  {Array.from(
                    { length: data.pagination.totalPages },
                    (_, idx) => idx + 1
                  ).map((p) => (
                    <button
                      key={p}
                      type="button"
                      aria-current={p === page ? 'page' : undefined}
                      onClick={() => updateQuery({ page: String(p) })}
                      className={`min-h-[42px] min-w-[42px] rounded-xl text-sm font-semibold ${
                        p === page
                          ? 'bg-espresso-900 text-white'
                          : 'border border-espresso-200 bg-white text-espresso-800 hover:bg-espresso-100'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    type="button"
                    disabled={!data.pagination.hasNext}
                    onClick={() => updateQuery({ page: String(page + 1) })}
                    className="min-h-[42px] rounded-xl border border-espresso-200 bg-white px-4 text-sm font-medium disabled:opacity-40"
                  >
                    Next
                  </button>
                </nav>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ShopPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
          <ProductSkeletonGrid count={6} />
        </div>
      }
    >
      <ShopContent />
    </Suspense>
  );
}
