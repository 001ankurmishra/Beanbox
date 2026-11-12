# BeanBox Authorization & Security Architecture (`AUTHZ_EXPLAINED.md`)

> Comprehensive guide to authentication, Role-Based Access Control (RBAC), Insecure Direct Object Reference (IDOR) prevention, session grace windows, security notifications, and every protected API endpoint in BeanBox.

---

## 1. Access Control Model & Trust Boundaries

BeanBox enforces defense-in-depth authorization across four layers:

1. **HTTP Security & CSRF Middleware** (`backend/app/middleware/security.py`)
   - Validates `Origin` / `Referer` and double-submit `X-CSRF-Token` vs `beanbox_csrf` on all cookie-authenticated unsafe requests (`POST`, `PATCH`, `PUT`, `DELETE`), exempting only signed payment webhooks (`/api/payments/webhook`), login, signup, and pre-auth password reset endpoints.
2. **Router Auth & Role Dependencies** (`backend/app/dependencies.py`)
   - `get_optional_user`: returns `AuthPrincipal | None` for anonymous-capable cart endpoints.
   - `require_user` (aliased `require_auth`): verifies HS256 JWT (`typ="access"`), checks that the backing session in `sessions` exists, belongs to `claims.user_id`, is not revoked (`revoked_at IS NULL`), and is not expired, then loads the user from `users`.
   - `require_verified`: composes `require_user` and rejects unverified emails with `403 EMAIL_NOT_VERIFIED`.
   - `require_admin` (`require_role("admin")`): composes `require_user`, **always re-queries `users` from the repository** (never trusting JWT `role` claims alone), rejects non-admins with `403`, and enforces `totp_enabled == True` (`403 ADMIN_2FA_REQUIRED`) for every `/api/admin/*` call.
3. **Service & Repository Ownership Scoping** (`backend/app/services/*`, `backend/app/repositories/*`)
   - User-owned lookups and mutations query by **both resource ID and caller `user_id`** directly in the repository layer (`find_by_id_for_user`, `delete_for_user`, `revoke_by_id`, `remove`), and services treat any missing or cross-user match uniformly as **`404 NotFoundError`**.
4. **PostgreSQL Row-Level Security (RLS)** (`backend/supabase/schema.sql`, `002_production_auth.sql`)
   - All 20 Supabase tables have `ENABLE ROW LEVEL SECURITY` with zero permissive `anon`/`authenticated` Data API policies, ensuring direct browser/Supabase API keys cannot bypass FastAPI.

---

## 2. Permission Matrix (Role × Resource × Action)

