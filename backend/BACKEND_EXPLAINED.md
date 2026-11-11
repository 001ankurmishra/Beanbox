# BeanBox Backend Explained (Python + FastAPI)

A clear, point-by-point architectural guide to how the **BeanBox** Python + FastAPI backend works—from folder structure and security layers to atomic stock reservations, 5% GST pricing, payment webhook idempotency, and swapping to Supabase later.

---

## 1. Folder Structure & What Each Folder Does

All backend code lives under `backend/`:

- `app/config.py` — Loads and validates environment variables using `pydantic-settings` (`Settings`).
- `app/models/domain.py` — Canonical Pydantic v2 domain models (`CamelModel` base converts `snake_case` Python attributes into `camelCase` HTTP JSON automatically).
- `app/schemas/` — Request/query validation schemas (`auth.py`, `product.py`, `cart.py`, `address.py`, `order.py`, `review.py`, `admin.py`, `common.py`).
- `app/utils/` — Centralized `AppError` exception hierarchy (`errors.py`) and uniform JSON envelope helpers (`response.py`).
- `app/repositories/interfaces/` — Abstract Base Class (`ABC`) storage contracts (`UserRepository`, `ProductRepository`, `CartRepository`, `OrderRepository`, `CouponRepository`, `AddressRepository`, `ReviewRepository`, `WishlistRepository`, `PaymentEventRepository`). Services and routers depend strictly on these interfaces.
- `app/repositories/memory/` — Thread-safe (`threading.RLock`) in-memory implementations seeded with realistic Indian coffee data, deep-copying records (`model_copy(deep=True)`) on reads/writes to isolate state.
- `app/repositories/__init__.py` — The single composition root (`create_in_memory_repositories`) that instantiates the active repository bundle.
- `app/seed/` — Seed dataset (`seed_data.py`: 20 products, 2 users, 4 coupons, sample address, historical delivered order, review, wishlist) and verification CLI (`run_seed.py`).
- `app/services/` — Pure domain business logic: pricing engine, auth, cart merging, atomic checkout, payment providers (Stripe SDK + HMAC mock fallback), mock emails, reviews, wishlist, and admin analytics.
- `app/middleware/` — `SecurityAndLoggingMiddleware` (request ID, security headers, access logging, sliding-window rate limiter) and global exception handlers (`error_handlers.py`).
- `app/dependencies.py` — FastAPI `Depends(...)` providers (`require_auth`, `require_admin`, `get_optional_user`, `get_guest_session_id`, `auth_rate_limit`).
- `app/routers/` — FastAPI routers binding URLs, Pydantic schemas, auth guards, and services.
- `app/main.py` — `create_app()` factory and ASGI `app` entrypoint serving OpenAPI/Swagger at `/api/docs`.
- `tests/` — `pytest` + FastAPI `TestClient` integration suites (`test_auth`, `test_cart`, `test_orders_stock`, `test_coupons`, `test_payments_webhook`, `test_products_wishlist_admin`).

---

## 2. Request Lifecycle

Every API call flows through a consistent pipeline:

