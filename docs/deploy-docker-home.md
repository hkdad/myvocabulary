# Deploy myvocabulary to your-server.local

**Target:** Home production server (`your-server.local`)  
**Port:** `8080` (host) → `8000` (container)  
**Repo:** https://github.com/hkdad/myvocabulary

---

## Quick deploy

```bash
git clone https://github.com/hkdad/myvocabulary.git
cd myvocabulary
cp .env.example .env
# Edit .env: set SECRET_KEY (openssl rand -hex 32), DEBUG=false, CORS_ORIGINS
mkdir -p data/audio data/backups data/curated logs
chmod +x start.sh scripts/backup-db.sh
./start.sh
```

Open: `http://your-server.local:8080`

**Test logins:** `parent`/`parent123`, `mia`/`mia`, `leo`/`leo`, `max`/`max`

---

## Fix: "Wrong username or password" after deploy

The database has no users yet. Run the seed script:

```bash
cd /path/to/myvocabulary
docker compose exec -T app python scripts/seed.py
```

You should see:

```
Created user: parent
Created user: mia
Created user: leo
Created user: max
...
Seed complete.
```
(Re-seed resets demo passwords: kids use username == password.)

Then try logging in again.

**Prevention:** Current `Dockerfile` runs `python scripts/seed.py` on every container start (idempotent). Rebuild and redeploy:

```bash
git pull
docker compose up -d --build
```

---

## Verify login from the server

```bash
curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"leo","password":"leo"}'
```

Expected: JSON with `"access_token"`. If you get `AUTH_INVALID_CREDENTIALS`, run seed (above).

---

## Production `.env` checklist

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | Random 32-byte hex (`openssl rand -hex 32`) — **required**; app refuses to start if still the default |
| `DEBUG` | `false` |
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | URLs you use, e.g. `http://your-server.local:8080,http://192.168.x.x:8080` |

**Security notes (production):**
- Login quick-picks show display names only (no usernames).
- Refresh cookies use `Secure` when `APP_ENV=production`.
- Rate limits: login (10/min per IP), daily challenge rebuild (5/day per learner), CSV import (3/hour per parent).

`DATABASE_URL` and `AUDIO_DIR` are set in `docker-compose.yml` for the container.

---

## Updates

```bash
git pull
docker compose up -d --build
```

Data in `./data/` is preserved.

---

## Backups

```bash
./scripts/backup-db.sh
```

Backups: `data/backups/myvocabulary_YYYYMMDD_HHMMSS.db`
