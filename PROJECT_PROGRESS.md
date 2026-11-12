# BeanBox — Complete Architecture, Security & Review Guide

Comprehensive technical reference for **BeanBox** (India-based specialty coffee e-commerce store using `INR (₹)` integer paise, `5% GST`, free shipping at `₹999+`, repository abstraction, Next.js 14 storefront, and production-grade authentication).

This document is structured so you—or any AI/human code reviewer (e.g., Claude)—can understand **every layer built**, **where every security invariant lives**, and **what has vs. hasn't been verified live**.

---

## 1. Timeline & Current Completion Status

| Phase | Scope | Status |
| :--- | :--- | :--- |
| **Phase 1 — E-Commerce Backend** | FastAPI + Pydantic v2 (`CamelModel`), 9 domain repositories, pricing/GST engine, atomic stock & coupon reservations, Stripe + Mock webhook payments | **Done & Verified** |
| **Phase 2 — Frontend Storefront & Consoles** | Next.js 14 (App Router), TypeScript, Tailwind CSS, storefront, bag/checkout, account portal, roastery admin console, local SVG art | **Done & Verified** |
| **Phase 3 — Live Supabase PostgreSQL** | Initial 13 RLS-enabled tables, `psycopg_pool` PgBouncer-safe repos, idempotent seed (`20` products / `57` variants, `4` coupons, demo customer & admin) | **Done & Connected** |
| **Phase 4 — Production-Grade Auth & Security** | 15m JWT + 30d rotating opaque refresh cookies w/ family reuse detection, Argon2id + transparent bcrypt rehash, CSRF double-submit + `Origin` check, brute-force exponential lockout, email verification checkout gate, TOTP 2FA (AES-256-GCM at rest + 10 recovery codes, mandatory for admins), Google OAuth 2.0 + PKCE (`S256`) + `nonce`, DB-checked RBAC, audit logs, strict rate limits, single-flight frontend refresh | **Done & Verified Live** |
| **Phase 5 — Authorization, IDOR Hardening & Alerts** | Service + repository `user_id` ownership scoping returning `404` (not `403`) on cross-user orders/invoices/payments/addresses/reviews/wishlist/cart/sessions, 10s concurrent-tab refresh grace window (`003_refresh_grace.sql`), security notification emails (password change, 2FA toggle, new-device login), [AUTHZ_EXPLAINED.md](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/AUTHZ_EXPLAINED.md), `test_authorization.py` | **Done & Verified** |

---

## 2. Tech Stack & Core Design Invariants

- **Backend (`backend/`)**: Python 3.13, FastAPI, Pydantic v2 (`CamelModel` converts internal `snake_case` Python fields to `camelCase` JSON), `PyJWT[crypto]`, `argon2-cffi`, `bcrypt` (legacy verification + upgrade only), `pyotp`, `qrcode`, `cryptography` (`AESGCM` + `HKDF`), `httpx`, `psycopg[binary]` + `psycopg-pool`, `stripe`, `pytest`, `ruff`.
- **Frontend (`frontend/`)**: Next.js 14 (`14.2.x`, App Router), React 18, TypeScript, Tailwind CSS, `lucide-react`.
- **Database**: Supabase PostgreSQL (`20` tables in `public`, **all 20 with RLS enabled**, **0 missing FK indexes**).
- **Monetary Precision**: All prices, discounts, GST (`5%` split `2.5% CGST + 2.5% SGST`), and totals use **integer paise** (`₹1 = 100 paise`). See [pricing_service.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/services/pricing_service.py).

---

## 3. Repository Architecture (`14` Interfaces × `memory` & `supabase`)

Services and routers depend strictly on Abstract Base Classes inside [backend/app/repositories/interfaces/](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/repositories/interfaces/__init__.py):

- **Core Commerce**: `UserRepository`, `ProductRepository` (sorted `SELECT ... FOR UPDATE` stock reservation), `CartRepository`, `CouponRepository` (atomic `used_count < usage_limit` increment), `AddressRepository`, `OrderRepository`, `ReviewRepository`, `WishlistRepository`, `PaymentEventRepository`.
- **Auth & Security**: `SessionRepository`, `OAuthAccountRepository`, `TwoFactorRepository`, `LoginAttemptRepository`, `AuditLogRepository`.
- **Implementations**:
  - `backend/app/repositories/memory/`: Thread-safe (`RLock`) in-memory repositories used automatically when `APP_ENV=test` or `REPOSITORY_BACKEND=memory`.
  - `backend/app/repositories/supabase/`: Live Postgres implementations backed by `psycopg_pool.ConnectionPool` (`prepare_threshold=None` in [db.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/repositories/supabase/db.py) for Supabase transaction/session pooler compatibility).
