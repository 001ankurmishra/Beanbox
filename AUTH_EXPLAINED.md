# BeanBox Production Authentication & Security Guide

Simple, visual reference for how BeanBox's upgraded authentication, session management, 2FA, Google OAuth, CSRF protection, and audit trail work end to end.

---

## 1. System Flows (ASCII Diagrams)

### A. Signup → Email Verification
```text
Browser (Next.js)                  FastAPI (/api/auth)                  Postgres / Email
       |                                   |                                   |
       |-- POST /signup ------------------>|                                   |
       |   { name, email, password }       |-- Validate policy (10+ chars,     |
       |                                   |   not common, no email inside)    |
       |                                   |-- Hash password (Argon2id) ------>|
       |                                   |-- INSERT users (emailVerified=F)->|
       |                                   |-- Generate 256-bit verify token   |
       |                                   |-- Store sha256(token) (24h TTL) ->|
       |                                   |-- Send email w/ ?token=RAW ------>| (inbox / console)
       |                                   |-- Create session + family_id ---->|
       |<-- 201 Set-Cookie:                |                                   |
       |    beanbox_access  (15m,HttpOnly) |                                   |
       |    beanbox_refresh (30d,Path=/api/auth,HttpOnly)                      |
       |    beanbox_csrf    (readable JS)  |                                   |
       |                                   |                                   |
  (Can browse, edit cart, preview checkout)|                                   |
  |-- POST /api/orders (unverified) ------>|-- require_verified -> 403         |
       |                                   |                                   |
  User clicks link -> /verify-email?token=RAW                                  |
       |-- POST /verify-email { token } -->|                                   |
       |                                   |-- Lookup sha256(token), unused,   |
       |                                   |   not expired (24h) ------------->|
       |                                   |-- Mark used + set emailVerified=T |
       |<-- 200 { user } ------------------|                                   |
       |-- POST /api/orders (verified) --->|-- 201 Order Created --------------|
```

### B. Login (Password + Argon2id Upgrade + Brute-Force Protection + Optional 2FA)
```text
Browser                            FastAPI (/api/auth/login)               DB (users/login_attempts)
       |-- POST /login { email, pw } ----->|                                   |
       |                                   |-- Check lock: acct:<email> & ip ->|
       |                                   |   (if locked -> dummy Argon2 + 429)|
       |                                   |-- Load user (if missing: run      |
       |                                   |   dummy Argon2id verify -> 401)   |
       |                                   |-- Verify pw (Argon2id or bcrypt)  |
       |                                   |   If fail: +1 acct & ip counters  |
       |                                   |   5 failures -> lock 15m (x2 next)|
       |                                   |   Return generic "Invalid creds"  |
       |                                   |                                   |
       |                                   |-- If legacy bcrypt matched:       |
       |                                   |   rehash & UPDATE argon2id ------>|
       |                                   |                                   |
       |                                   |-- If user.totpEnabled == True:    |
       |<-- 200 { requiresTwoFactor: true, challengeToken } (NO auth cookies!) |
       |                                   |                                   |
       |                                   |-- Else: create session row +      |
       |<-- 200 { user } + access/refresh/csrf cookies + audit(login_success)  |
```

### C. Access Token Expiry → Single-Flight Silent Refresh → Rotation
```text
Frontend (apiFetch)                             FastAPI (/api)
  Call A ---\
  Call B ----+--> GET /orders, /cart, /wishlist
  Call C ---/            |
                         v (access JWT expired after 15m)
                 401 Unauthorized (x3 concurrently)
                         |
       +-----------------+-----------------+
       | Single-flight refreshInFlight     | (Call B & C wait on SAME promise)
       v                                   |
  POST /api/auth/refresh                   |
  Cookie: beanbox_refresh=R1 (Path=/api/auth)
  Header: X-CSRF-Token + Origin            |
       |                                   |
       +--> Backend validates R1's sha256 against sessions table:
            - Pushes sha256(R1) into previous_refresh_hashes
            - Stores sha256(R2) as current refresh_token_hash
            - Signs brand-new 15m JWT access token (A2)
            - Returns 200 w/ new beanbox_access(A2), beanbox_refresh(R2), csrf
       |
       v
  Call A, B, C automatically retry once with A2 -> 200 OK!
  (If refresh fails -> clear state & redirect browser to /login?next=...)
```

