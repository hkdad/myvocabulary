# Backup and restore

**Last updated:** 2026-08-04

## What to back up

| Path (host) | Contents |
|-------------|----------|
| `./data/myvocabulary.db` | SQLite database (users, SRS, bank, challenges) |
| `./data/audio/` | Cached TTS files (regenerable, but large) |
| `./data/backups/` | Output of the backup script |

Stop or briefly pause writers if you need a cold copy; for routine backups use the script (SQLite online backup / file copy).

## Manual backup

```bash
./scripts/backup-db.sh
```

Recommended cron (host, daily 02:00):

```bash
0 2 * * * /path/to/myvocabulary/scripts/backup-db.sh
```

## Restore

1. Stop the app: `docker compose down` (or stop local uvicorn)
2. Replace `data/myvocabulary.db` with a backup copy
3. Start again: `./start.sh` or `make dev-backend`
4. Confirm login (e.g. `leo`/`leo` or `max`/`max`)

## Seed after empty DB

If the DB is new/empty:

```bash
docker compose exec -T app python scripts/seed.py
# or locally:
cd backend && uv run python scripts/seed.py
```

Demo accounts: `parent`/`parent123`, `mia`/`mia`, `leo`/`leo`, `max`/`max`.

See also [deploy-docker-home.md](./deploy-docker-home.md).