| Resource | Action | Guest | Unverified Customer | Verified Customer | Admin (2FA Active) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Products (Catalog)** | List / view / search active products | Allow | Allow | Allow | Allow |
| **Products (Catalog)** | Create / update / delete / manage inventory | Deny (401) | Deny (403) | Deny (403) | Allow |
| **Cart** | View / add / update / remove / clear own cart | Allow (`session_id` cookie) | Allow (`user_id`) | Allow (`user_id`) | Allow (`user_id`) |
| **Wishlist** | List / add / remove own wishlist items | Deny (401) | Allow (own) | Allow (own) | Allow (own) |
| **Addresses** | List / create / update / delete / set default | Deny (401) | Allow (own only; 404 others) | Allow (own only; 404 others) | Allow (own only; 404 others) |
| **Checkout Preview** | Preview cart pricing + optional own address | Deny (401) | Allow (own address; 404 others) | Allow (own address; 404 others) | Allow (own address; 404 others) |
| **Orders** | Place order (`POST /api/orders`) | Deny (401) | Deny (`403 EMAIL_NOT_VERIFIED`) | Allow (own address; 404 others) | Allow (own address; 404 others) |
| **Orders** | List own orders | Deny (401) | Allow (own) | Allow (own) | Allow (own) |
| **Orders** | View order / download GST invoice | Deny (401) | Own only (404 others) | Own only (404 others) | Any order |
| **Orders** | Customer cancel (`pending`/`paid`/`processing`) | Deny (401) | Own only (404 others) | Own only (404 others) | Own only (404 others) |
| **Orders (Admin)** | List all orders / update order status | Deny (401) | Deny (403) | Deny (403) | Allow |
| **Payments** | Create checkout session (`POST /api/payments/checkout-session`) | Deny (401) | Deny (`403 EMAIL_NOT_VERIFIED`) | Own pending order only (404 others) | Own pending order only (404 others) |
| **Payments** | Trigger mock payment outcome (test/dev mock mode) | Deny (401) | Own order only (404 others) | Own order only (404 others) | Own order only (404 others) |
| **Payments Webhook** | Signed provider webhook (`POST /api/payments/webhook`) | Signed HMAC / Stripe sig only (400/401 on invalid) | Same | Same | Same |
| **Reviews** | Read reviews for active products | Allow | Allow | Allow | Allow |
| **Reviews** | Create review (`POST /api/products/{slug}/reviews`) | Deny (401) | Verified buyer of product only (`403 VERIFIED_PURCHASE_REQUIRED`) | Verified buyer only (`403`) | Verified buyer only (`403`) |
| **Reviews** | Delete review (`DELETE /api/reviews/{review_id}`) | Deny (401) | Author only (404 others) | Author only (404 others) | Any review |
| **Profile & Password** | View / update `name` & `phone` / change password / verify email | Deny (401) | Allow (own; no email-change endpoint) | Allow (own) | Allow (own) |
| **Sessions & 2FA** | List / revoke own sessions / logout all / setup & toggle 2FA | Deny (401) | Allow (own sessions; 404 others) | Allow (own sessions; 404 others) | Allow (cannot disable 2FA: `403 ADMIN_2FA_REQUIRED`) |
| **Coupons (Admin)** | List / create / update / delete coupons | Deny (401) | Deny (403) | Deny (403) | Allow |
| **Users & Roles (Admin)** | List all users / change other users' roles | Deny (401) | Deny (403) | Deny (403) | Allow (cannot modify own role: `400 CANNOT_CHANGE_OWN_ROLE`) |
| **Security Audit Logs** | Query system audit trail (`GET /api/admin/audit-logs`) | Deny (401) | Deny (403) | Deny (403) | Allow |

> **Admin 2FA Gate**: If a user holds `role = "admin"` in `users` but has `totp_enabled = False`, `require_admin` denies access to all `/api/admin/*` endpoints with `403 ADMIN_2FA_REQUIRED` until TOTP enrollment completes.

---

## 3. What IDOR Is and How BeanBox Prevents It

### What is IDOR?
**Insecure Direct Object Reference (IDOR)** occurs when an API accepts a client-supplied identifier (such as `orderId`, `addressId`, `reviewId`, `sessionId`, `variantId`, or `productId`) and fetches/mutates the backing record directly by ID without verifying that the authenticated caller owns that object. An attacker can enumerate or guess UUIDs/IDs to read another customer's GST invoice (shipping address & phone), cancel their order, pay on or tamper with their checkout, delete their saved addresses/reviews/wishlist items, or kill their sessions.

### Why BeanBox Returns `404` Instead of `403`
Returning `403 Forbidden` when another user's resource exists vs. `404 Not Found` when it doesn't creates an **existence oracle** — attackers can probe IDs to learn which UUIDs exist in the database. Across all user-owned resources, BeanBox queries repositories scoped by `(resource_id, principal.id)` and raises `404 Not Found` when no matching row exists for that user.

### Where IDOR Is Prevented (Service + Repository Layers)
1. **Orders & Invoices** (`OrderService` + `OrderRepository`):
   - `OrderRepository.find_by_id_for_user(order_id, user_id)` queries `WHERE id = %s AND user_id = %s` (Supabase) and `o.id == order_id and o.user_id == user_id` (InMemory).
   - `OrderService.get_order_for_user`, `cancel_order`, `get_invoice`, and `create_payment_session` all enforce `find_by_id_for_user` + `order.user_id != user_id` (unless `is_admin=True` on read/invoice) and raise `NotFoundError("Order not found")` (`404`).
2. **Checkout & Shipping Addresses** (`AddressService` + `AddressRepository` + `OrderService`):
   - `AddressRepository.find_by_id_for_user(address_id, user_id)` is used by `OrderService.preview_checkout` and `OrderService.create_order` so User A cannot preview or place an order shipping to User B's `addressId` (`404`).
   - `AddressRepository.update`, `delete`, and `set_default` all scope queries with `WHERE id = %s AND user_id = %s` and return `404` when absent or owned by someone else.