### D. Refresh Token Reuse Detection (Theft / Replay Defense)
```text
Legitimate User Session (family_id = fam_1)
  Login -> R1  ==>  Refresh -> R2 (R1 moved to previous_refresh_hashes)

Attacker steals R1 earlier and replays it AFTER victim rotated to R2:

Attacker                                    FastAPI (/api/auth/refresh)        Postgres (sessions)
   |-- POST /refresh (Cookie: R1) ------------>|                                    |
   |                                           |-- Lookup refresh_token_hash=H(R1)  |
   |                                           |   -> NOT FOUND as current token    |
   |                                           |-- Check previous_refresh_hashes    |
   |                                           |   CONTAINS H(R1) -> REUSE!!        |
   |                                           |-- UPDATE sessions SET revoked_at   |
   |                                           |   WHERE family_id = 'fam_1' ------>|
   |                                           |-- audit_logs: refresh_reuse_detected
   |<-- 401 REFRESH_TOKEN_REUSE_DETECTED ------|                                    |

Result: Both attacker AND victim's R2 / access JWT are revoked immediately.
        Victim is safely forced to re-authenticate.
```

### E. Google OAuth 2.0 (Authorization Code + PKCE + State + Nonce)
```text
Browser                    BeanBox Backend                    Google Identity Platform
   |-- GET /auth/google/start -->|                                      |
   |                             |-- Generate state, nonce,             |
   |                             |   code_verifier (48B random)         |
   |                             |-- code_challenge = b64url(sha256(v)) |
   |<-- 302 Google Auth URL -----|                                      |
   |    + Set-Cookie beanbox_oauth_tx (HttpOnly, AES-GCM encrypted)     |
   |------------------------------------------------------------------->| (User consents)
   |<-- 302 /api/auth/google/callback?code=AUTH_CODE&state=STATE -------|
   |-- GET /google/callback ---->|                                      |
   |                             |-- Decrypt beanbox_oauth_tx cookie    |
   |                             |-- Compare state == tx.state (CS)     |
   |                             |-- POST oauth2.googleapis.com/token ->|
   |                             |   { code, client_secret,             |
   |                             |     code_verifier }  (PKCE proof!)   |
   |                             |<-- { id_token (RS256 JWT) } ---------|
   |                             |-- Verify RS256 via Google JWKS       |
   |                             |-- Verify id_token.nonce == tx.nonce  |
   |                             |-- Verify email_verified == true      |
   |                             |-- Link oauth_accounts or create user |
   |<-- 302 Frontend (/ or /login?twofa=1#challenge=...) + cookies -----|
```

### F. 2FA (TOTP + Single-Use Recovery Codes) Login Flow
```text
Step 1: Password / Google OK on account with totp_enabled=true
        Backend issues short-lived (5m) single-use challengeToken JWT (NO session yet)

Browser                                  FastAPI (/api/auth/2fa/verify-login)
   |-- POST /2fa/verify-login --------------->|
   |   { challengeToken, code }               |-- Verify challengeToken sig, exp, typ
   |                                          |-- Check 2fa:<user_id> lockout (< 5 fails)
   |                                          |-- If 6 digits: decrypt AES-GCM TOTP secret
   |                                          |   & verify RFC 6238 code (timestep > last_used)
   |                                          |-- Else: HMAC-SHA256 recovery code &
   |                                          |   mark used_at = now() atomically
   |                                          |-- Mark challengeToken jti consumed
   |                                          |-- Create session row + issue access/refresh/csrf
   |<-- 200 { user } + auth cookies ----------|
```

---

## 2. Security Controls & Attacks Prevented

