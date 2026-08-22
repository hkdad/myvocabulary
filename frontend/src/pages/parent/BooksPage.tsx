import { type ChangeEvent, type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  assignBook,
  confirmBook,
  getBook,
  getBookProgress,
  listBooks,
  previewBook,
  unassignBook,
  type BookProgress,
  type BookSummary,
} from "../../api/books";
import { listLearners, type LearnerProfile } from "../../api/learners";
import PageShell from "../../components/PageShell";

function coverageLabel(target: number): string {
  return target >= 0.9 ? "Read independently (90%)" : "Read with help (80%)";
}

export default function BooksPage() {
  const [books, setBooks] = useState<BookSummary[]>([]);
  const [learners, setLearners] = useState<LearnerProfile[]>([]);
  const [selected, setSelected] = useState<BookSummary | null>(null);
  const [progress, setProgress] = useState<BookProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assignId, setAssignId] = useState<number | "">("");

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

  async function openBook(bookId: number) {
    setError(null);
    try {
      const detail = await getBook(bookId);
      setSelected(detail);
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
      setProgress([]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not parse book");
    } finally {
      setUploading(false);
    }
  }

  async function handleConfirm(coverageTarget: number) {
    if (!selected) {
      return;
    }
    setConfirming(true);
    setError(null);
    try {
      const confirmed = await confirmBook(selected.id, coverageTarget);
      setSelected(confirmed);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not confirm book");
    } finally {
      setConfirming(false);
    }
  }

  async function handleAssign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || assignId === "") {
      return;
    }
    setError(null);
    try {
      const updated = await assignBook(selected.id, assignId);
      setSelected(await getBook(updated.id));
      setProgress(await getBookProgress(updated.id));
      setAssignId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign book");
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

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Parent</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Books</h1>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Upload a level-matched book. Daily challenge drips those words; bank retention stays
              warm.
            </p>
          </div>
          <Link to="/parent/dashboard" className="text-sm font-semibold text-warm-link">
            Dashboard
          </Link>
        </header>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Upload</h2>
          <p className="mt-1 text-sm text-warm-brown-soft">txt or epub. PDF comes later.</p>
          <label className="warm-btn warm-btn-primary mt-4 inline-flex cursor-pointer text-sm">
            {uploading ? "Parsing…" : "Choose file"}
            <input
              type="file"
              accept=".txt,.epub,text/plain,application/epub+zip"
              className="hidden"
              disabled={uploading}
              onChange={(event) => void handleUpload(event)}
            />
          </label>
        </section>

        {error && (
          <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">{error}</p>
        )}

        {loading && <p className="text-sm font-semibold text-warm-muted">Loading books…</p>}

        <section className="grid gap-4 lg:grid-cols-2">
          <div className="warm-card p-6">
            <h2 className="text-lg font-extrabold text-warm-brown">Library</h2>
            {books.length === 0 && !loading && (
              <p className="mt-3 text-sm text-warm-brown-soft">No books yet.</p>
            )}
            <ul className="mt-3 divide-y divide-orange-100">
              {books.map((book) => (
                <li key={book.id}>
                  <button
                    type="button"
                    onClick={() => void openBook(book.id)}
                    className="flex w-full items-start justify-between gap-3 py-3 text-left"
                  >
                    <span>
                      <span className="font-extrabold text-warm-brown">{book.title}</span>
                      <span className="mt-1 block text-sm text-warm-brown-soft">
                        {book.status === "confirmed" ? coverageLabel(book.coverage_target) : "Preview"}{" "}
                        · {book.study_lemma_count.toLocaleString()} study words · ~
                        {book.days_at_five_new} days at 5/day
                      </span>
                    </span>
                    <span className="text-sm font-semibold text-warm-muted">
                      {book.assigned_learner_ids.length} assigned
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          {selected && (
            <div className="warm-card p-6">
              <h2 className="text-lg font-extrabold text-warm-brown">{selected.title}</h2>
              <p className="mt-2 text-sm text-warm-brown-soft">
                {selected.token_count.toLocaleString()} tokens ·{" "}
                {selected.content_lemma_count.toLocaleString()} content lemmas · skipped{" "}
                {selected.skipped_function_words.toLocaleString()} function words and{" "}
                {selected.skipped_proper_nouns.toLocaleString()} names
              </p>
              <p className="mt-2 text-sm text-warm-body">
                Coverage curve: 80% = {selected.coverage_curve["80"] ?? "—"} lemmas, 90% ={" "}
                {selected.coverage_curve["90"] ?? "—"} lemmas
              </p>
              {(selected.baseline_match_count ?? 0) > 0 && (
                <p className="mt-2 text-sm text-warm-body">
                  {selected.baseline_match_count} already in the family dictionary ·{" "}
                  {selected.new_word_count} new
                </p>
              )}

              {selected.status === "preview" && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={confirming}
                    onClick={() => void handleConfirm(0.8)}
                    className="warm-btn warm-btn-primary text-sm"
                  >
                    Confirm 80% · read with help
                  </button>
                  <button
                    type="button"
                    disabled={confirming}
                    onClick={() => void handleConfirm(0.9)}
                    className="warm-btn text-sm"
                  >
                    Confirm 90% · read independently
                  </button>
                </div>
              )}

              {selected.sample_study && selected.sample_study.length > 0 && (
                <div className="mt-4">
                  <p className="text-sm font-bold text-warm-muted">Study set sample</p>
                  <p className="mt-1 text-sm text-warm-brown-soft">
                    {selected.sample_study
                      .slice(0, 12)
                      .map((row) => row.lemma)
                      .join(", ")}
                  </p>
                </div>
              )}

              {selected.status === "confirmed" && (
                <>
                  <form onSubmit={handleAssign} className="mt-4 flex flex-wrap gap-2">
                    <select
                      className="warm-input max-w-xs"
                      value={assignId}
                      onChange={(event) =>
                        setAssignId(event.target.value ? Number(event.target.value) : "")
                      }
                    >
                      <option value="">Select learner</option>
                      {learners.map((learner) => (
                        <option key={learner.id} value={learner.id}>
                          {learner.display_name} · {learner.english_level}
                        </option>
                      ))}
                    </select>
                    <button type="submit" className="warm-btn warm-btn-primary text-sm">
                      Make active book
                    </button>
                  </form>
                  <ul className="mt-3 divide-y divide-orange-100">
                    {selected.assigned_learner_ids.map((learnerId) => {
                      const learner = learners.find((row) => row.id === learnerId);
                      const row = progress.find((item) => item.learner_id === learnerId);
                      return (
                        <li key={learnerId} className="flex items-center justify-between gap-3 py-3">
                          <span>
                            <span className="font-semibold text-warm-brown">
                              {learner?.display_name ?? `Learner #${learnerId}`}
                            </span>
                            {row && (
                              <span className="mt-1 block text-sm text-warm-brown-soft">
                                Book progress {row.study_progress_percent}% · Page coverage{" "}
                                {row.page_coverage_percent}%
                                {row.ready_to_read ? " · ready to read" : ""}
                              </span>
                            )}
                          </span>
                          <button
                            type="button"
                            onClick={() => void handleUnassign(learnerId)}
                            className="text-sm font-semibold text-red-600"
                          >
                            Close book
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
          )}
        </section>
      </main>
    </PageShell>
  );
}
