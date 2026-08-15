# myvocabulary

[![CI](https://github.com/hkdad/myvocabulary/actions/workflows/ci.yml/badge.svg)](https://github.com/hkdad/myvocabulary/actions/workflows/ci.yml)

Family vocabulary learning and dictionary app for kids — React frontend, FastAPI backend, SQLite.

## Quick start (local development)

```bash
make install
make migrate
make seed        # parent, mia, leo, max accounts
make dev-backend   # terminal 1 — http://localhost:8000
make dev-frontend  # terminal 2 — http://localhost:5173
```

Open http://localhost:5173/login and sign in:

| User | Password | Lands on |
|------|----------|----------|
| `parent` | `parent123` | `/parent/dashboard` |
| `mia` | `mia` | `/app/home` (teen theme) |
| `leo` | `leo` | `/app/home` (kid theme) |
| `max` | `max` | `/app/home` (kid theme) |

## Production (Docker)

```bash
cp .env.example .env   # edit SECRET_KEY
chmod +x start.sh
./start.sh             # http://localhost:8080
```

## Project structure

```
myvocabulary/
├── backend/       # FastAPI + SQLAlchemy + Alembic
├── frontend/      # React + TypeScript + Vite + Tailwind
├── data/          # SQLite DB, audio cache (gitignored except curated/)
├── docs/          # Spec, project plan, ADRs
├── scripts/       # backup-db.sh, seed (Sprint 1)
├── start.sh       # One-command Docker startup
└── docker-compose.yml
```

## Useful commands

| Command | Description |
|---------|-------------|
| `make install` | Install backend + frontend dependencies |
| `make migrate` | Run Alembic migrations |
| `make test` | Run backend tests + frontend build |
| `make lint` | Run Ruff + frontend lint |
| `make backup` | Backup SQLite database |

## Documentation

- [Phase 1 Technical Spec](docs/phase-1-spec.md) (shipped)
- [Phase 2 Technical Spec](docs/phase-2-spec.md) (current product truth — loop + readiness)
- [Project Plan](docs/project-plan.md)
- [Project Status](docs/project-status.md)
- [Architecture](docs/architecture.md)
- [Backup / restore](docs/backup-restore.md)
- [Deploy (your-server.local)](docs/deploy-docker-home.md)

## Sprint status

**Phase 1:** ✅ Complete on `main` (Sprints 0–7).

**Phase 2 P2.0:** ✅ Shipped on `main` — family word bank, Loop Engine, recognition-first Daily Challenge, strength (1/2/3 days), readiness gauge, Level-up exam at ≥75% readiness (30 MCQ, 80% pass), lazy 繁中, E2E learning-loop.

**Phase 2 P2.1:** 🔄 Polish (category filters, parent goal editing, due-load warnings). Spec: [phase-2-spec.md](docs/phase-2-spec.md).

See [Project Plan](docs/project-plan.md) for full sprint breakdown.