- **Wiring**: [backend/app/repositories/__init__.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/repositories/__init__.py) and [`create_app`](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/main.py).

---

## 4. Production Auth & Security Map (For Code Review)

Detailed ASCII diagrams and endpoint matrices live in [AUTH_EXPLAINED.md](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/AUTH_EXPLAINED.md). Here is the exact code map to inspect:

### A. Cryptographic Primitives & Password Policy — [backend/app/utils/security.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/utils/security.py)
- **Password hashing**: `Argon2id` (`time_cost=3`, `memory_cost=65536` / 64 MiB, `parallelism=4`).
- **Transparent bcrypt migration**: On login, `$2a$`/`$2b$`/`$2y$` bcrypt hashes verify cleanly and immediately rehash to `$argon2id$` in DB (`verify_password_constant_time`).
- **Timing attack protection**: Missing accounts, locked accounts, and OAuth-only (`!oauth-only`) placeholders execute `dummy_password_work()` using Argon2id so failures take uniform time.
- **Policy (`validate_password_policy`)**: Min 10 characters (`max 128`), rejects curated common passwords, rejects passwords containing the user's normalized email.
- **Secrets encryption at rest**: `encrypt_secret` / `decrypt_secret` use `AES-256-GCM` with keys derived via `HKDF-SHA256` from `TOTP_ENCRYPTION_KEY` (falling back to HKDF from `JWT_SECRET` in dev/test). Format: `v1:<urlsafe_b64(12B_nonce + ciphertext_and_tag)>`.
- **Tokens & backup codes**: Opaque tokens via `secrets.token_urlsafe(32)`; hashed at rest via SHA-256 (sessions/verify/reset) or HMAC-SHA256 keyed with `JWT_SECRET` (recovery codes).

### B. Cookies, Sessions, Refresh Rotation & Reuse Detection — [auth_service.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/services/auth_service.py), [auth.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/routers/auth.py)
- **`beanbox_access`**: 15-min HS256 JWT (`sub`, `role`, `sid`, `jti`, `iat`, `exp`, `typ="access"`), `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` in production/HTTPS.
- **`beanbox_refresh`**: 30-day 256-bit random opaque string, `HttpOnly`, `SameSite=Lax`, **`Path=/api/auth`**, `Secure` in production/HTTPS. Only `sha256` stored in `sessions`.
- **Atomic Rotation, 10s Grace Window & Replay Detection**: `rotate_refresh_token()` in [`SupabaseSessionRepository`](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/repositories/supabase/session_repository.py) atomically appends the spent hash to `previous_refresh_hashes` (`GIN`-indexed), stores `grace_refresh_hash` + `grace_expires_at` (`REFRESH_GRACE_SECONDS=10` via [003_refresh_grace.sql](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/supabase/migrations/003_refresh_grace.sql)), and sets the new `refresh_token_hash` only if `revoked_at IS NULL`. Concurrent tab refreshes of the immediately previous token within 10s issue a fresh access JWT (`refresh_grace_hit`) without overwriting the rotated cookie or revoking the family; replay after 10s or after a subsequent rotation triggers `revoke_family(family_id)` + `refresh_reuse_detected` audit log + `401 REFRESH_TOKEN_REUSE_DETECTED`.
- **Sessions endpoints**: `GET /api/auth/sessions`, `DELETE /api/auth/sessions/{session_id}`, `POST /api/auth/logout`, `POST /api/auth/logout-all`.

### C. CSRF, Security Headers & Rate Limits — [middleware/security.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/middleware/security.py), [dependencies.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/dependencies.py), [main.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/main.py)
- **CSRF (`_validate_cookie_csrf`)**: Runs on all `/api/*` state-changing requests (`POST`/`PUT`/`PATCH`/`DELETE`) carrying `beanbox_access` or `beanbox_refresh` (unless using `Bearer` auth or HMAC-signed `/api/payments/webhook`). Enforces **both**:
  1. `beanbox_csrf` cookie equals `X-CSRF-Token` header via `secrets.compare_digest`.
  2. Strict `Origin` (or fallback `Referer`) matches configured `FRONTEND_URL` (rejecting `"null"` or missing both headers).
- **Per-endpoint sliding-window rate limiters**: `login` (`15/15m`), `signup` (`5/15m`), `reset` (`5/15m`), `verify_resend` (`3/15m`), `refresh` (`30/15m`), `2fa` (`10/15m`), plus global API limiter (`240/60s`).
- **Safe logging**: Request logs omit URL query strings (`?token=`, `?code=`), headers, and bodies; `AuditService` scrubs keys like `password`, `token`, `secret`, `code`, `code_verifier`.

