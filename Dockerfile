# Frontend build
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
ENV CI=true
RUN corepack enable
COPY frontend/ ./
RUN pnpm install --frozen-lockfile
RUN pnpm build

# Backend runtime
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl ffmpeg \
  && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY backend/pyproject.toml backend/README.md ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/scripts ./scripts
COPY data/curated ./data/curated

RUN uv venv .venv \
  && uv pip install --python .venv/bin/python -e .

COPY --from=frontend-build /app/frontend/dist ./static

ENV PATH="/app/.venv/bin:$PATH"
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/myvocabulary.db
ENV AUDIO_DIR=/app/data/audio

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
