# BeanBox — Specialty Coffee E-Commerce Store (India)

A complete, production-style coffee e-commerce store built as a monorepo with **Next.js 14 (App Router)**, **Tailwind CSS**, **TypeScript**, and a **Python + FastAPI** backend following a strict Repository Pattern wired to **Supabase PostgreSQL** (with an automatic in-memory fallback for isolated unit tests).

- **Market**: India (`INR ₹`, 5% GST split into CGST 2.5% + SGST 2.5%, free shipping above ₹999, ₹79 below ₹999).
- **Payments**: Stripe Checkout (test mode) with automatic HMAC-SHA256 signed Mock Payment Provider fallback when Stripe keys are not set.

---

## Project Structure

```text
.
├── backend/                # Python 3.13 + FastAPI + Pydantic v2 REST API
│   ├── app/
│   │   ├── main.py         # FastAPI app factory & Swagger UI (/api/docs)
│   │   ├── models/         # Canonical Pydantic domain models
│   │   ├── repositories/   # ABC interfaces + seeded in-memory implementations
│   │   ├── services/       # Pricing (5% GST), Auth, Cart, Checkout, Payments, Admin
│   │   ├── routers/        # API endpoints
│   │   ├── middleware/     # Security headers, rate limiting, logging, error handlers
│   │   └── seed/           # 20 products, 2 users, 4 coupons, sample order/review
│   ├── tests/              # Pytest + TestClient integration suites
│   └── BACKEND_EXPLAINED.md
├── frontend/               # Next.js 14 App Router + TypeScript + Tailwind CSS
│   ├── public/images/      # Local SVG product artwork
│   └── src/
│       ├── app/            # Storefront, Product Detail, Cart, Checkout, Account, Admin
│       ├── components/     # Navbar, CartDrawer, ProductCard, ConfirmDialog, UI
│       ├── context/        # Auth, Optimistic Cart, Optimistic Wishlist, Toasts
│       └── lib/api/        # Typed fetch client (credentials: include)
└── package.json            # Convenience root scripts
```

---

## Quick Start

### 1. Environment Variables
Copy the example env files if you want custom values (safe dev defaults work out of the box):
```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

### 2. Backend Setup & Run (FastAPI on port `4000`)
```bash
cd backend
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# Verify seed data
.venv/bin/python -m app.seed.run_seed

# Run automated tests & lint (in-memory unit + security suites)
.venv/bin/pytest -v
.venv/bin/ruff check app tests

# Run Postgres concurrency & parity suite against isolated local Docker Postgres (NEVER production Supabase)
docker compose -f ../docker-compose.test.yml up -d --wait
DATABASE_URL_TEST="postgresql://beanbox_test:beanbox_test_password@localhost:5433/beanbox_test" \
  .venv/bin/pytest -v -m pg
docker compose -f ../docker-compose.test.yml down -v

# Start FastAPI server
.venv/bin/uvicorn app.main:app --reload --port 4000
```
- API Health: `http://localhost:4000/api/health`
- Interactive OpenAPI / Swagger Docs: `http://localhost:4000/api/docs`

### 3. Frontend Setup & Run (Next.js 14 on port `3000`)
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## Demo Accounts & Promo Codes

| Role | Email | Password |
| :--- | :--- | :--- |
| **Customer** | `arjun@beanbox.in` | `Coffee@1234` |
| **Admin** | `admin@beanbox.in` | `Admin@1234` |

**Active Coupons**:
- `WELCOME10` — 10% off (min ₹499, max ₹300)
- `FLAT150` — Flat ₹150 off (min ₹999)
- `BREW20` — 20% off (min ₹1,499, max ₹500)
- `EXPIRED50` — Expired promo (useful for verifying rejection)

---

## Architecture Documentation
See [`backend/BACKEND_EXPLAINED.md`](backend/BACKEND_EXPLAINED.md) for a complete walkthrough of the FastAPI request lifecycle, `httpOnly` cookie authentication, atomic oversell prevention, webhook idempotency, worked GST calculation example, and Supabase migration guide.