### D. Brute-Force, Email Verification, Reset, 2FA, OAuth PKCE & RBAC
- **Brute-force (`login_attempts`)**: Tracks both `acct:<email>` and `ip:<ip>` even when the email does not exist (zero enumeration). Locks after `5` failures for `15m` with exponential backoff (`15m → 30m → 60m...`) and generic `"Invalid credentials"` error.
- **Email verification (`email_verification_tokens`)**: 24h single-use hashed token on signup; `60s` resend cooldown (`POST /api/auth/verify-email/resend`). Unverified users can browse/cart/preview; `POST /api/orders` ([orders.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/routers/orders.py)) and `POST /api/payments/checkout-session` ([payments.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/routers/payments.py)) require `require_verified`.
- **Password reset**: Identical response whether email exists or not; 15m single-use hashed token; enforces password policy; revokes all user sessions; resets account lock.
- **TOTP 2FA (`totp_secrets`, `recovery_codes`)**: `POST /api/auth/2fa/setup` returns manual Base32 secret + SVG QR data URI; `enable` returns 10 single-use recovery codes once; login returns a 5-min single-use `challengeToken` requiring `/api/auth/2fa/verify-login` (with monotonic `last_used_timestep` replay prevention + 5-failure lockout); mandatory for `admin` (cannot disable).
- **Google OAuth 2.0 + PKCE ([google_oauth_service.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/services/google_oauth_service.py))**: `/api/auth/google/start` generates CSPRNG `state`, `nonce`, and PKCE `code_verifier`/`code_challenge (S256)` sealed in AES-GCM encrypted `httpOnly` `beanbox_oauth_tx` cookie (`Path=/api/auth/google`); `/callback` verifies `state`, exchanges code with `code_verifier`, verifies Google RS256 `id_token` via JWKS + `nonce` + `email_verified=true`, links existing verified account or creates user, and enforces Step-2 2FA if enabled. Returns `503 OAUTH_DISABLED` cleanly if credentials are blank.
- **RBAC ([dependencies.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/dependencies.py))**:
  - `require_user`: verifies JWT + active non-revoked DB `session`.
  - `require_verified`: `require_user` + `email_verified == True`.
  - `require_role("admin")`: **always re-reads `user.role` and `user.totp_enabled` from Postgres** (stale `role="admin"` JWTs are rejected immediately after DB demotion) + requires `totp_enabled == True` (`403 ADMIN_2FA_REQUIRED`).
- **Audit Logs & Role Management ([admin.py](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/app/routers/admin.py))**: `GET /api/admin/audit-logs` and `PATCH /api/admin/users/{user_id}/role` (revokes target sessions and logs `role_changed`).

### E. Authorization, IDOR Hardening & Security Notifications — [AUTHZ_EXPLAINED.md](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/AUTHZ_EXPLAINED.md)
- **Repository-Scoped Ownership (`404` not `403`)**: `find_by_id_for_user` added across `OrderRepository`, `AddressRepository`, and `ReviewRepository` (`delete_for_user` on reviews); `WishlistService.remove` and `CartService.remove_item` raise `404` when absent from the caller's resource set; `SessionRepository.revoke_by_id` scopes by `(session_id, user_id)`.
- **Mass Assignment & Email Immutability**: Request schemas inherit `CamelModel` (`extra="ignore"`), services build explicit input dataclasses server-side, and no email-change endpoint exists (`UpdateProfileRequest` exposes only `name` and `phone`).
- **Security Alert Emails (`type="security_notification"`)**: Dispatched via `EmailService` / `ConsoleEmailService` with IP and `User-Agent` (never logging tokens/passwords) on password change/reset, 2FA enable/disable, and login from a previously unseen `User-Agent` device (`SessionRepository.check_device_history`).

---

## 5. Frontend Architecture (`frontend/src/`, `25` Built Routes)

- **API Client ([lib/api/client.ts](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/lib/api/client.ts) & [endpoints.ts](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/lib/api/endpoints.ts))**:
  - Automatically reads `beanbox_csrf` / `X-CSRF-Token` response header (bootstrapping `/api/auth/csrf` lazily if absent) and attaches `X-CSRF-Token` on all mutating calls.
  - On `401`, executes **single-flight `refreshAccessTokenSingleFlight()`** so parallel requests queue behind one `POST /api/auth/refresh`, then all retry once; on failure redirects to `/login?next=...` (skipping public auth checks like `authApi.me()`).
