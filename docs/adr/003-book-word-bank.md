# ADR 003 — Book as Word Bank

**Status:** Accepted  
**Date:** 2026-08-22

## Context

Parents upload a level-appropriate book so Daily Challenge drips words the child will
meet on the page. The family word bank, SRS cards, and shared `DictionaryEntry` rows
already exist. Sherlock Holmes coverage numbers in the research note are a **pipeline
anchor only** — not a kid reading target.

## Decisions

### 1. Hybrid daily mix (Decision #9)

Book mode replaces **new-word drip**, not the whole challenge.

- New cards come from the learner's **active book** study set, filtered by family-bank
  CEFR: keep lemmas **at or above** the learner's level; keep **unbanked** lemmas;
  drop below-level bank tags. Empty filter → retention-only day (`book_new_drip_empty`).
- Retention cards still come from **baseline family-bank SRS** (any released level).
- Daily challenge shell (recognition SRS + Listen & Pick) is unchanged.

Closing the book assignment restores normal bank drip.

### 2. Study cap is per-book, default 80% content coverage (Decision #10)

Parse Preview shows this book's coverage curve (50 / 80 / 90 / 95%).

- Default study set = lemmas needed for **80% of content tokens** ("Read with help").
- Parent may raise the cap to **90%** ("Read independently") before confirm.
- Function words and proper nouns are skipped (not taught as cards).
- Words already in the family bank share the same `DictionaryEntry` / SRS card.

Sherlock 90% content ≈ 3,340 is research validation, not a product default.

### 3. Two progress metrics — not "Level Readiness" (Decision #12)

Do **not** reuse the CEFR Level Readiness gauge name.

| Metric | Formula | UI name |
|--------|---------|---------|
| Study Progress | known study-set lemmas ÷ study-set size | **Book progress** |
| Page Coverage | known content lemmas ÷ all content lemmas | **Page coverage** |

"Known" = SRS strength is learning, familiar, or mastered (at least one correct
review day). Baseline overlap counts as free progress.

**Ready to read** = Page coverage ≥ 80%.

Kid home shows **Book progress** (not "Book Quest" — Quests already means CEFR packs).

### 4. Lemma-only cards in v1 (Decision #5, deferred variants)

One card per lemma. Surface forms (`woke` → `wake`) are **not** stored in v1.
Revisit a variants table after the loop slice is stable.

### 5. Definitions on drip, not on card open

Lazy means "not at upload time". When a book word is released into today's mix,
fill a placeholder definition **before** the mix is returned (Ollama kid-friendly
JSON first, `fetch_from_api` fallback). Kids never wait on a spinner for a gloss.

## Consequences

- `WordList.source="book"` plus a `books` metadata table.
- Loop engine must split drip allowlist from retention allowlist.
- spaCy is optional; a fallback tokenizer/lemmatizer keeps tests and CI offline.
