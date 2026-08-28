import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  bankCategoriesFromSummary,
  bankLevelsFromSummary,
  cancelDefinitionFillJob,
  deleteWordBank,
  getCurrentDefinitionFillJob,
  getWordBankItems,
  getWordBankSummary,
  startDefinitionFillJob,
  type DefinitionFillJob,
  type WordBankItem,
  type WordBankSummary,
} from "../../api/loop";
import PageShell from "../../components/PageShell";
import { isPlaceholderDefinition } from "../../lib/placeholderDefinition";

const ACTIVE_JOB_STATUSES = new Set(["queued", "running"]);

export default function WordBankPage() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<WordBankSummary | null>(null);
  const [items, setItems] = useState<WordBankItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [placeholdersOnly, setPlaceholdersOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [fillJob, setFillJob] = useState<DefinitionFillJob | null>(null);
  const [startingFill, setStartingFill] = useState(false);

  const pageSize = 50;
  const levelOptions = summary ? bankLevelsFromSummary(summary.by_level) : [];
  const categoryOptions = summary ? bankCategoriesFromSummary(summary.by_category) : [];
  const jobActive = fillJob !== null && ACTIVE_JOB_STATUSES.has(fillJob.status);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setItemsError(null);
    try {
      const [bankSummary, currentJob] = await Promise.all([
        getWordBankSummary(),
        getCurrentDefinitionFillJob(),
      ]);
      setSummary(bankSummary);
      setFillJob(currentJob);

      try {
        const pageData = await getWordBankItems({
          level: level || undefined,
          category: category || undefined,
          q: search || undefined,
          page,
          page_size: pageSize,
          placeholders_only: placeholdersOnly || undefined,
        });
        setItems(pageData.items);
        setTotal(pageData.total);
        setTotalPages(pageData.total_pages);
      } catch (err) {
        setItems([]);
        setTotal(bankSummary.total_items);
        setTotalPages(0);
        const message = err instanceof Error ? err.message : "Failed to load words";
        setItemsError(
          bankSummary.total_items > 0
            ? `${message} Your bank has ${bankSummary.total_items.toLocaleString()} words — try refreshing the page.`
            : message,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load word bank");
    } finally {
      setLoading(false);
    }
  }, [category, level, page, placeholdersOnly, search]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!jobActive) {
      return;
    }
    const timer = window.setInterval(() => {
      void getCurrentDefinitionFillJob()
        .then((job) => {
          setFillJob(job);
          if (job && !ACTIVE_JOB_STATUSES.has(job.status)) {
            void load();
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [jobActive, load]);

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setSearch(searchInput.trim());
  }

  function clearFilters() {
    setLevel("");
    setCategory("");
    setSearch("");
    setSearchInput("");
    setPlaceholdersOnly(false);
    setPage(1);
  }

  async function handleStartFill() {
    setStartingFill(true);
    setError(null);
    try {
      const job = await startDefinitionFillJob();
      setFillJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start definition fill");
    } finally {
      setStartingFill(false);
    }
  }

  async function handleCancelFill() {
    if (!fillJob) {
      return;
    }
    try {
      const job = await cancelDefinitionFillJob(fillJob.id);
      setFillJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel job");
    }
  }

  async function handleDelete() {
    if (!summary?.total_items) {
      return;
    }
    const confirmed = window.confirm(
      `Delete all ${summary.total_items.toLocaleString()} words from the family bank? Kids' review progress for these words will be removed. This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteWordBank();
      navigate("/parent/word-lists");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete word bank");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Parent</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Family word bank</h1>
            {summary && (
              <p className="mt-1 text-sm text-warm-brown-soft">
                {summary.total_items.toLocaleString()} words uploaded
                {summary.placeholder_count > 0 && (
                  <>
                    {" "}
                    · {summary.placeholder_count.toLocaleString()} missing definitions
                  </>
                )}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {summary && summary.placeholder_count > 0 && (
              <button
                type="button"
                className="warm-btn warm-btn-primary text-sm"
                disabled={startingFill || jobActive}
                onClick={() => void handleStartFill()}
              >
                {startingFill
                  ? "Starting…"
                  : jobActive
                    ? "Filling definitions…"
                    : "Fill missing definitions"}
              </button>
            )}
            {summary && summary.total_items > 0 && (
              <button
                type="button"
                className="text-sm font-semibold text-red-600 disabled:opacity-50"
                disabled={deleting}
                onClick={() => void handleDelete()}
              >
                {deleting ? "Deleting…" : "Delete bank"}
              </button>
            )}
            <Link to="/parent/word-lists" className="warm-btn warm-btn-secondary text-sm">
              Back to word lists
            </Link>
          </div>
        </header>

        {error && <p className="font-semibold text-red-600">{error}</p>}
        {itemsError && <p className="font-semibold text-red-600">{itemsError}</p>}

        {fillJob && (jobActive || fillJob.status === "completed" || fillJob.status === "failed") && (
          <section className="warm-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-bold text-warm-brown">Definition fill job</p>
                <p className="mt-1 text-sm text-warm-brown-soft">
                  {fillJob.filled.toLocaleString()} filled · {fillJob.failed.toLocaleString()}{" "}
                  failed · {fillJob.processed.toLocaleString()} / {fillJob.total.toLocaleString()}{" "}
                  processed
                </p>
                {fillJob.status === "failed" && fillJob.error_message && (
                  <p className="mt-1 text-sm text-red-600">{fillJob.error_message}</p>
                )}
              </div>
              {jobActive && (
                <button
                  type="button"
                  className="warm-btn warm-btn-secondary text-sm"
                  onClick={() => void handleCancelFill()}
                >
                  Cancel
                </button>
              )}
            </div>
            {fillJob.total > 0 && (
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-orange-100">
                <div
                  className="h-full rounded-full bg-warm-coral transition-all"
                  style={{ width: `${Math.min(100, (fillJob.processed / fillJob.total) * 100)}%` }}
                />
              </div>
            )}
          </section>
        )}

        {summary && summary.total_items > 0 && (
          <section className="warm-card p-4">
            <div className="flex flex-wrap gap-4 text-sm text-warm-body">
              {Object.entries(summary.by_level).map(([lvl, count]) => (
                <button
                  key={lvl}
                  type="button"
                  className={`rounded-full px-3 py-1 font-semibold ${
                    level === lvl
                      ? "bg-warm-coral text-white"
                      : "bg-white/80 text-warm-brown hover:bg-orange-50"
                  }`}
                  onClick={() => {
                    setPage(1);
                    setLevel(level === lvl ? "" : lvl);
                  }}
                >
                  {lvl}: {count}
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="warm-card p-6">
          <form onSubmit={handleSearchSubmit} className="flex flex-wrap gap-2">
            <input
              className="warm-input min-w-[12rem] flex-1"
              placeholder="Search word or definition…"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <select
              className="warm-input max-w-[10rem]"
              aria-label="Filter by level"
              value={level}
              onChange={(event) => {
                setPage(1);
                setLevel(event.target.value);
              }}
            >
              <option value="">All levels</option>
              {levelOptions.map((lvl) => (
                <option key={lvl} value={lvl}>
                  {lvl}
                </option>
              ))}
            </select>
            <select
              className="warm-input max-w-[12rem]"
              aria-label="Filter by category"
              value={category}
              onChange={(event) => {
                setPage(1);
                setCategory(event.target.value);
              }}
            >
              <option value="">All categories</option>
              {categoryOptions.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm font-semibold text-warm-brown">
              <input
                type="checkbox"
                checked={placeholdersOnly}
                onChange={(event) => {
                  setPage(1);
                  setPlaceholdersOnly(event.target.checked);
                }}
              />
              Missing definitions only
            </label>
            <button type="submit" className="warm-btn warm-btn-primary text-sm">
              Search
            </button>
            {(level || category || search || placeholdersOnly) && (
              <button
                type="button"
                className="warm-btn warm-btn-secondary text-sm"
                onClick={clearFilters}
              >
                Clear
              </button>
            )}
          </form>
          <p className="mt-3 text-sm text-warm-brown-soft">
            Showing {items.length} of {total.toLocaleString()} matching words
          </p>
        </section>

        <section className="warm-card overflow-hidden p-0">
          {loading ? (
            <p className="p-6 text-warm-brown-soft">Loading words…</p>
          ) : items.length === 0 ? (
            <p className="p-6 text-warm-brown-soft">
              {summary?.total_items
                ? "No words match your filters."
                : "No word bank yet — upload a CSV from Word Lists."}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-orange-100 bg-orange-50/50 text-warm-brown">
                  <tr>
                    <th className="px-4 py-3 font-bold">Word</th>
                    <th className="px-4 py-3 font-bold">Definition</th>
                    <th className="px-4 py-3 font-bold">Level</th>
                    <th className="px-4 py-3 font-bold">Category</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-orange-50">
                  {items.map((item) => (
                    <tr key={item.id} className="text-warm-body">
                      <td className="px-4 py-3 font-semibold text-warm-brown">{item.word}</td>
                      <td className="max-w-md px-4 py-3 text-warm-brown-soft">
                        {isPlaceholderDefinition(item.definition)
                          ? "Definition pending…"
                          : item.definition}
                      </td>
                      <td className="px-4 py-3">{item.level ?? "—"}</td>
                      <td className="px-4 py-3">{item.categories.join(" · ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              className="warm-btn warm-btn-secondary text-sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <span className="text-sm font-semibold text-warm-brown">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="warm-btn warm-btn-secondary text-sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        )}
      </main>
    </PageShell>
  );
}
