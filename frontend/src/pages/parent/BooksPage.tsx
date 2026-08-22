import { type ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  assignBook,
  confirmBook,
  deleteBook,
  getBook,
  getBookProgress,
  hideBookLemma,
  listBooks,
  previewBook,
  unassignBook,
  updateBookTitle,
  type BookProgress,
  type BookSummary,
} from "../../api/books";
import { listLearners, type LearnerProfile } from "../../api/learners";
import LearnerAvatar from "../../components/LearnerAvatar";
import PageShell from "../../components/PageShell";

function coverageLabel(target: number): string {
  return target >= 0.9 ? "Read independently (90%)" : "Read with help (80%)";
}

function statusBadge(status: string, coverageTarget: number) {
  if (status === "confirmed") {
    return (
      <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">
        {coverageLabel(coverageTarget)}
      </span>
    );
  }
  return (
    <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">
      Preview — not confirmed yet
    </span>
  );
}

function ConfirmStudySetButtons({
  confirming,
  titleDraft,
  onConfirm,
}: {
  confirming: boolean;
  titleDraft: string;
  onConfirm: (target: number) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        type="button"
        disabled={confirming || !titleDraft.trim()}
        onClick={() => onConfirm(0.8)}
        className="warm-btn warm-btn-primary text-sm"
      >
        {confirming ? "Confirming…" : "Confirm 80% · read with help"}
      </button>
      <button
        type="button"
        disabled={confirming || !titleDraft.trim()}
        onClick={() => onConfirm(0.9)}
        className="warm-btn text-sm"
      >
        Confirm 90% · read independently
      </button>
    </div>
  );
}
function stepState(
  selected: BookSummary | null,
): { upload: boolean; confirm: boolean; assign: boolean } {
  if (!selected) {
    return { upload: true, confirm: false, assign: false };
  }
  if (selected.status === "preview") {
    return { upload: true, confirm: true, assign: false };
  }
  return {
    upload: true,
    confirm: true,
    assign: selected.assigned_learner_ids.length === 0,
  };
}

