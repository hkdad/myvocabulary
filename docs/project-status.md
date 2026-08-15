# Project Status

**Last updated:** 2026-08-04  
**Status:** Phase 2 P2.0 Loop MVP shipped on `main` · recognition-first + readiness-gated Level-up · P2.1 polish in progress  
**Latest merges:** #31 readiness gate + Max seed · #30 Mastered@3 days + word progress · #29 CERT docs/UX · #26–#28 lazy 繁中, recognition-first loop, MC challenges  

**Test accounts:** `parent`/`parent123`, `mia`/`mia`, `leo`/`leo`, `max`/`max`

---

## Phase 1 milestones (complete)

| Milestone | Sprint | Status |
|-----------|--------|--------|
| M0 Scaffold | Sprint 0 | ✅ |
| M1 Login | Sprint 1 | ✅ |
| M2 Dictionary | Sprint 2 | ✅ |
| M3 Lists | Sprint 3 | ✅ |
| M4 Learn (SRS) | Sprint 4 | ✅ |
| M5 Dictate | Sprint 5 | ✅ |
| M6 Ship (Docker) | Sprint 6 | ✅ |
| M7 Engage (AI + challenges) | Sprint 7 | ✅ |

---

## Phase 2 milestones

| Milestone | Sprint | Status |
|-----------|--------|--------|
| Spec + plan | Docs | ✅ |
| M8 Loop MVP | P2.0 | ✅ Shipped |
| M9 Polish | P2.1 | 🔄 In progress |
| M10 Smart assist | P2.2 | ⏳ |

**Phase 2 focus:** family word bank (CSV), Loop Engine (drip + retention mix), soft daily challenge,
strength dashboards, **recognition-first pedagogy** (CERT-style), lazy 繁中 on MCQ, level readiness
benchmarks, MC level-up challenges gated at readiness ≥ 75%.

See [phase-2-spec.md](./phase-2-spec.md) §1.6 (pedagogy) and §5.3 (readiness).

---

## Shipped on `main` (through 2026-08-04)

### Learning loop
- Family word bank CSV upload (parent UI)
- Loop Engine: new-word drip + learning/familiar + mastered retention mix
- Soft Daily Challenge — **completes on SRS recognition review** (not dictation)
- Optional bonus spelling (Listen & Pick + typed dictation) tracked separately
- Mistake practice: recognition review + mandatory spelling (max 5 words)
- Strength: Learning (1 day) / Familiar (2 days) / Mastered (3+ days) from distinct recognition reviews

### Readiness & Level-up
- Parent readiness gauge (accuracy, breadth, retention, consistency, category balance)
- Vocabulary breadth = Familiar+ bank words at current level (honest familiar/mastered copy)
- Level-up exam: **30** MCQ, pass ≥ **80%**; unlocks at readiness ≥ **75%** or parent-accepted assessment
- Parent Accept still owns `english_level` change; exam pass awards badge

### UX & language
- Lazy Traditional Chinese on review/challenge MCQ (`useLazyDefinitionChoices`)
- Level progress card + `/app/words` learning figures
- Level-up / streak challenges use multiple-choice recognition (not typing)
- Kid home prioritizes Listen & Pick over typed dictation
- Seed includes Max (`max`/`max`, PRE-A1, kid) for easy local testing

### Phase 1 (still active)
- Parent + learner auth (JWT + refresh)
- English dictionary + TTS + lazy 繁中 lookup
- Curated/custom word lists + per-child assignment
- SM-2 spaced repetition flashcards
- Dictation (kid Listen & Pick / teen typed — both bonus for daily progress)
- Parent dashboard + learner stats
- AI level assessment + challenges
- Docker deployment via `./start.sh`

---

*See [project-plan.md](./project-plan.md) for full roadmap.*
