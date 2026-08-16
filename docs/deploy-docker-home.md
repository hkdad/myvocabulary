# Deploy myvocabulary to docker.home

**Target:** Home production server (`docker.home`, `192.168.1.40`)  
**SSH:** `jacky@docker.home`  
**Path:** `/home/jacky/myvocabulary`  
**Port:** `8080` (host) → `8000` (container)  
**Repo:** https://github.com/hkdad/myvocabulary  
**Also reachable:** `https://dict.home` (Caddy reverse proxy to `:8080`)

---

## Quick deploy (fresh server)

```bash
git clone https://github.com/hkdad/myvocabulary.git
cd myvocabulary
cp .env.example .env
# Edit .env: set SECRET_KEY (openssl rand -hex 32), DEBUG=false, CORS_ORIGINS
mkdir -p data/audio data/backups data/curated logs
chmod +x start.sh scripts/backup-db.sh
./start.sh
```

Open: `http://docker.home:8080` or `https://dict.home`

**Test logins:** `parent`/`parent123`, `mia`/`mia`, `leo`/`leo`, `max`/`max`

---

## Migrate from jackywongxp/myvocabulary (one-time)

If the server already has a checkout from the old private repo, histories do not share commits. Retarget origin and hard-reset (keeps `./data/` and `.env`):

```bash
cd /home/jacky/myvocabulary

# Backup live DB first
docker compose exec -T app python -c "
import sqlite3, datetime
src = sqlite3.connect('/app/data/myvocabulary.db')
path = '/app/data/backups/myvocabulary_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.db'
dst = sqlite3.connect(path)
src.backup(dst); dst.close(); src.close()
print(path)
"

git remote set-url origin https://github.com/hkdad/myvocabulary.git
git fetch origin
git reset --hard origin/main
git clean -fd
mkdir -p data/curated   # required for Docker build context
docker compose up -d --build
```

---

## Fix: "Wrong username or password" after deploy

The database has no users yet. Run the seed script:

```bash
cd /home/jacky/myvocabulary
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
| `CORS_ORIGINS` | `http://docker.home:8080,http://192.168.1.40:8080` (add `https://dict.home` if you use the Caddy hostname) |

**Security notes (production):**
- Login quick-picks show display names only (no usernames).
- Refresh cookies use `Secure` when `APP_ENV=production`.
- Rate limits: login (10/min per IP), daily challenge rebuild (5/day per learner), CSV import (3/hour per parent).

`DATABASE_URL` and `AUDIO_DIR` are set in `docker-compose.yml` for the container.

---

## Updates (canonical)

On the server:

```bash
cd /home/jacky/myvocabulary
git pull
docker compose up -d --build
```

Data in `./data/` is preserved.

From your Mac, you can also rsync via `scripts/deploy.sh` (fallback; does not change git remote).

---

## Backups

```bash
./scripts/backup-db.sh
```

Backups: `data/backups/myvocabulary_YYYYMMDD_HHMMSS.db`
