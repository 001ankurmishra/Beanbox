# BeanBox — Complete Project Progress & Architecture Summary

This document summarizes **everything built, connected, and verified** so far for **BeanBox** (an India-based specialty coffee e-commerce store using `INR (₹)`, `5% GST`, and free shipping at `₹999+`).

---

## 1. High-Level Timeline & What Is Complete

| Phase | Scope | Status |
| :--- | :--- | :--- |
| **Phase 1 — Backend (`/backend`)** | Python 3.13 + FastAPI + Pydantic v2 API, Repository Interfaces, Seeded In-Memory Repositories, Pricing/GST Engine, Stripe + Mock Payments, Pytest Suite, Swagger Docs, `BACKEND_EXPLAINED.md` | **Done & Verified** |
| **Phase 2 — Frontend (`/frontend`)** | Next.js 14 (App Router), TypeScript, Tailwind CSS warm coffee UI, 22 routes (Storefront, Checkout, Mock Pay, Account, Admin Console), Optimistic Cart & Wishlist, Local SVG Artwork | **Done & Verified** |
| **Phase 3 — Live Database (`Supabase`)** | PostgreSQL 17.11 schema (13 tables + FK indexes + RLS), 9 `Supabase*Repository` implementations using `psycopg_pool`, idempotent seeder, live E2E API verification | **Done & Connected** |

---

## 2. Tech Stack & Key Decisions

- **Backend**: Python 3.13, FastAPI, Uvicorn, Pydantic v2 (`CamelModel` converts internal `snake_case` attributes to `camelCase` HTTP JSON), `PyJWT` (`httpOnly` cookie `beanbox_token`), `bcrypt`, `stripe`, `psycopg[binary]` + `psycopg-pool`, `pytest`, `ruff`.
- **Frontend**: Next.js 14 (`14.2.x`, App Router), React 18, TypeScript, Tailwind CSS (`Fraunces` serif + `Plus Jakarta Sans` body fonts, `lucide-react` icons).
- **Database**: Supabase PostgreSQL (`ibskuzkmeyhoncnclobh`, `ap-south-1` Session Pooler).
- **Monetary Precision**: All prices, discounts, GST, and totals are stored and computed in **integer paise** (`₹1 = 100 paise`) to prevent floating-point rounding bugs and match Stripe INR minor units.
- **Indian Pricing & Tax Formula** (`backend/app/services/pricing_service.py`):
  1. `itemsSubtotalPaise` = sum of `variant.pricePaise × quantity` (sourced strictly on server).
  2. `discountPaise` = percent or flat coupon discount (capped and validated server-side).
  3. `taxableAmountPaise` = `itemsSubtotalPaise - discountPaise`.
  4. `gstPaise` = `5%` of `taxableAmountPaise` (split in invoices as `2.5% CGST` + `2.5% SGST`).
  5. `shippingPaise` = `₹0` if `taxableAmountPaise >= ₹999` (`99900` paise), else `₹79` (`7900` paise).
  6. `totalPaise` = `taxableAmountPaise + gstPaise + shippingPaise`.

---

## 3. Everything Built in `/backend`

### A. Repository Layer (`backend/app/repositories/`)
All services and routers depend strictly on Abstract Base Class contracts—never directly on storage:
- **Interfaces (`interfaces/`)**: `UserRepository`, `ProductRepository`, `CartRepository`, `CouponRepository`, `AddressRepository`, `OrderRepository`, `ReviewRepository`, `WishlistRepository`, `PaymentEventRepository`.
- **In-Memory Implementations (`memory/`)**: Thread-safe (`threading.RLock`) seeded repositories used automatically when `APP_ENV=test` so unit tests stay fast and isolated.
- **Supabase Postgres Implementations (`supabase/`)**:
  - `db.py`: `create_pg_pool()` using `psycopg_pool.ConnectionPool` (`min_size=1`, `max_size=10`, `prepare_threshold=None` for PgBouncer compatibility).
  - Deadlock-free atomic stock reservation (`reserve_stock` locks requested variant rows in sorted order via `ORDER BY pv.id FOR UPDATE`) in `supabase/product_repository.py`.
  - Atomic single-query coupon claim (`UPDATE coupons SET used_count = used_count + 1 ... WHERE used_count < usage_limit`) in `supabase/coupon_repository.py`.
