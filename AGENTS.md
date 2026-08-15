# AGENTS.md

Family vocabulary learning app (kids). React 19 + Vite frontend, FastAPI + SQLAlchemy + Alembic backend, SQLite, Playwright e2e. JS via **pnpm**, Python via **uv**.

## Layout

- `backend/` — FastAPI app (`app/main.py`); all routes under `/api/v1` (`app/api/v1`). OpenAPI docs at `/docs` only when `DEBUG=true`.
- `frontend/` — React + TS + Vite + Tailwind 4 + Zustand + React Query + React Router 7.
- `e2e/` — Playwright, its own pnpm project.
- `docs/` — `docs/phase-2-spec.md` is current product truth; ADRs in `docs/adr/`.
- `data/` — SQLite DB + audio, gitignored and created at runtime.

## Commands (canonical source: `Makefile`)

`make` is **not installed on this Windows machine** — run the equivalents in PowerShell. Backend venv binaries live in `.venv\Scripts\` here (the Makefile assumes POSIX `.venv/bin/`).

- Setup: `cd backend; uv venv .venv; uv pip install -e ".[dev]"` then `cd frontend; pnpm install`
- Migrate: `cd backend; .venv\Scripts\alembic.exe upgrade head`
- Seed dev users (`parent`/`parent123`, `mia`/`mia`, `leo`/`leo`, `max`/`max`): `cd backend; .venv\Scripts\python.exe scripts/seed.py`
- Dev backend: `.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000` — Vite dev server proxies `/api` to it
- Dev frontend: `cd frontend; pnpm dev` (port 5173)
- Backend tests: `cd backend; .venv\Scripts\python.exe -m pytest -q`
- Frontend tests: `cd frontend; pnpm test` (vitest run)
- Lint: backend `ruff check .`; frontend `pnpm run lint`
- Format: backend `ruff format .`; frontend `format` script is just `oxlint` (no prettier)
- Prod SPA build: `cd frontend; pnpm build`, then copy `frontend/dist/*` into `backend/static/` (FastAPI serves it; `backend/static/` is gitignored)
- E2E: `cd e2e; pnpm install; pnpm exec playwright install chromium; pnpm test`

## Gotchas

- **Frontend lint is oxlint, not ESLint** (rules in `frontend/.oxlintrc.json`). `pnpm format` == `pnpm lint`.
- **Backend ruff**: line-length 100, target py312, selects `E,F,I,UP`.
- **E2E self-manages infra**: `e2e/playwright.config.ts` boots its own backend (`:8799`) + frontend (`:5174`), builds a fresh seeded SQLite DB at `e2e/.e2e-myvocabulary.db`, sets `E2E_SKIP_CATALOG=1`, runs `workers: 1`. Just run `pnpm test` in `e2e/` after install.
- **Backend pytest** uses an in-memory SQLite DB with manually-created FTS5 triggers (`backend/tests/conftest.py`); no migrations needed. `pytest-asyncio` is in `auto` mode; rate limiter is reset per test.
- **Auth is cookie-based** (httpOnly refresh + short bearer access token — `docs/adr/001-auth-cookies.md`); session state lives in the Zustand `authStore`.
- **Dictionary + TTS hit external APIs** (`DICTIONARY_API_URL` + `DICTIONARY_FALLBACK_API_URL`); tests override/mock them.
- **AI level assessment is optional**: runs only when `OPENAI_API_KEY` is set in `.env` (OpenAI-compatible; defaults to `https://opencode.ai/zen/go/v1`, model `mimo-v2.5`).
- **Env**: `backend/.env.example` → `backend/.env` (DB at `../data/myvocabulary.db`); `frontend/.env.example` → `frontend/.env` (`VITE_API_BASE_URL`). `SECRET_KEY` required for prod. `frontend/.env.local` exists locally but is gitignored.
- **Prod**: single container — `cp .env.example .env && ./start.sh` → `:8080` (see `docs/deploy-docker-home.md`, ADR 002).
- **CI** (`backend/.github/workflows/ci.yml` actually `.github/workflows/ci.yml`) on push/PR to `main`: ruff check + `ruff format --check` + pytest; frontend `pnpm build` only (vitest/lint not run in CI); `docker compose config`; e2e. Pre-commit runs `ruff --fix` + `ruff-format` scoped to `backend/`.
