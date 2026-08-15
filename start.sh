#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: docker daemon is not running."
  exit 1
fi

mkdir -p data/audio data/backups data/curated

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example — review SECRET_KEY before production use."
fi

echo "Building and starting myvocabulary..."
docker compose up -d --build

echo "Waiting for health check..."
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8080/health >/dev/null 2>&1; then
    echo ""
    echo "Running database migrations..."
    docker compose exec -T app alembic upgrade head

    echo "Seeding accounts and curated lists (idempotent)..."
    docker compose exec -T app python scripts/seed.py || true

    echo ""
    echo "myvocabulary is running at http://localhost:8080"
    echo "Login: parent/parent123, mia/mia, leo/leo"
    exit 0
  fi
  sleep 2
done

echo "Error: service did not become healthy in time."
docker compose logs --tail=50
exit 1