- **XSS Token Theft** → **Mitigated**: Access JWT (`beanbox_access`) and Refresh token (`beanbox_refresh`) are stored strictly in `HttpOnly` cookies (never `localStorage`), so injected JavaScript cannot read or exfiltrate session credentials. Also **Path scoping** (`Path=/api/auth`) keeps refresh tokens off every non-auth endpoint.
- **CSRF (Cross-Site Request Forgery)** → **Blocked (2 layers)**:
  1. `SameSite=Lax` cookies stop third-party cross-site POST form submissions from carrying cookies.
  2. Double-submit CSRF (`beanbox_csrf` cookie + `X-CSRF-Token` header verified via constant-time `secrets.compare_digest`) PLUS strict `Origin` / `Referer` allowlist verification on all cookie-authenticated mutations.
- **Token Theft & Replay** → **Contained & Auto-Revoked**:
  - Access JWTs expire in **15 minutes**.
  - Refresh tokens are **256-bit opaque secrets**, stored ONLY as SHA-256 hashes in DB (`sessions`), rotated on every `/refresh`, and **reuse detection** revokes the entire `family_id` on replay.
  - Step-2 TOTP codes enforce monotonic `last_used_timestep` (same 30s code cannot be replayed twice); challenge tokens, email verification tokens, password reset tokens, and recovery codes are all single-use.
- **Brute-Force & Credential Stuffing** → **Throttled + Locked**:
  - Stricter per-IP sliding-window rate limits per endpoint (`login`, `signup`, `reset`, `verify-resend`, `refresh`, `2fa`).
  - Persistent per-account + per-IP failure counters lock after 5 failures for 15 minutes with exponential doubling (`15m -> 30m -> 60m...`).
  - Argon2id (`memory=64 MiB, time=3, parallelism=4`) resists GPU/ASIC cracking, with transparent bcrypt-to-Argon2id upgrade on login and weak/common/email-containing passwords rejected.
- **Account Enumeration** → **Prevented**:
  - Login runs dummy Argon2id verification on missing/locked accounts for uniform timing and returns only `"Invalid credentials"`.
  - Forgot password returns the exact same `200` payload for existing and non-existent emails.
  - Lockout counters apply identically to non-existent and real emails.
- **Session Fixation & Privilege Stale Claims** → **Prevented**:
  - Every login mints a fresh `session.id`, `family_id`, `jti`, and rotates CSRF cookies.
  - Access JWTs carry `sid` checked against DB `sessions.revoked_at`, so device logout / password change / password reset invalidates access immediately.
  - `require_role("admin")` re-reads `role` and `totp_enabled` directly from Postgres instead of trusting stale JWT claims.
- **Authorization Code Interception / OAuth CSRF** → **Blocked**:
  - Google OAuth uses `PKCE (S256)`, AES-GCM sealed `httpOnly` transaction cookies (`beanbox_oauth_tx`), cryptographically random `state` + OIDC `nonce` verification, `email_verified=true` enforcement, and strict relative `next` URL sanitization (no open redirects).
- **Secrets-at-Rest Protection** → **Enforced**:
  - TOTP secrets are encrypted with `AES-256-GCM` (`v1:...`) before storage; recovery codes, refresh tokens, reset tokens, and verification tokens store only cryptographic hashes; logs scrub query strings and sensitive metadata keys.

---

## 3. New & Updated Auth / Admin Endpoints

