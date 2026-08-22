# Changelog

All notable releases of myvocabulary. Version source of truth: [`VERSION`](VERSION).

## 0.2.0 — 2026-08-22

### Added
- Book as Word Bank: parent upload, parse preview, assign one active book per learner
- Hybrid daily mix: new words from active book, retention from family bank
- Book progress + page coverage on learner home
- Lazy Traditional Chinese on MCQ via `ensure-zh` (MyMemory fallback when no LLM key)

### Fixed
- Definition prefetch/cache for book and bank words
- Clear translation no longer refilled on dictionary lookup GET
- MCQ choices render before zh translation finishes loading
- Level/book progress bar layout and strength stats alignment

### Database
- Alembic through `020_book_title_source`

## 0.1.0 — 2026-08-04

- Phase 2 Loop MVP on `main`: family word bank, daily challenge, SRS strength, readiness
