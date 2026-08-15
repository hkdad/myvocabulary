# Docker deployment

**Status:** Accepted  
**Date:** 2026-07-30

## Context

The app will run on a family home server. We want one-command startup and persistent data across restarts.

## Decision

- Production deployment uses **Docker Compose**
- `./start.sh` is the single entry point
- SQLite database and audio files are stored in `./data` via a volume mount
- Multi-stage Dockerfile builds React frontend and Python backend in one image

## Consequences

- Simple deployment for the family server
- Local development can still use `make dev` without Docker
- HTTPS reverse proxy (Caddy) can be added as an optional compose service later