- **New/Updated Pages & Components**:
  - [VerifyEmailBanner.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/components/auth/VerifyEmailBanner.tsx) + `/verify-email` ([verify-email page](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/app/verify-email/page.tsx), React 18 StrictMode double-invoke guarded via `useRef`).
  - [GoogleSignInButton.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/components/auth/GoogleSignInButton.tsx) on `/login` & `/signup`.
  - 2-step TOTP / recovery-code flow on [login/page.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/app/login/page.tsx) (supports both password step 1 and `#challenge=` OAuth hash redirect).
  - `/account/security` ([security/page.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/app/account/security/page.tsx)): Change Password, TOTP QR + recovery codes setup/regenerate/disable, Active Sessions device list with per-device **Log out** and **Log out all devices**.
  - Admin enforcement: [admin/layout.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/app/admin/layout.tsx) redirects any `admin` with `!totpEnabled` to `/account/security?enforce2fa=1`; added `/admin/audit-logs` ([audit-logs/page.tsx](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend/src/app/admin/audit-logs/page.tsx)).

---

## 6. Database State (`Supabase` PostgreSQL)

Applied [schema.sql](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/supabase/schema.sql) + [002_production_auth.sql](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/supabase/migrations/002_production_auth.sql) + [003_refresh_grace.sql](file:///Users/ankurmishra/Documents/CODE/COFEEBEAT/backend/supabase/migrations/003_refresh_grace.sql):
- **20 tables in `public`** (all **RLS-enabled**, **0 missing FK indexes**):
  `users`, `password_reset_tokens`, `sessions`, `email_verification_tokens`, `oauth_accounts`, `totp_secrets`, `recovery_codes`, `login_attempts`, `audit_logs`, `products`, `product_variants`, `carts`, `cart_items`, `coupons`, `addresses`, `orders`, `order_items`, `payment_events`, `reviews`, `wishlist_items`.
- **Demo accounts**:
  - `arjun@beanbox.in` / `Coffee@1234` (`customer`, `email_verified=true`, `totp_enabled=false`)
  - `admin@beanbox.in` / `Admin@1234` (`admin`, `email_verified=true`, `totp_enabled=false` — prompts mandatory 2FA setup on first UI login)

---

## 7. Verification Record (Honest Scope)

| Check | Result | Notes |
| :--- | :--- | :--- |
| Backend Lint (`.venv/bin/ruff check app tests`) | **0 errors** (`All checks passed!`) | Run after final code edit |
| Backend Automated Suite (`.venv/bin/pytest -v`) | **32 passed, 1 warning in 2.95s** | Runs against isolated `InMemory` repos (`test_auth.py`, `test_auth_security.py`, `test_authorization.py`, cart, coupons, orders/stock, webhooks, catalog/admin) |
| Frontend Build (`tsc --noEmit`, `next lint`, `next build`) | **0 TS errors, 0 lint errors, 25/25 routes** | 11 pre-existing `@next/next/no-img-element` warnings on SVG catalog assets |
| Live Supabase Migrations & SQL Checks | **Passed** | All 20 tables + RLS + 0 missing FK indexes verified (`002` + `003` applied); live `SupabaseAddressRepository`, `SupabaseOrderRepository`, `SupabaseReviewRepository`, and `SupabaseSessionRepository` query checks + live auth flow passed |
| Live Browser & Auth Flow | **Verified Working** | Frontend (`:3000`) & Backend (`:4000`) tested live with user sign-in/authentication working |

---

## 8. Quick Start & Pre-Production Checklist

### Run Locally
```bash
# Terminal 1 — FastAPI Backend (port 4000)
cd /Users/ankurmishra/Documents/CODE/COFEEBEAT/backend
.venv/bin/uvicorn app.main:app --reload --port 4000

# Terminal 2 — Next.js Frontend (port 3000)
cd /Users/ankurmishra/Documents/CODE/COFEEBEAT/frontend
npm run dev
```

### Before Real Production Launch
1. Rotate `JWT_SECRET`, `TOTP_ENCRYPTION_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, database password, and `GOOGLE_CLIENT_SECRET` (especially any credential pasted into development chats).
2. Add your production origin & callback URL (`https://.../api/auth/google/callback`) in Google Cloud Console and publish the OAuth Consent Screen.
3. Configure `TRUST_PROXY_HEADERS=true` if deployed behind a sanitizing reverse proxy, enforce HTTPS so `Secure` cookies activate (`COOKIE_SECURE=auto`), and swap `ConsoleEmailService` for a transactional email provider (SES/Resend/Postmark) + Redis-backed rate limiting if scaling past 1 API worker.