- **Composition Root (`app/repositories/__init__.py` & `app/main.py`)**: Automatically connects Supabase whenever `DATABASE_URL` is configured (`APP_ENV != "test"`).

### B. Domain Services (`backend/app/services/`) & Routers (`backend/app/routers/`)
- **Auth (`auth.py` / `auth_service.py`)**: Signup, login, logout, `/me` profile update, forgot/reset password (SHA-256 hashed single-use token, 15-min TTL), RBAC (`customer` / `admin`), automatic guest cart merge on login/signup.
- **Products & Reviews (`products.py` / `product_service.py` / `review_service.py`)**: Search, multi-filter (`category`, `roast`, `origin`, `minPrice`, `maxPrice`, `inStock`, `featured`), sort, pagination (max 48), detail by slug, related products, and verified-buyer-only reviews (1–5★, max 1 per product per user, automatic product rating recalculation).
- **Cart (`cart.py` / `cart_service.py`)**: Guest session cookie (`beanbox_guest_id`), stock enforcement, server-side price recalculation ignoring tampered client prices, and guest-to-user cart merge on auth.
- **Addresses (`addresses.py` / `address_service.py`)**: CRUD with Indian 10-digit mobile and 6-digit PIN code validation + default address promotion.
- **Checkout & Orders (`orders.py` / `order_service.py`)**: Authoritative `/checkout/preview`, atomic order creation with stock & coupon reservation, order history, customer cancellation before shipping (releases stock/coupon + refunds if paid), and Indian GST invoice endpoint (`HSN 0901`, Seller GSTIN, CGST/SGST split).
- **Payments & Webhooks (`payments.py` / `payment_service.py`)**: Unified `PaymentProvider` interface supporting `StripePaymentProvider` (INR test mode) and `MockPaymentProvider` (HMAC-SHA256 signed webhooks + local `/checkout/mock-pay` simulator). Enforces raw-body signature verification, `PaymentEventRepository` webhook idempotency, order confirmation emails, and stock/coupon release on payment failure or expiration.
- **Wishlist (`wishlist.py` / `wishlist_service.py`)**: Save/remove/list active wishlist items.
- **Admin (`admin.py` / `admin_service.py`)**: Dashboard stats (revenue, order status breakdown, top 5 products, low-stock variants `<= 5`), product CRUD, variant stock/price editor, order status state machine (`pending → paid → processing → shipped → delivered / cancelled / refunded`) with shipped email dispatch, coupon CRUD, and user list.
- **Security & Quality (`app/middleware/`)**: Request ID (`X-Request-Id`), security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `CSP`), CORS with `credentials: true`, sliding-window rate limiting (`240 req/min` general; `25 req/15 min` on auth), Pydantic validation on every route, centralized `{ success: false, error, requestId }` handler, and interactive Swagger docs at `/api/docs`.

---

## 4. Everything Built in `/frontend`

### A. Core Architecture (`frontend/src/`)
- **Typed API Client (`src/lib/api/client.ts` & `endpoints.ts`)**: `apiFetch` configured with `credentials: 'include'` for `httpOnly` JWT & guest session cookies, typed `ApiClientError`, and INR/label helpers (`src/lib/format.ts`).
- **Context Providers (`src/context/`)**:
  - `AuthContext.tsx`: Hydrates `/api/auth/me` and triggers cart/wishlist sync on login/logout.
  - `CartContext.tsx`: Optimistic add, quantity update, and remove with automatic state rollback & error toast on failure, plus slide-over drawer control.
  - `WishlistContext.tsx`: Optimistic heart toggle with rollback & toast notifications.
  - `ToastContext.tsx`: Accessible `aria-live="polite"` notifications.
- **Accessible UI & Local Assets (`src/components/` & `public/images/products/`)**:
  - Native `<dialog>` modals (`ConfirmDialog.tsx`, `CartDrawer.tsx`, mobile nav drawer in `Navbar.tsx`) with scroll containment (`overscroll-behavior: contain`) and click-outside fallbacks.
  - 9 custom local SVG product illustrations so every card, gallery, and invoice thumbnail loads cleanly with zero broken external image links.