| Method | Path | Auth Required | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/auth/csrf` | Public | Issues/refreshes double-submit CSRF cookie & `X-CSRF-Token` header |
| `GET` | `/api/auth/providers` | Public | Returns `{ googleOAuthEnabled }` for frontend UI gating |
| `POST` | `/api/auth/signup` | Public (Rate-limited) | Registers user (Argon2id + policy), sends 24h verification email, sets cookies |
| `POST` | `/api/auth/login` | Public (Rate-limited + Lockout) | Password login; returns user+cookies or Step-2 `challengeToken` if 2FA enabled |
| `POST` | `/api/auth/refresh` | Refresh cookie + CSRF | Rotates opaque refresh token & 15m JWT; detects reuse and revokes family |
| `POST` | `/api/auth/logout` | Cookie / Session + CSRF | Revokes current session row and clears auth cookies |
| `POST` | `/api/auth/logout-all` | `require_user` + CSRF | Revokes all active sessions for current user and clears cookies |
| `POST` | `/api/auth/change-password` | `require_user` + CSRF | Verifies current password, updates hash (Argon2id), revokes all other sessions |
| `POST` | `/api/auth/verify-email` | Public (Rate-limited) | Consumes single-use 24h verification token and marks email verified |
| `POST` | `/api/auth/verify-email/resend` | `require_user` + CSRF | Re-sends email verification link (60s cooldown + IP limit) |
| `GET` | `/api/auth/sessions` | `require_user` | Lists active non-revoked sessions/devices (`isCurrent`, IP, UA, timestamps) |
| `DELETE` | `/api/auth/sessions/{sessionId}` | `require_user` + CSRF | Immediately revokes a specific session/device belonging to the user |
| `GET` | `/api/auth/2fa/status` | `require_user` | Returns `{ enabled, requiredForRole, recoveryCodesRemaining }` |
| `POST` | `/api/auth/2fa/setup` | `require_user` + CSRF | Generates TOTP secret (stored AES-256-GCM encrypted) + SVG QR data URL |
| `POST` | `/api/auth/2fa/enable` | `require_user` + CSRF | Verifies first TOTP code, enables 2FA, returns 10 recovery codes once |
| `POST` | `/api/auth/2fa/verify-login` | Public (Challenge JWT + Rate-limited) | Completes Step-2 login using 6-digit TOTP or single-use recovery code |
| `POST` | `/api/auth/2fa/recovery-codes/regenerate` | `require_user` + CSRF | Requires current TOTP code and issues 10 fresh backup codes |
| `POST` | `/api/auth/2fa/disable` | `require_user` + CSRF | Disables 2FA (requires code + password; forbidden for `admin` role) |
| `GET` | `/api/auth/google/start` | Public | Starts Google OAuth 2.0 + PKCE (`S256`) flow with encrypted state cookie |
| `GET` | `/api/auth/google/callback` | OAuth tx cookie | Validates state, exchanges code w/ PKCE, verifies ID token `nonce`, links/creates user |
| `PATCH` | `/api/admin/users/{userId}/role` | `require_role("admin")` + CSRF | Updates user role, revokes target user's sessions, writes audit log |
| `GET` | `/api/admin/audit-logs` | `require_role("admin")` | Paginated & filterable security audit trail (`ip`, `userAgent`, `requestId`) |

---

## 4. What Large Companies Add Beyond This

1. **Passkeys / WebAuthn (FIDO2)**: Phishing-resistant biometric/hardware-key login (`navigator.credentials`) using origin-bound public-key cryptography instead of passwords or TOTP codes (cannot be phished even on a lookalike domain).
2. **Enterprise SSO (SAML 2.0 & OIDC Multi-Tenant)**: Domain-verified workforce login via Okta, Microsoft Entra ID, or Google Workspace with SCIM automated deprovisioning when employees leave.
3. **Device Trust & mTLS / Hardware Attestation**: Tracking recognized device fingerprints or TPM/Secure Enclave posture signals before granting sensitive admin/billing privileges.
4. **Risk-Based / Adaptive Authentication**: Real-time scoring using impossible-travel geo-velocity, ASN/TOR/VPN reputation, credential-stuffing breach feeds (HaveIBeenPwned k-anonymity check), and anomalous behavior to step up verification only when risk is elevated.
5. **Distributed Redis Rate Limiting & Anomaly Alerts**: Moving sliding-window counters from per-process memory to Redis (`ZSET` / Lua scripts) across load-balanced API replicas, plus real-time PagerDuty/Slack alerts on reuse-detection spikes or admin role escalations.
