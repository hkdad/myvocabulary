.PHONY: install dev dev-backend dev-frontend test test-e2e lint format migrate seed import-catalog delete-curated backup build

install:
	cd backend && uv venv .venv && uv pip install -e ".[dev]"
	cd frontend && pnpm install

dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && pnpm dev --host 127.0.0.1 --port 5173

dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals."

test:
	cd backend && .venv/bin/pytest -q
	cd frontend && pnpm test && pnpm build

test-e2e:
	cd backend && (test -d .venv || uv venv .venv) && uv pip install -e ".[dev]"
	cd backend && .venv/bin/alembic upgrade head
	cd e2e && pnpm install && pnpm exec playwright install chromium && pnpm test

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && pnpm run lint

format:
	cd backend && .venv/bin/ruff format .
	cd frontend && pnpm run format

migrate:
	cd backend && .venv/bin/alembic upgrade head

import-catalog:
	cd backend && .venv/bin/python scripts/import_curated_lists.py

delete-curated:
	cd backend && .venv/bin/python scripts/delete_curated_lists.py

seed:
	cd backend && .venv/bin/python scripts/seed.py

backup:
	./scripts/backup-db.sh

build:
	cd frontend && pnpm build
	mkdir -p backend/static
	cp -r frontend/dist/* backend/static/
