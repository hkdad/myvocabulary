# Architecture overview

**Status:** Living pointers — detailed rules live in the Phase specs and ADRs.  
**Last updated:** 2026-08-04

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | React 18, TypeScript, Vite, Tailwind, Zustand |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| DB | SQLite (WAL) under `data/myvocabulary.db` |
| Deploy | Docker + `start.sh` → host `:8080` |

## Key services (backend)

| Concern | Module |
|---------|--------|
| Auth (JWT + httpOnly refresh) | `app/services/auth_service.py` — [ADR 001](./adr/001-auth-cookies.md) |
| Dictionary + TTS | `dictionary_service.py`, `tts_service.py` |
| Word lists / family bank | `word_list_service.py`, `word_bank_service.py` |
| Loop Engine (drip + strength) | `loop_engine.py` |
| Readiness scoring | `readiness_service.py`, `performance_analytics.py` |
| Challenges / Level-up gate | `challenge_service.py` |
| AI level assessment | `ai_level_service.py` |

## Product rules (current)

- Recognition-first daily challenge — [phase-2-spec §1.6](./phase-2-spec.md)
- Strength: Learning / Familiar / Mastered = 1 / 2 / 3+ distinct review days
- Level-up exam unlocks at readiness ≥ 75%; parent Accept owns level change — [phase-2-spec §5.3](./phase-2-spec.md)
- Docker deploy — [ADR 002](./adr/002-docker-deployment.md), [deploy-docker-home.md](./deploy-docker-home.md)

## API docs

With the backend running locally: `http://127.0.0.1:8000/docs` (OpenAPI).
