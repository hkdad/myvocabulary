# Book as Word Bank (v1)

Product rules for uploading a book and feeding Daily Challenge. Complements
[ADR 003](./adr/003-book-word-bank.md).

## Goal

Parent uploads a **level-matched** book (txt / epub). The app builds a study set from
that book's own coverage curve. The child's Daily Challenge drips those words while
keeping baseline retention warm. Parent sees **Book progress** and **Page coverage**.

## Flow

1. Parent uploads txt or epub → parse preview (not yet a word list).
2. Preview shows tokens, content lemmas, 80%/90% caps, baseline matches, time estimate.
3. Parent confirms (default 80% cap, optional 90%) → `WordList(source=book)` + items.
4. Parent activates the book for one child (one active book per learner).
5. Daily Challenge: **new = book study set (level-filtered)**, **retention = family bank SRS**.
6. Closing the assignment restores bank drip.

## Study set

Content lemmas ranked by frequency. Take the shortest prefix that covers
`coverage_target` of content-token mass. Hidden lemmas are excluded.

New uploads skip content lemmas shorter than three letters (after function-word
filtering) to reduce HTML fragments and junk tokens.

## Suspicious word review

On the parent Books page, **Find suspicious words** scans the full lemma list for:

- Single-letter tokens
- HTML-like fragments (`em`, `br`, `div`, …)
- Very short tokens (under three letters)
- Broken fallback lemmatization (e.g. `consciou`)

Parents review the list and **hide** selected lemmas. Hiding removes them from the
study set (and from the confirmed `WordList` when applicable). Hidden lemmas can be
unhidden from the same panel.

## Family word bank definitions

On **Family word bank**, parents see how many CSV-imported words still lack
definitions. **Fill missing definitions** starts a background job that looks up
glosses without blocking the page. Use **Missing definitions only** to filter the
table while the job runs.

## Book definitions (all books)

On **Books**, the header shows how many words across all confirmed books still
need English glosses. **Fill English definitions** runs a background job via the
dictionary API. Traditional Chinese is filled lazily during practice.

## EPUB text extraction

EPUB uploads are parsed with **ebooklib** (spine reading order) and **lxml** DOM
text extraction. Adjacent HTML spans stay as one word (`consci` + `ous` →
`conscious`), and soft hyphens / line-break hyphens are normalized before
tokenization. The fallback lemmatizer keeps whole words like `something` and
`nothing` (no more `someth` / `noth` junk).

Uploaded book files (epub/txt) are kept on disk under `data/books/<book_id>/`
for debugging and re-analysis.

Minimal or malformed EPUB zips fall back to the older regex stripper so uploads
still work.

**Re-upload required:** lemmas are built at preview/confirm time. If a book was
confirmed before this fix, delete it and upload the EPUB again — definition fill
cannot repair split-word junk already stored as lemmas.

## New-word level filter

Book study lemmas do not carry their own CEFR tags. When a lemma also exists in the
family bank, that bank `level` is used to filter **new drip only**:

- Keep bank-tagged lemmas at **or above** the learner's current CEFR.
- Drop bank-tagged lemmas **below** the learner's current CEFR.
- Keep **unbanked** study lemmas (no family-bank row) — they are book-specific vocabulary.

If every bank-tagged study lemma is below level and there are no unbanked lemmas left,
the mix is **retention-only** for that day (`book_new_drip_empty=true`). Retention is
unchanged (any released SRS, including lower bands).


## Out of v1

PDF parsing, auto book progression, lemma surface-variant table, frequency-sorted
drip beyond rank-at-confirm, book covers / ebook metadata.

## Deploy note

Book parsing uses spaCy (`en_core_web_sm`), installed with the backend dependencies.
If spaCy is missing, analysis falls back to a naive tokenizer — lemmas like `continu`
(from `continued`) can appear. Re-upload a book after installing spaCy to refresh lemmas.
