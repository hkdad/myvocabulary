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
5. Daily Challenge: **new = book study set**, **retention = family bank SRS**.
6. Closing the assignment restores bank drip.

## Study set

Content lemmas ranked by frequency. Take the shortest prefix that covers
`coverage_target` of content-token mass. Hidden lemmas are excluded.

## Out of v1

PDF parsing, auto book progression, lemma surface-variant table, frequency-sorted
drip beyond rank-at-confirm, book covers / ebook metadata.