3. **Reviews** (`ReviewService` + `ReviewRepository`):
   - Non-admin deletes call `ReviewRepository.find_by_id_for_user(review_id, user_id)` and `ReviewRepository.delete_for_user(review_id, user_id)` (`WHERE id = %s AND user_id = %s`), returning `404 NotFoundError("Review not found")` for another user's review. Admin moderation continues to work via `is_admin=True`.
4. **Wishlist** (`WishlistService` + `WishlistRepository`):
   - `WishlistRepository.remove(user_id, product_id)` deletes strictly `WHERE user_id = %s AND product_id = %s` and returns `bool`. `WishlistService.remove` checks that boolean and raises `404 NotFoundError("Wishlist item not found")` instead of silently returning `200`.
5. **Cart** (`CartService` + `cart` router):
   - Every cart read/write derives a server-side `CartOwner(user_id=...)` from `require_user` / verified principal (never trusting a request body owner ID). Both `update_item_quantity` and `remove_item` verify the `variant_id` belongs to the caller's cart and raise `404 NotFoundError("Cart item not found")` otherwise. `DELETE /api/cart/items/{variant_id}` never allocates a new guest cookie when no cart exists.
6. **Sessions** (`AuthService` + `SessionRepository`):
   - `SessionRepository.revoke_by_id(session_id, user_id)` filters `WHERE id = %s AND user_id = %s`; `AuthService.revoke_session` raises `404 NotFoundError("Session not found")` if another user's session ID is supplied.

---

## 4. Additional Authorization Hardening Controls

- **Mass Assignment Protection**: All request schemas inherit `CamelModel` (`extra="ignore"` by default in Pydantic v2) with explicit field allowlists (`SignupRequest`, `UpdateProfileRequest`, `CreateAddressRequest`, `CreateOrderRequest`, `CreateReviewRequest`, `AddToCartRequest`). Services construct explicit repository input dataclasses and overwrite `user_id`, `role`, `status`, `payment_status`, `pricing`, and `verified_purchase` server-side.
- **No Email-Change Endpoint**: `UpdateProfileRequest` exposes only `name` and `phone`. Account email addresses are immutable post-signup (verified against `email_verification_tokens` or verified Google OAuth `id_token` claims).
- **Demoted Admin Immediate Rejection**:
  1. `AdminService.update_user_role` atomically calls `session_repo.revoke_all_for_user(target_user_id)` upon any role change, immediately invalidating existing access JWTs and refresh tokens (`401 SESSION_REVOKED`).
  2. Even if an access JWT still has a `"role": "admin"` claim before expiry, `require_role("admin")` in `dependencies.py` re-reads `db_user = users.find_by_id(principal.id)` on every request and rejects with `403`.
- **10-Second Refresh Token Grace Window (`REFRESH_GRACE_SECONDS=10`)**:
  - When a refresh token `R0` rotates to `R1`, `sessions.grace_refresh_hash` records `hash(R0)` with `grace_expires_at = now + 10s` (`003_refresh_grace.sql`).
  - If a second concurrent browser tab submits `R0` within 10 seconds (sequentially or in a parallel CAS race inside `rotate_refresh_token`), `AuthService.refresh_session` issues a fresh access JWT (`refresh_grace_hit` audit event) without invalidating `R1` or revoking the family.
  - Only the **immediately previous** token gets the grace window: once `R1 -> R2` happens (`grace_refresh_hash` becomes `hash(R1)`), replaying `R0` immediately revokes the family (`401 REFRESH_TOKEN_REUSE_DETECTED`), and replaying `R0` after the 10-second `grace_expires_at` passes also revokes the family.
- **Security Notification Emails** (`EmailService` / `ConsoleEmailService`):
  - Sent (`type="security_notification"`) with request IP & `User-Agent` (never logging tokens or passwords) on:
    - Password changed (`change_password` and `reset_password`)
    - 2FA enabled or disabled (`enable_2fa` and `disable_2fa`)
    - Login from an unrecognized device (`_issue_session` checking `SessionRepository.check_device_history` when prior sessions exist and the current `User-Agent` has never been seen for that user).

---

## 5. Complete Table of Protected Routes

### A. User-Authenticated & Resource-Scoped Routes

