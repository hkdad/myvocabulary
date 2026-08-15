#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${ROOT_DIR}/data/myvocabulary.db"
BACKUP_DIR="${ROOT_DIR}/data/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/myvocabulary_${TIMESTAMP}.db"

mkdir -p "${BACKUP_DIR}"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "No database found at ${DB_PATH}"
  exit 1
fi

sqlite3 "${DB_PATH}" ".backup '${BACKUP_PATH}'"
echo "Backup saved to ${BACKUP_PATH}"