### B. All 22 Built Next.js Routes (`frontend/src/app/`)
- **Storefront**: `/` (Home hero, categories, featured roasts, Indian estates, testimonials), `/shop` (search, category/roast/origin/INR price filters, sort, pagination, skeletons, empty states), `/products/[slug]` (gallery, size/grind variant picker, live stock indicator, tasting notes, verified buyer reviews, related items).
- **Bag & Checkout**: `/cart` (+ global `CartDrawer`), `/checkout` (saved/new Indian address form, coupon apply/remove, backend pricing breakdown), `/checkout/mock-pay` (interactive test-mode payment outcome simulator), `/orders/success`.
- **Auth**: `/login` (with one-click demo fill buttons), `/signup`, `/forgot-password`, `/reset-password`.
- **Account Portal**: `/account` (profile), `/account/addresses`, `/account/orders`, `/account/orders/[id]` (GST invoice print view + cancel before shipping), `/account/wishlist`.
- **Admin Console**: `/admin` (KPIs, top products, low-stock alerts, recent orders), `/admin/products`, `/admin/orders` (state-machine transitions), `/admin/inventory` (inline stock & INR price updates), `/admin/coupons`.
- **Error Handling**: `not-found.tsx` (404), `error.tsx`, `global-error.tsx`.

---

## 5. Supabase Database State (`backend/supabase/schema.sql`)

- **13 Tables Created with Row-Level Security (`rls=True`) & Zero Missing FK Indexes**:
  `users`, `password_reset_tokens`, `products`, `product_variants`, `carts`, `cart_items`, `coupons`, `addresses`, `orders`, `order_items`, `payment_events`, `reviews`, `wishlist_items`.
- **Seeded Initial Data (`app/seed/run_seed.py` & `seed_supabase.py`)**:
  - **20 products** (`57` variants) across `beans`, `ground`, `cold_brew`, `equipment`, and `gift_sets`.
  - **2 users**:
    - Customer: `arjun@beanbox.in` / `Coffee@1234` (with 1 default Bengaluru address, 1 delivered order, 1 verified review, 1 wishlist item)
    - Admin: `admin@beanbox.in` / `Admin@1234`
  - **4 coupons**: `WELCOME10`, `FLAT150`, `BREW20`, `EXPIRED50`.

---

## 6. Verification Summary

- **Backend Linter (`ruff check app tests`)**: 0 errors.
- **Backend Automated Tests (`pytest -v`)**: **13/13 passed** (`test_auth.py`, `test_cart.py`, `test_coupons.py`, `test_orders_stock.py`, `test_payments_webhook.py`, `test_products_wishlist_admin.py`).
- **Frontend Checks (`tsc --noEmit`, `next lint`, `next build`)**: 0 type errors, 0 lint errors, **22/22 routes** built cleanly.
- **Live Supabase Integration Verification**: Verified `GET /api/health` (`repositoryBackend: "supabase"`), `GET /api/products` (`20` items), and a full end-to-end checkout flow (guest cart → login merge → `WELCOME10` preview → atomic order reservation → signed mock webhook → GST invoice → cancellation restoring stock → admin stats), plus live browser guest-cart flow confirmation.

---

## 7. Quick Start & Recommended Next Steps

### Run Locally
```bash
# Terminal 1 — FastAPI Backend (port 4000)
cd /Users/ankurmishra/Documents/CODE/COFEEBEAT/backend
.venv/bin/uvicorn app.main:app --reload --port 4000

# Terminal 2 — Next.js Frontend (port 3000)
cd /Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend
npm run dev
```

### Before Deploying to Production
1. Rotate the Supabase database password and `service_role` / secret key in Supabase Project Settings and update `backend/.env`.
2. Add real Stripe test/live keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) if switching out of Mock Payment mode.
3. Replace `ConsoleEmailService` with an SMTP / transactional email provider (e.g., Resend) and swap placeholder SVGs with product photography if desired.
