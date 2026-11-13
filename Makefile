.PHONY: help api worker beat test test-celery test-pg lint build

PYTHON ?= backend/.venv/bin/python
CELERY ?= backend/.venv/bin/celery
UVICORN ?= backend/.venv/bin/uvicorn
PYTEST ?= backend/.venv/bin/pytest
RUFF ?= backend/.venv/bin/ruff

help:
	@echo "BeanBox Development & Background Jobs Commands:"
	@echo "  make api         - Start FastAPI backend on port 4000 (reload enabled)"
	@echo "  make worker      - Start Celery worker (2 concurrent prefork processes, all queues)"
	@echo "  make beat        - Start Celery Beat periodic scheduler (single instance only)"
	@echo "  make test        - Run backend pytest test suite"
	@echo "  make test-celery - Run real-worker Celery test suite against REDIS_URL_TEST"
	@echo "  make test-pg     - Run PostgreSQL concurrency and partial-index test suite"
	@echo "  make lint        - Run Ruff linter on backend and ESLint on frontend"
	@echo "  make build       - Run Next.js frontend production build"

api:
	cd backend && ../$(UVICORN) app.main:app --host 0.0.0.0 --port 4000 --reload

worker:
	cd backend && ../$(CELERY) -A app.worker.celery_app worker -l info -Q default,emails,maintenance -c 2

beat:
	cd backend && ../$(CELERY) -A app.worker.celery_app beat -l info

test:
	cd backend && ../$(PYTEST) tests/

test-celery:
	cd backend && APP_ENV=test REDIS_URL_TEST=redis://localhost:6379/0 ../$(PYTEST) -m celery tests/

test-pg:
	cd backend && ../$(PYTEST) -m pg tests/

lint:
	$(RUFF) check backend
	npm --prefix frontend run lint

build:
	npm --prefix frontend run build