export default function BooksPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [learners, setLearners] = useState<LearnerProfile[]>([]);
  const [selected, setSelected] = useState<BookSummary | null>(null);
  const [progress, setProgress] = useState<BookProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [savingTitle, setSavingTitle] = useState(false);
  const [titleSaved, setTitleSaved] = useState(false);
  const [assigningId, setAssigningId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [titleDraft, setTitleDraft] = useState("");
  const [hidingLemmaId, setHidingLemmaId] = useState<number | null>(null);
  const assignSectionRef = useRef<HTMLDivElement>(null);

  const steps = stepState(selected);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [bookRows, learnerRows] = await Promise.all([listBooks(), listLearners()]);
      setBooks(bookRows);
      setLearners(learnerRows.filter((row) => row.is_active));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load books");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (selected) {
      setTitleDraft(selected.title);
      setTitleSaved(false);
    }
  }, [selected?.id, selected?.title]);

  async function openBook(bookId: number) {
    setError(null);
    try {
      const detail = await getBook(bookId);
      setSelected(detail);
      setTitleDraft(detail.title);
      if (detail.status === "confirmed") {
        setProgress(await getBookProgress(bookId));
      } else {
        setProgress([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load book");
    }
  }

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const preview = await previewBook(file);
      setSelected(preview);
      setTitleDraft(preview.title);
      setProgress([]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse book");
    } finally {
      setUploading(false);
    }
  }

  async function saveTitle() {
    if (!selected || !titleDraft.trim()) {
      return;
    }
    if (titleDraft.trim() === selected.title) {
      return;
    }
    setSavingTitle(true);
    setTitleSaved(false);
    setError(null);
    try {
      const updated = await updateBookTitle(selected.id, titleDraft.trim());
      setSelected(updated);
      setTitleDraft(updated.title);
      setBooks((rows) => rows.map((row) => (row.id === updated.id ? { ...row, ...updated } : row)));
      setTitleSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save title");
    } finally {
      setSavingTitle(false);
    }
  }

  async function handleConfirm(coverageTarget: number) {
    if (!selected) {
      return;
    }
    if (!titleDraft.trim()) {
      setError("Enter a book name before confirming.");
      return;
    }
    setConfirming(true);
    setError(null);
    try {
      const confirmed = await confirmBook(selected.id, coverageTarget, titleDraft.trim());
      setSelected(confirmed);
      setTitleDraft(confirmed.title);
      if (confirmed.status === "confirmed") {
        setProgress(await getBookProgress(confirmed.id));
      }
      await load();
      assignSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm book");
    } finally {
      setConfirming(false);
    }
  }

  async function handleAssign(learnerId: number) {
    if (!selected) {
      return;
    }
    setAssigningId(learnerId);
    setError(null);
    try {
      await assignBook(selected.id, learnerId);
      setSelected(await getBook(selected.id));
      setProgress(await getBookProgress(selected.id));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign book");
    } finally {
      setAssigningId(null);
    }
  }

  async function handleUnassign(learnerId: number) {
    if (!selected) {
      return;
    }
    setError(null);
    try {
      await unassignBook(selected.id, learnerId);
      setSelected(await getBook(selected.id));
      setProgress(await getBookProgress(selected.id));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not close book");
    }
  }

  async function handleDelete(bookId: number, bookTitle: string) {
    const label = bookTitle || "this book";
    if (
      !window.confirm(
        `Delete "${label}"? Daily challenge will stop dripping these words. This cannot be undone.`,
      )
    ) {
      return;
    }
    setDeletingId(bookId);
    setError(null);
    try {
      await deleteBook(bookId);
      if (selected?.id === bookId) {
        setSelected(null);
        setProgress([]);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete book");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleHideLemma(lemmaId: number, hidden: boolean) {
    if (!selected) {
      return;
    }
    setHidingLemmaId(lemmaId);
    setError(null);
    try {
      const updated = await hideBookLemma(selected.id, lemmaId, hidden);
      setSelected(updated);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update word");
    } finally {
      setHidingLemmaId(null);
    }
  }

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Parent</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Books 📗</h1>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Upload → name & confirm → assign to a child. Their daily challenge drips book words;
              bank retention stays warm.
            </p>
          </div>
          <Link to="/parent/dashboard" className="warm-btn warm-btn-secondary text-sm">
            Back to dashboard
          </Link>
        </header>

        <section className="warm-card p-4">
          <ol className="flex flex-wrap gap-4 text-sm">
            <li className={steps.upload ? "font-bold text-warm-brown" : "text-warm-muted"}>
              1. Upload
            </li>
            <li className={steps.confirm ? "font-bold text-warm-brown" : "text-warm-muted"}>
              2. Name & confirm
            </li>
            <li className={steps.assign ? "font-bold text-warm-coral" : "text-warm-muted"}>
              3. Assign to child
            </li>
          </ol>
        </section>

        {error && <p className="font-semibold text-red-600">{error}</p>}

        <section className="warm-card bg-gradient-to-br from-emerald-50/90 to-teal-50/90 p-6">
          <div className="flex flex-wrap items-start gap-4">
            <span className="text-4xl">📗</span>
            <div className="min-w-0 flex-1">
              <h2 className="text-xl font-extrabold text-warm-brown">Step 1 · Upload a book</h2>
              <p className="mt-1 text-sm text-warm-body">
                txt or epub — pick a book at your child&apos;s level. PDF comes later.
              </p>
              <label
                className={`warm-btn warm-btn-primary mt-4 inline-flex cursor-pointer text-sm ${uploading ? "pointer-events-none opacity-60" : ""}`}
              >
                {uploading ? "Parsing…" : "Choose file"}
                <input
                  type="file"
                  accept=".txt,.epub,text/plain,application/epub+zip"
                  className="hidden"
                  disabled={uploading}
                  onChange={(event) => void handleUpload(event)}
                />
              </label>
            </div>
          </div>
        </section>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Library</h2>
          {loading && <p className="mt-4 text-sm text-warm-brown-soft">Loading books…</p>}
          {!loading && books.length === 0 && (
            <p className="mt-4 text-sm text-warm-brown-soft">
              No books yet — upload a txt or epub to get started.
            </p>
          )}
          <ul className="mt-4 space-y-2">
            {books.map((book) => (
              <li key={book.id} className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void openBook(book.id)}
                  className={`flex min-w-0 flex-1 items-start justify-between gap-3 rounded-2xl p-4 text-left transition ${
                    selected?.id === book.id
                      ? "bg-white/90 ring-2 ring-warm-coral/30"
                      : "bg-white/70 hover:bg-white/90"
                  }`}
                >
                  <span className="min-w-0">
                    <span className="font-extrabold text-warm-brown">{book.title}</span>
                    <span className="mt-1 block text-sm text-warm-brown-soft">
                      {book.original_filename} · {book.study_lemma_count.toLocaleString()} study
                      words
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-2">
                    {statusBadge(book.status, book.coverage_target)}
                    <span className="text-xs font-semibold text-warm-muted">
                      {book.assigned_learner_ids.length} assigned
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  disabled={deletingId === book.id}
                  onClick={() => void handleDelete(book.id, book.title)}
                  className="shrink-0 self-center px-2 text-sm font-semibold text-red-600 disabled:opacity-50"
                  title="Delete book"
                >
                  {deletingId === book.id ? "…" : "Delete"}
                </button>
              </li>
            ))}
          </ul>
        </section>

        {selected && (
          <section className="warm-card p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-extrabold text-warm-brown">
                  Step 2 · Name &amp; confirm study set
                </h2>
                <div className="mt-2">{statusBadge(selected.status, selected.coverage_target)}</div>
              </div>
              <button
                type="button"
                disabled={deletingId === selected.id}
                onClick={() => void handleDelete(selected.id, selected.title)}
                className="text-sm font-semibold text-red-600 disabled:opacity-50"
              >
                {deletingId === selected.id ? "Deleting…" : "Delete book"}
              </button>
            </div>

            <div className="mt-4 flex flex-wrap items-end gap-2">
              <label className="min-w-[12rem] flex-1">
                <span className="text-sm font-bold text-warm-muted">Book name</span>
                <input
                  className="warm-input mt-1 w-full"
                  value={titleDraft}
                  onChange={(event) => {
                    setTitleDraft(event.target.value);
                    setTitleSaved(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      void saveTitle();
                    }
                  }}
                  placeholder="Enter the book title"
                />
              </label>
              <button
                type="button"
                disabled={savingTitle || !titleDraft.trim() || titleDraft.trim() === selected.title}
                onClick={() => void saveTitle()}
                className="warm-btn warm-btn-secondary text-sm"
              >
                {savingTitle ? "Saving…" : "Save"}
              </button>
            </div>
            {titleSaved && (
              <p className="mt-2 text-sm font-semibold text-emerald-700">Book name saved.</p>
            )}
            {selected.title_needs_review && (
              <p className="mt-2 text-sm font-semibold text-amber-800">
                We couldn&apos;t find a title in the file — please enter the book name above.
              </p>
            )}
            {selected.title_source === "content" || selected.title_source === "metadata" ? (
              <p className="mt-2 text-sm text-warm-brown-soft">
                Name read from the book file. Edit if it looks wrong.
              </p>
            ) : null}
            <p className="mt-1 text-xs text-warm-muted">File: {selected.original_filename}</p>

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <article className="rounded-2xl bg-white/70 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-warm-muted">Tokens</p>
                <p className="mt-1 text-lg font-extrabold text-warm-brown">
                  {selected.token_count.toLocaleString()}
                </p>
              </article>
              <article className="rounded-2xl bg-white/70 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-warm-muted">
                  Content lemmas
                </p>
                <p className="mt-1 text-lg font-extrabold text-warm-brown">
                  {selected.content_lemma_count.toLocaleString()}
                </p>
              </article>
              <article className="rounded-2xl bg-white/70 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-warm-muted">
                  Words at 80% (preview)
                </p>
                <p className="mt-1 text-lg font-extrabold text-warm-brown">
                  {selected.coverage_curve["80"] ?? "—"} lemmas
                </p>
              </article>
              <article className="rounded-2xl bg-white/70 p-4">
                <p className="text-xs font-bold uppercase tracking-wide text-warm-muted">
                  Words at 90% (preview)
                </p>
                <p className="mt-1 text-lg font-extrabold text-warm-brown">
                  {selected.coverage_curve["90"] ?? "—"} lemmas
                </p>
              </article>
            </div>

            {(selected.baseline_match_count ?? 0) > 0 && (
              <p className="mt-4 text-sm text-warm-body">
                {selected.baseline_match_count} already in the family word bank ·{" "}
                {selected.new_word_count} new
              </p>
            )}

            {selected.status === "preview" && (
              <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50/80 p-4">
                <h3 className="text-sm font-bold text-amber-900">Confirm study set</h3>
                <p className="mt-1 text-sm text-amber-900/80">
                  The stats above are a preview only. Tap <strong>Confirm</strong> to lock in how
                  many words to teach — then you can assign to a child below.
                </p>
                <ConfirmStudySetButtons
                  confirming={confirming}
                  titleDraft={titleDraft}
                  onConfirm={(target) => void handleConfirm(target)}
                />
              </div>
            )}

            {selected.status === "confirmed" && (
              <p className="mt-4 rounded-2xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
                Study set confirmed ({coverageLabel(selected.coverage_target).toLowerCase()}) —
                scroll down to assign to a child.
              </p>
            )}

            {selected.sample_study && selected.sample_study.length > 0 && selected.status === "preview" && (
              <div className="mt-6">
                <h3 className="text-sm font-bold text-warm-muted">Study set sample</h3>
                <ul className="mt-2 divide-y divide-orange-100 rounded-2xl bg-white/70 px-4">
                  {selected.sample_study.slice(0, 20).map((row) => (
                    <li key={row.id} className="flex items-center justify-between gap-3 py-3">
                      <span className="text-sm text-warm-brown-soft">
                        <span className="font-semibold text-warm-brown">{row.lemma}</span>
                        {row.matched_baseline ? " · in bank" : ""}
                      </span>
                      {!row.is_hidden && (
                        <button
                          type="button"
                          disabled={hidingLemmaId === row.id}
                          onClick={() => void handleHideLemma(row.id, true)}
                          className="text-xs font-semibold text-warm-muted hover:text-red-600"
                        >
                          {hidingLemmaId === row.id ? "…" : "Hide"}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div ref={assignSectionRef} className="mt-8 border-t border-orange-100 pt-6">
              <h3 className="text-lg font-extrabold text-warm-brown">Step 3 · Assign to a child</h3>
              {selected.status !== "confirmed" ? (
                <>
                  <p className="mt-2 text-sm text-amber-800">
                    Assignment unlocks after you confirm the study set. The &ldquo;80%&rdquo; number
                    in the stats is only a preview — tap one of the Confirm buttons above.
                  </p>
                  <ConfirmStudySetButtons
                    confirming={confirming}
                    titleDraft={titleDraft}
                    onConfirm={(target) => void handleConfirm(target)}
                  />
                </>
              ) : learners.length === 0 ? (
                <p className="mt-2 text-sm text-warm-brown-soft">
                  No active learners —{" "}
                  <Link to="/parent/learners" className="text-warm-link underline">
                    add a learner
                  </Link>{" "}
                  first.
                </p>
              ) : (
                <>
                  <p className="mt-2 text-sm text-warm-brown-soft">
                    Tap a child to make this their active book. Daily challenge will drip new words
                    from this book.
                  </p>
                  <ul className="mt-4 space-y-2">
                    {learners.map((learner) => {
                      const isAssigned = selected.assigned_learner_ids.includes(learner.id);
                      const row = progress.find((item) => item.learner_id === learner.id);
                      return (
                        <li
                          key={learner.id}
                          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white/70 p-4"
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            <LearnerAvatar learner={learner} size="sm" />
                            <span>
                              <span className="font-semibold text-warm-brown">
                                {learner.display_name}
                              </span>
                              <span className="mt-1 block text-sm text-warm-brown-soft">
                                {learner.english_level}
                                {row && (
                                  <>
                                    {" "}
                                    · Book progress {row.study_progress_percent}% · Page coverage{" "}
                                    {row.page_coverage_percent}%
                                    {row.ready_to_read ? " · ready to read ✓" : ""}
                                  </>
                                )}
                              </span>
                            </span>
                          </div>
                          {isAssigned ? (
                            <button
                              type="button"
                              onClick={() => void handleUnassign(learner.id)}
                              className="warm-btn warm-btn-secondary text-sm text-red-700"
                            >
                              Close book
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={assigningId === learner.id}
                              onClick={() => void handleAssign(learner.id)}
                              className="warm-btn warm-btn-primary text-sm"
                            >
                              {assigningId === learner.id ? "Assigning…" : "Assign to this child"}
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
          </section>
        )}
      </main>
    </PageShell>
  );
}