| Method | Path | Auth / Role Guard | Ownership & Repository Check | Cross-User / Failure Status |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/logout-all` | `require_user` | Revokes all sessions for `principal.id` | `401` if unauthenticated |
| `GET` | `/api/auth/me` | `require_user` | Reads user for `principal.id` | `401` if unauthenticated/revoked |
| `PATCH` | `/api/auth/me` | `require_user` | Updates only `name` & `phone` for `principal.id` | `401` unauthenticated; extra fields ignored |
| `POST` | `/api/auth/change-password` | `require_user` | Verifies current password for `principal.id`, revokes other sessions, sends alert email | `401` bad password |
| `POST` | `/api/auth/verify-email/resend` | `require_user` | Issues verification token for `principal.id` (60s cooldown + rate limit) | `429` on cooldown |
| `GET` | `/api/auth/sessions` | `require_user` | `SessionRepository.list_active_for_user(principal.id)` | `401` |
| `DELETE` | `/api/auth/sessions/{session_id}` | `require_user` | `SessionRepository.revoke_by_id(session_id, principal.id)` (`WHERE id=%s AND user_id=%s`) | **`404`** for another user's session |
| `GET` | `/api/auth/2fa/status` | `require_user` | Reads 2FA state for `principal.id` | `401` |
| `POST` | `/api/auth/2fa/setup` | `require_user` | Generates encrypted TOTP secret for `principal.id` | `409` if already enabled |
| `POST` | `/api/auth/2fa/enable` | `require_user` | Verifies TOTP code, enables 2FA for `principal.id`, sends alert email | `400` bad code |
| `POST` | `/api/auth/2fa/recovery-codes/regenerate` | `require_user` | Verifies TOTP code, replaces recovery codes for `principal.id` | `401` bad code |
| `POST` | `/api/auth/2fa/disable` | `require_user` | Verifies TOTP/recovery + password; blocks admins; sends alert email | `403 ADMIN_2FA_REQUIRED` for admin |
| `POST` | `/api/products/{slug}/reviews` | `require_auth` | `OrderRepository.has_verified_purchase(principal.id, product.id)` | `403 VERIFIED_PURCHASE_REQUIRED` |
| `DELETE` | `/api/reviews/{review_id}` | `require_auth` | `ReviewRepository.find_by_id_for_user` + `delete_for_user` (or any if `admin`) | **`404`** for non-admin on others' review |
| `GET` | `/api/cart` | `get_optional_user` | Scoped to `CartOwner(user_id=principal.id)` or guest `beanbox_guest_id` cookie | Separate carts per owner |
| `POST` | `/api/cart/items` | `get_optional_user` | Adds catalog variant to caller's `CartOwner` cart with server pricing | `404` invalid variant / `409` stock |
| `PATCH` | `/api/cart/items/{variant_id}` | `get_optional_user` | Updates item only inside caller's `CartOwner` cart | **`404`** if not in caller's cart |
| `DELETE` | `/api/cart/items/{variant_id}` | `get_optional_user` | Deletes item only inside caller's `CartOwner` cart | **`404`** if not in caller's cart |
| `DELETE` | `/api/cart` | `get_optional_user` | Clears only caller's `CartOwner` cart | — |
| `GET` | `/api/wishlist` | `require_auth` | Lists items for `principal.id` | `401` |
| `POST` | `/api/wishlist/{product_id}` | `require_auth` | Verifies active catalog product, adds for `principal.id` | `404` product missing |
| `DELETE` | `/api/wishlist/{product_id}` | `require_auth` | `WishlistRepository.remove(principal.id, product_id)` (`WHERE user_id=%s AND product_id=%s`) | **`404`** if not in caller's wishlist |
| `GET` | `/api/addresses` | `require_auth` | `AddressRepository.list_by_user_id(principal.id)` | `401` |
| `POST` | `/api/addresses` | `require_auth` | Creates address assigned to `principal.id` (ignores body `userId`) | `401` |
| `PATCH` | `/api/addresses/{address_id}` | `require_auth` | `AddressRepository.update(address_id, principal.id, ...)` (`WHERE id=%s AND user_id=%s`) | **`404`** for another user's address |
| `DELETE` | `/api/addresses/{address_id}` | `require_auth` | `AddressRepository.delete(address_id, principal.id)` (`WHERE id=%s AND user_id=%s`) | **`404`** for another user's address |
| `PATCH` | `/api/addresses/{address_id}/default` | `require_auth` | `AddressRepository.set_default(address_id, principal.id)` (`WHERE id=%s AND user_id=%s`) | **`404`** for another user's address |
| `POST` | `/api/checkout/preview` | `require_auth` | Optional `addressId` checked via `AddressRepository.find_by_id_for_user(..., principal.id)` | **`404`** for another user's address |
| `POST` | `/api/orders` | `require_verified` | Requires verified email; `addressId` via `AddressRepository.find_by_id_for_user` | `403 EMAIL_NOT_VERIFIED`; **`404`** others' address |
| `GET` | `/api/orders` | `require_auth` | `OrderRepository.list_by_user_id(principal.id, ...)` | `401` |
| `GET` | `/api/orders/{order_id}` | `require_auth` | `OrderRepository.find_by_id_for_user(order_id, principal.id)` (or any if `admin`) | **`404`** for non-admin on others' order |
| `POST` | `/api/orders/{order_id}/cancel` | `require_auth` | `get_order_for_user(..., is_admin=False)` -> `find_by_id_for_user(order_id, principal.id)` | **`404`** for another user's order |
| `GET` | `/api/orders/{order_id}/invoice` | `require_auth` | `get_order_for_user(..., is_admin=(role=="admin"))` -> `find_by_id_for_user` | **`404`** for non-admin on others' invoice |
| `POST` | `/api/payments/checkout-session` | `require_verified` | `OrderRepository.find_by_id_for_user(order_id, principal.id)` | `403 EMAIL_NOT_VERIFIED`; **`404`** others' order |
| `POST` | `/api/payments/mock/trigger` | `require_auth` | `get_order_for_user(order_id, principal.id, is_admin=False)` (plus mock-mode check) | **`404`** for another user's order |

### B. Admin-Protected Routes (All Under `router.dependencies = [Depends(require_admin)]`)

| Method | Path | Auth / Role Guard | Enforcement Details |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/admin/stats` | `require_admin` (`role=="admin"` in DB + `totp_enabled`) | Dashboard revenue, orders, stock, customers (`403` for customers) |
| `GET` | `/api/admin/products` | `require_admin` | Lists active + inactive products |
| `POST` | `/api/admin/products` | `require_admin` | Creates product & variants |
| `PATCH` | `/api/admin/products/{product_id}` | `require_admin` | Updates catalog product (`404` if missing) |
| `DELETE` | `/api/admin/products/{product_id}` | `require_admin` | Deletes catalog product (`404` if missing) |
| `PATCH` | `/api/admin/inventory/{product_id}/{variant_id}` | `require_admin` | Updates stock / price for variant |
| `GET` | `/api/admin/orders` | `require_admin` | Lists all store orders |
| `PATCH` | `/api/admin/orders/{order_id}/status` | `require_admin` | Enforces valid state transitions (`409` invalid transition) |
| `GET` | `/api/admin/coupons` | `require_admin` | Lists coupons |
| `POST` | `/api/admin/coupons` | `require_admin` | Creates coupon |
| `PATCH` | `/api/admin/coupons/{coupon_id}` | `require_admin` | Updates coupon |
| `DELETE` | `/api/admin/coupons/{coupon_id}` | `require_admin` | Deletes coupon |
| `GET` | `/api/admin/users` | `require_admin` | Lists all users + order counts |
| `PATCH` | `/api/admin/users/{user_id}/role` | `require_admin` (double-bound) | Changes another user's role & revokes all target sessions (`400` on self) |
| `GET` | `/api/admin/audit-logs` | `require_admin` | Paginated security audit log feed |

### C. Public / Token-Gated Auth & Catalog Routes (Non-IDOR Endpoints)

- `GET /api/health`, `GET /api/products`, `GET /api/products/{slug}`, `GET /api/products/{slug}/related`, `GET /api/products/{slug}/reviews`: Public read-only catalog/health endpoints (returns only `is_active` products).
- `GET /api/auth/csrf`, `GET /api/auth/providers`, `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `POST /api/auth/verify-email`, `POST /api/auth/forgot-password`, `POST /api/auth/reset-password`, `POST /api/auth/2fa/verify-login`, `GET /api/auth/google/start`, `GET /api/auth/google/callback`: Rate-limited pre-auth / token-bearing endpoints (`refresh` cookie, SHA-256 verification/reset tokens, PKCE sealed cookie `beanbox_oauth_tx`, short-lived single-use `2fa_challenge` JWT).
- `POST /api/payments/webhook`: Verifies HMAC-SHA256 (`x-mock-signature`) or Stripe webhook signature (`stripe-signature`) with idempotent `payment_events` tracking.