1. **CORS & Security Middleware (`app/main.py` + `app/middleware/security.py`)**:
   - `CORSMiddleware` validates `FRONTEND_URL` with `allow_credentials=True`.
   - `SecurityAndLoggingMiddleware` attaches `X-Request-Id`, sets security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`), enforces the general sliding-window rate limit (`240 req/min`), and logs method, path, status, and duration.
2. **Router & Dependencies (`app/dependencies.py`)**:
   - FastAPI resolves `Depends(...)` guards (`auth_rate_limit`, `get_optional_user`, `require_auth`, or `require_admin`).
3. **Pydantic Validation (`app/schemas/`)**:
   - FastAPI automatically parses and validates `Path`, `Query`, and JSON body models before the route function runs; validation errors trigger `validation_error_handler` returning `400 VALIDATION_ERROR`.
4. **Router Handler (Controller Role)**:
   - Extracts validated schema inputs and auth principal, delegates to a service method, and returns `make_success_response(...)`.
5. **Service (`app/services/`)**:
   - Enforces domain rules (5% GST calculation, coupon eligibility, state transitions, ownership checks) and calls repository interfaces.
6. **Repository (`app/repositories/`)**:
   - Executes storage operations (`InMemory*Repository` now, `Supabase*Repository` later) and returns isolated domain models.
7. **Response / Exception Handlers (`app/middleware/error_handlers.py`)**:
   - Successes return `{ "success": true, "data": ... }`; any raised `AppError` or HTTP error is caught and formatted as `{ "success": false, "error": { "code", "message", "details?" }, "requestId" }`.

---

## 3. How Authentication Works (Signup -> Cookie -> Protected Routes -> Role Check)

- **Signup (`POST /api/auth/signup`)**:
  - Checks email uniqueness (`409 EMAIL_ALREADY_EXISTS`).
  - Hashes password with `bcrypt.hashpw(..., bcrypt.gensalt(rounds=10))`.
  - Creates a `customer` user (`role` is hardcoded server-side and never read from the client).
  - Dispatches a welcome email via `ConsoleEmailService`.
  - If a `beanbox_guest_id` cookie is present, merges guest cart items into the new user's cart.
- **JWT in `httpOnly` Cookie**:
  - Signs `{ "sub": user.id, "role": user.role, "exp": ... }` using `PyJWT` (`HS256`, `JWT_SECRET`, 7-day expiry).
  - Sets `beanbox_token` cookie with `httponly=True` (hidden from JS/XSS), `samesite="lax"`, `secure=(APP_ENV == "production")`.
- **Protected Routes (`Depends(require_auth)`)**:
  - Reads `beanbox_token` cookie (or `Authorization: Bearer <token>`), decodes & verifies JWT signature/expiry, and returns `AuthPrincipal(id, role)`. Invalid/missing tokens raise `401 UNAUTHORIZED`.
- **Role Check (`Depends(require_admin)`)**:
  - All `/api/admin/*` endpoints depend on `require_admin`, rejecting non-admin users with `403 FORBIDDEN`.
- **Forgot / Reset Password**:
  - Generates `secrets.token_hex(32)`, stores only its SHA-256 digest (`15 min` expiry) in `UserRepository`, logs the reset link via mock email, and marks the token consumed upon reset.

---

## 4. How Cart Prices Are Calculated (And Why Server-Side)

- Clients only send `{ productId, variantId, quantity }`—never prices or totals.
- On `GET /api/cart`, `POST /api/cart/items`, and `PATCH /api/cart/items/{variantId}`, `CartService.hydrate()` looks up every variant live from `ProductRepository.find_variant_by_id()`.
- Extra client fields (`price`, `unitPricePaise`, `discount`) are ignored by Pydantic schemas (`AddToCartRequest`).
- Why server-side?
  - Prevents client-side payload tampering (e.g., altering ₹499 to ₹1 in browser DevTools).
  - Guarantees live catalog price changes and available stock counts are always reflected accurately.
- **Guest Cart Merging**: Guest shoppers get an `httpOnly` `beanbox_guest_id` cookie on cart mutations. When they call `/api/auth/login` or `/api/auth/signup`, `CartService.merge_guest_cart_into_user()` combines quantities into their user cart (capped at live `variant.stock`) and deletes the temporary guest cart.

---

## 5. How Order Creation Prevents Overselling

1. `OrderService.create_order()` first validates any coupon and atomically claims a slot via `CouponRepository.increment_usage_if_available()`.
2. Next, it calls `ProductRepository.reserve_stock(items)`:
   - Protected by a `threading.RLock()` in `InMemoryProductRepository`.
   - Aggregates quantities per `(product_id, variant_id)` and checks **every** line item against `variant.stock` **before** decrementing any stock.
   - If *any* item lacks sufficient stock, zero variants are decremented, any reserved coupon slot is decremented back, and the API fails cleanly with `409 INSUFFICIENT_STOCK`.
   - When connected to Supabase later, this maps directly to a PostgreSQL RPC transaction (`UPDATE ... WHERE stock >= qty`) to prevent concurrent overselling.
3. Once stock is reserved, the `pending` order is saved and the user's cart is cleared to prevent duplicate checkouts.
4. On payment failure, session expiry, or pre-shipping cancellation, `OrderService.release_order_resources()` restores stock and coupon usage.

---

## 6. Full Payment Flow with Webhook & Idempotency

```text
Customer -> POST /api/orders (pending order created, stock reserved)
         -> POST /api/payments/checkout-session (Stripe or Mock session URL)
         -> Pays on Stripe Checkout (or /checkout/mock-pay in dev)
Gateway  -> POST /api/payments/webhook (raw bytes + signature header)
```

1. **Raw Body Signature Verification (`app/routers/payments.py`)**:
   - Reads exact raw request bytes (`raw_body = await request.body()`).
   - **Stripe mode** (`STRIPE_SECRET_KEY` set): verifies via `stripe.Webhook.construct_event(raw_body, signature, STRIPE_WEBHOOK_SECRET)`.
   - **Mock mode** (default when keys absent): verifies timing-safe HMAC-SHA256 (`x-mock-signature: v1=<hex>`) using `MOCK_WEBHOOK_SECRET`.
   - Invalid signatures raise `400 INVALID_SIGNATURE`.
2. **Idempotency (`PaymentEventRepository`)**:
   - Checks `has_processed_event(event.event_id)` before mutating anything.
   - Replayed webhooks immediately return `200 { "received": true, "duplicate": true }`, preventing double status updates or duplicate confirmation emails.
3. **Outcomes**:
   - `checkout.session.completed` / `payment_intent.succeeded`: verifies amount matches `order.pricing.total_paise`, moves order `pending -> paid`, records the event, and sends order confirmation email.
   - `checkout.session.expired` / `payment_intent.payment_failed`: transitions order `pending -> cancelled`, atomically releases reserved stock and coupon usage, and records the event.

---

## 7. Coupons, Shipping & 5% GST Calculation (Worked Example)

All monetary amounts are stored and computed in **integer paise** (`₹1 = 100 paise`) inside `app/services/pricing_service.py`:

1. **Items Subtotal**: `Σ (variant.price_paise × quantity)`
2. **Coupon Discount**:
   - `percent`: `round_half_up(items_subtotal_paise × value / 100)`, capped at `max_discount_paise`.
   - `flat`: `min(value, items_subtotal_paise)`.
3. **Taxable Amount**: `items_subtotal_paise - discount_paise`
4. **GST (5%)**: `round_half_up(taxable_amount_paise × 0.05)` (split in invoices into `2.5% CGST` + `2.5% SGST`).
5. **Shipping Fee**: `₹0` if `taxable_amount_paise >= ₹999` (`99,900` paise), else `₹79` (`7,900` paise).
6. **Grand Total**: `taxable_amount_paise + gst_paise + shipping_paise`

### Worked Example
Customer orders **2 × 250g Chikmagalur Baba Budangiri Arabica (`₹499` each)** with coupon **`WELCOME10` (10% off, min order ₹499, max discount ₹300)**:

- **Items Subtotal**: `2 × ₹499.00` = **₹998.00** (`99,800` paise)
- **Coupon (`WELCOME10`, 10%)**: `99,800 × 0.10` = **₹99.80** (`9,980` paise)
- **Taxable Amount**: `₹998.00 - ₹99.80` = **₹898.20** (`89,820` paise)
- **GST (5% of ₹898.20)**: `round(89,820 × 0.05)` = **₹44.91** (`4,491` paise; CGST ₹22.45 + SGST ₹22.46)
- **Shipping**: ₹898.20 < ₹999.00 -> **₹79.00** (`7,900` paise)
- **Grand Total**: `₹898.20 + ₹44.91 + ₹79.00` = **₹1,022.11** (`102,211` paise)

*(Adding 1 more bag brings taxable amount above ₹999.00 and drops shipping to **₹0.00**.)*

---

## 8. Order Status State Machine

Enforced in `OrderService` and `AdminService` (`ALLOWED_STATUS_TRANSITIONS`):

```text
pending ──▶ paid ──▶ processing ──▶ shipped ──▶ delivered ──▶ refunded
   │         │           │
   ▼         ▼           ▼
cancelled  cancelled / refunded
```

- **Customer cancellation (`POST /api/orders/{orderId}/cancel`)**: allowed in `pending`, `paid`, or `processing` (releases stock & initiates refund if paid). Rejected with `409 ORDER_NOT_CANCELLABLE` after `shipped`.
- **Admin `shipped` update**: records `shipped_at` and dispatches the `order_shipped` mock email.
- **Terminal states**: `cancelled` and `refunded` cannot transition further.

---

## 9. Error Handling & Security Layers

- **Security Headers**: Every API response sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, and `Content-Security-Policy` (relaxed on `/api/docs` for Swagger UI).
- **CORS**: `allow_origins=[FRONTEND_URL]` with `allow_credentials=True` for `httpOnly` cookie authentication.
- **Rate Limiting**: Thread-safe sliding-window `InMemoryRateLimiter` (`240 req/min` general API; `25 req/15 min` on auth endpoints `/signup`, `/login`, `/forgot-password`, `/reset-password`).
- **Pydantic Validation & Pagination Caps**: Every query, path, and body input is validated; product pagination caps at `limit <= 48`, admin/order pagination at `limit <= 50`.
- **Centralized Error Format**:
  ```json
  {
    "success": false,
    "error": { "code": "ERROR_CODE", "message": "Human readable message", "details": [] },
    "requestId": "uuid"
  }
  ```
- **Zero Client Trust**: Prices, stock checks, GST, discounts, user `role`, and `paymentStatus` are always computed/verified on the server.

---

## 10. Complete API Endpoint Reference

Interactive OpenAPI/Swagger docs are served automatically by FastAPI at `/api/docs` (raw JSON at `/api/docs.json`).

| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | Public | Server & active payment provider status |
| `GET` | `/api/docs` | Public | Swagger UI interactive documentation |
| `GET` | `/api/docs.json` | Public | OpenAPI 3.1 JSON schema |
| `POST` | `/api/auth/signup` | Public | Register customer, set `httpOnly` cookie, merge guest cart |
| `POST` | `/api/auth/login` | Public | Authenticate user, set `httpOnly` cookie, merge guest cart |
| `POST` | `/api/auth/logout` | Public | Clear `beanbox_token` cookie |
| `GET` | `/api/auth/me` | Customer/Admin | Get authenticated user profile |
| `PATCH` | `/api/auth/me` | Customer/Admin | Update profile name or phone |
| `POST` | `/api/auth/forgot-password` | Public | Generate reset token & log mock email |
| `POST` | `/api/auth/reset-password` | Public | Reset password with single-use token |
| `GET` | `/api/products` | Public | Search, filter (`category`, `roast`, `origin`, `minPrice`, `maxPrice`, `inStock`, `featured`), sort, paginate |
| `GET` | `/api/products/{slug}` | Public | Get product details and variants by slug |
| `GET` | `/api/products/{slug}/related` | Public | Get related products |
| `GET` | `/api/products/{slug}/reviews` | Public | List product reviews and rating distribution |
| `POST` | `/api/products/{slug}/reviews` | Customer/Admin | Create 1–5★ review (verified buyers only, 1 per product) |
| `DELETE` | `/api/reviews/{reviewId}` | Owner/Admin | Delete review and recalculate rating stats |
| `GET` | `/api/cart` | Guest/Customer | Get cart with server-calculated GST & shipping |
| `POST` | `/api/cart/items` | Guest/Customer | Add variant to cart (sets `beanbox_guest_id` cookie for guests) |
| `PATCH` | `/api/cart/items/{variantId}` | Guest/Customer | Update item quantity (`0` removes) |
| `DELETE` | `/api/cart/items/{variantId}` | Guest/Customer | Remove variant from cart |
| `DELETE` | `/api/cart` | Guest/Customer | Clear cart |
| `GET` | `/api/addresses` | Customer/Admin | List user addresses |
| `POST` | `/api/addresses` | Customer/Admin | Create Indian address (10-digit mobile, 6-digit PIN) |
| `PATCH` | `/api/addresses/{addressId}` | Customer/Admin | Update address |
| `DELETE` | `/api/addresses/{addressId}` | Customer/Admin | Delete address (auto-promotes next default) |
| `PATCH` | `/api/addresses/{addressId}/default` | Customer/Admin | Set default shipping address |
| `POST` | `/api/checkout/preview` | Customer/Admin | Preview coupon discount, 5% GST, shipping & total |
| `POST` | `/api/orders` | Customer/Admin | Create `pending` order with atomic stock & coupon reservation |
| `GET` | `/api/orders` | Customer/Admin | Paginated customer order history |
| `GET` | `/api/orders/{orderId}` | Owner/Admin | Get order details |
| `POST` | `/api/orders/{orderId}/cancel` | Owner | Cancel order before shipping & release stock |
| `GET` | `/api/orders/{orderId}/invoice` | Owner/Admin | Get GST tax invoice JSON (`CGST`/`SGST`/`HSN 0901`) |
| `POST` | `/api/payments/checkout-session` | Owner | Create Stripe or Mock checkout session |
| `POST` | `/api/payments/webhook` | Signed Webhook | Verify raw signature, enforce idempotency, update order/stock |
| `POST` | `/api/payments/mock/trigger` | Owner | Trigger signed mock payment outcome (`success`/`failed`/`expired`) |
| `GET` | `/api/wishlist` | Customer/Admin | List wishlist products |
| `POST` | `/api/wishlist/{productId}` | Customer/Admin | Add product to wishlist |
| `DELETE` | `/api/wishlist/{productId}` | Customer/Admin | Remove product from wishlist |
| `GET` | `/api/admin/stats` | Admin | Dashboard revenue, orders, top products, low stock |
| `GET` | `/api/admin/products` | Admin | List all products (including inactive) |
| `POST` | `/api/admin/products` | Admin | Create product & variants |
| `PATCH` | `/api/admin/products/{productId}` | Admin | Update product |
| `DELETE` | `/api/admin/products/{productId}` | Admin | Delete product |
| `PATCH` | `/api/admin/inventory/{productId}/{variantId}` | Admin | Update variant stock or price |
| `GET` | `/api/admin/orders` | Admin | List all orders with status filter |
| `PATCH` | `/api/admin/orders/{orderId}/status` | Admin | Transition order status along state machine |
| `GET` | `/api/admin/coupons` | Admin | List promo coupons |
| `POST` | `/api/admin/coupons` | Admin | Create promo coupon |
| `PATCH` | `/api/admin/coupons/{couponId}` | Admin | Update coupon |
| `DELETE` | `/api/admin/coupons/{couponId}` | Admin | Delete coupon |
| `GET` | `/api/admin/users` | Admin | List users with order counts |

---

## 11. Supabase PostgreSQL Integration

Because every service and router depends strictly on ABC interfaces in `app/repositories/interfaces/`, connecting Supabase required **zero** edits to routers, schemas, or services:

1. **Dependencies & Config**:
   - `backend/pyproject.toml` & `backend/requirements.txt` — `psycopg[binary]` and `psycopg-pool`.
   - `backend/.env` & `backend/app/config.py` — `REPOSITORY_BACKEND`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `DATABASE_URL`.
2. **Schema (`backend/supabase/schema.sql`)**:
   - Creates 13 normalized tables (`users`, `password_reset_tokens`, `products`, `product_variants`, `carts`, `cart_items`, `coupons`, `addresses`, `orders`, `order_items`, `payment_events`, `reviews`, `wishlist_items`) with foreign-key indexes and RLS enabled on every table.
3. **Supabase Repository Implementations (`backend/app/repositories/supabase/`)**:
   - `db.py` (`ConnectionPool` with `prepare_threshold=None` for PgBouncer compatibility)
   - `user_repository.py` (`SupabaseUserRepository`)
   - `product_repository.py` (`SupabaseProductRepository` using deadlock-safe `ORDER BY pv.id FOR UPDATE` transactions for atomic `reserve_stock`)
   - `cart_repository.py` (`SupabaseCartRepository`)
   - `coupon_repository.py` (`SupabaseCouponRepository` using atomic conditional `UPDATE ... WHERE used_count < usage_limit`)
   - `address_repository.py` (`SupabaseAddressRepository`)
   - `order_repository.py` (`SupabaseOrderRepository`)
   - `review_repository.py` (`SupabaseReviewRepository`)
   - `wishlist_repository.py` (`SupabaseWishlistRepository`)
   - `payment_event_repository.py` (`SupabasePaymentEventRepository`)
4. **Composition Root (`backend/app/repositories/__init__.py` & `backend/app/main.py`)**:
   - Automatically uses `create_supabase_repositories(settings.database_url)` when `DATABASE_URL` is configured (`APP_ENV != "test"`), while keeping unit tests fast and isolated on `InMemory*` repositories.
