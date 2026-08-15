# Auth strategy

**Status:** Accepted  
**Date:** 2026-07-30

## Context

Learners use separate devices and need long-lived sessions. Parents manage accounts and sensitive actions.

## Decision

- Use JWT access tokens (short-lived, in memory on the client)
- Store refresh tokens in **httpOnly cookies** where possible
- Role-based access: `parent` vs `learner`
- Parent approves all level changes and list assignments

## Consequences

- Safer than localStorage for refresh tokens
- Requires `allow_credentials=True` in CORS
- Sprint 1 will implement the full auth flow
