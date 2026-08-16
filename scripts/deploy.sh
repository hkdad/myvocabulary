#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOTE_HOST="${REMOTE_HOST:-docker.home}"
REMOTE_USER="${REMOTE_USER:-jacky}"
REMOTE_DIR="${REMOTE_DIR:-/home/jacky/myvocabulary}"
REMOTE="${REMOTE_USER}@${REMOTE_HOST}"

if ! command -v rsync >/dev/null 2>&1; then
  echo "Error: rsync is not installed."
  exit 1
fi

if ! command -v ssh >/dev/null 2>&1; then
  echo "Error: ssh is not installed."
  exit 1
fi

echo "Deploying myvocabulary to ${REMOTE}:${REMOTE_DIR}"
echo "Note: git pull on the server is the canonical update path. This script rsyncs code only."

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "${REMOTE}" "echo ok" >/dev/null 2>&1; then
  echo "Error: cannot SSH to ${REMOTE}."
  echo "Add your public key to the server first:"
  echo "  ssh-copy-id ${REMOTE}"
  exit 1
fi

rsync -avz --delete \
  --exclude '.git/' \
  --exclude 'node_modules/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude 'backend/.venv/' \
  --exclude 'backend/static/' \
  --exclude '.pnpm-store/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude 'logs/' \
  --exclude 'e2e/test-results/' \
  --exclude 'e2e/.e2e-myvocabulary.db*' \
  --exclude '.DS_Store' \
  "$ROOT_DIR/" "${REMOTE}:${REMOTE_DIR}/"

ssh "${REMOTE}" bash <<REMOTE_SCRIPT
set -euo pipefail
cd ${REMOTE_DIR}

mkdir -p data/audio data/backups data/curated logs

if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET_KEY="\$(openssl rand -hex 32)"
  sed -i.bak "s/^SECRET_KEY=.*/SECRET_KEY=\${SECRET_KEY}/" .env
  rm -f .env.bak
  echo "Created production .env with generated SECRET_KEY."
fi

# Ensure container paths and production settings even if .env already existed.
# Do not overwrite CORS_ORIGINS if already set (production hostnames differ per install).
if ! grep -q '^CORS_ORIGINS=.*docker.home' .env 2>/dev/null; then
  sed -i.bak \
    -e "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://docker.home:8080,http://192.168.1.40:8080|" \
    .env
  rm -f .env.bak
fi

sed -i.bak \
  -e "s|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:////app/data/myvocabulary.db|" \
  -e "s|^AUDIO_DIR=.*|AUDIO_DIR=/app/data/audio|" \
  -e "s/^APP_ENV=.*/APP_ENV=production/" \
  -e "s/^DEBUG=.*/DEBUG=false/" \
  .env
rm -f .env.bak

chmod +x start.sh
./start.sh
REMOTE_SCRIPT

echo ""
echo "Deployed. Open http://${REMOTE_HOST}:8080 (or https://dict.home)"
echo "Login: parent/parent123, mia/mia, leo/leo"
