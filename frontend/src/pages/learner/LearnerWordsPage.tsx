import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  bankCategoriesFromSummary,
  bankLevelsFromSummary,
  getLearnerWords,
  type LearnerWordItem,
  type LearnerWordStrength,
} from "../../api/loop";
import LearnerAvatar from "../../components/LearnerAvatar";
import LearnerTopNav from "../../components/LearnerTopNav";
import PageShell from "../../components/PageShell";
import { useAuthStore } from "../../stores/authStore";

const STRENGTH_OPTIONS: { value: LearnerWordStrength | ""; label: string }[] = [
  { value: "", label: "All strengths" },
  { value: "learning", label: "Learning" },
  { value: "familiar", label: "Familiar" },
  { value: "mastered", label: "Mastered" },
];

/** Distinct practice days needed for Mastered (matches backend MASTERED_MIN_DISTINCT_DAYS). */
const MASTERED_DAYS = 3;

function strengthLabel(strength: string): string {
  if (strength === "familiar") return "Familiar";
  if (strength === "mastered") return "Mastered";
  if (strength === "new") return "New";
  return "Learning";
}

function strengthBarClass(strength: string): string {
  if (strength === "mastered") return "bg-emerald-500";
  if (strength === "familiar") return "bg-amber-400";
  return "bg-sky-400";
}

function WordProgress({ item }: { item: LearnerWordItem }) {
  const days = item.distinct_review_days ?? 0;
  const progress = Math.min(100, Math.round((days / MASTERED_DAYS) * 100));
  const interval =
    item.interval_days > 0
      ? `Next interval ${item.interval_days}d`
      : days === 0
        ? "Not reviewed yet"
        : "In learning";

  return (
    <div className="min-w-[9rem]">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold text-warm-brown">{strengthLabel(item.strength)}</span>
        <span className="text-xs font-bold text-warm-muted">
          {days}/{MASTERED_DAYS} days
        </span>
      </div>
      <div
        className="mt-1 h-2 overflow-hidden rounded-full bg-orange-100"
        role="progressbar"
        aria-valuenow={days}
        aria-valuemin={0}
        aria-valuemax={MASTERED_DAYS}
        aria-label={`${days} of ${MASTERED_DAYS} practice days toward Mastered`}
      >
        <div
          className={`h-full rounded-full transition-all ${strengthBarClass(item.strength)}`}
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="mt-1 text-xs text-warm-brown-soft">{interval}</p>
    </div>
  );
}

export default function LearnerWordsPage() {
  const learner = useAuthStore((state) => state.user)?.learner;
  const shellVariant = learner?.ui_mode === "kid" ? "kid" : "teen";
  const [searchParams, setSearchParams] = useSearchParams();

  const initialStrength = searchParams.get("strength") ?? "";
  const initialLevel = searchParams.get("level") ?? "";
  const initialCategory = searchParams.get("category") ?? "";
  const initialSearch = searchParams.get("q") ?? "";
  const [items, setItems] = useState<LearnerWordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [byLevel, setByLevel] = useState<Record<string, number>>({});
  const [byCategory, setByCategory] = useState<Record<string, number>>({});
  const [byStrength, setByStrength] = useState<Record<string, number>>({});
  const [level, setLevel] = useState(initialLevel);
  const [category, setCategory] = useState(initialCategory);
  const [strength, setStrength] = useState(initialStrength);
  const [search, setSearch] = useState(initialSearch);
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const pageSize = 50;
  const levelOptions = bankLevelsFromSummary(byLevel);
  const categoryOptions = bankCategoriesFromSummary(byCategory);
  const releasedTotal =
    (byStrength.learning ?? 0) + (byStrength.familiar ?? 0) + (byStrength.mastered ?? 0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getLearnerWords({
        level: level || undefined,
        category: category || undefined,
        q: search || undefined,
        strength: strength || undefined,
        page,
        page_size: pageSize,
      });
      setItems(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
      setByLevel(data.by_level);
      setByCategory(data.by_category);
      setByStrength(data.by_strength);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load words");
      setItems([]);
      setTotal(0);
      setTotalPages(0);
    } finally {
      setLoading(false);
    }
  }, [category, level, page, search, strength]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setLevel(searchParams.get("level") ?? "");
    setCategory(searchParams.get("category") ?? "");
    const nextStrength = searchParams.get("strength") ?? "";
    const nextSearch = searchParams.get("q") ?? "";
    setStrength(nextStrength);
    setSearch(nextSearch);
    setSearchInput(nextSearch);
    setPage(1);
  }, [searchParams]);

  function updateFilterParams(updates: {
    level?: string;
    category?: string;
    strength?: string;
    q?: string;
  }) {
    const params = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value) {
        params.set(key, value);
      } else {
        params.delete(key);
      }
    }
    setSearchParams(params);
  }

  function handleSearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateFilterParams({ q: searchInput.trim() });
  }

  function clearFilters() {
    setSearchParams({});
  }

  function updateStrength(next: string) {
    updateFilterParams({ strength: next });
  }

  return (
    <PageShell variant={shellVariant}>
      <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <LearnerAvatar learner={learner} size="lg" className="bg-purple-100" />
            <div>
              <p className="text-sm font-bold text-warm-muted">Your progress</p>
              <h1 className="text-3xl font-extrabold text-warm-brown">My words</h1>
              <p className="mt-1 text-sm text-warm-brown-soft">
                {releasedTotal > 0
                  ? `${releasedTotal.toLocaleString()} words released · progress grows with each practice day`
                  : "Words appear here after they are released in your daily challenge"}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/app/stats" className="warm-btn warm-btn-secondary text-sm">
              Back to stats
            </Link>
            <LearnerTopNav />
          </div>
        </header>

        {error && <p className="font-semibold text-red-600">{error}</p>}

        {releasedTotal > 0 && (
          <section className="warm-card p-4">
            <div className="flex flex-wrap gap-2 text-sm text-warm-body">
              {STRENGTH_OPTIONS.filter((option) => option.value).map((option) => {
                const count = byStrength[option.value] ?? 0;
                const active = strength === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`rounded-full px-3 py-1 font-semibold ${
                      active
                        ? "bg-warm-coral text-white"
                        : "bg-white/80 text-warm-brown hover:bg-orange-50"
                    }`}
                    onClick={() => updateStrength(active ? "" : option.value)}
                  >
                    {option.label}: {count}
                  </button>
                );
              })}
            </div>
            {levelOptions.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2 text-sm text-warm-body">
                {levelOptions.map((lvl) => (
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
                    {lvl}: {byLevel[lvl] ?? 0}
                  </button>
                ))}
              </div>
            )}
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
              onChange={(event) => updateFilterParams({ level: event.target.value })}
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
              onChange={(event) => updateFilterParams({ category: event.target.value })}
            >
              <option value="">All categories</option>
              {categoryOptions.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
            <select
              className="warm-input max-w-[12rem]"
              aria-label="Filter by strength"
              value={strength}
              onChange={(event) => updateStrength(event.target.value)}
            >
              {STRENGTH_OPTIONS.map((option) => (
                <option key={option.label} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button type="submit" className="warm-btn warm-btn-primary text-sm">
              Search
            </button>
            {(level || category || search || strength) && (
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
              {releasedTotal > 0
                ? "No words match your filters."
                : "No released words yet — finish a daily challenge to start your deck."}
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
                    <th className="px-4 py-3 font-bold">Progress</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-orange-50">
                  {items.map((item) => (
                    <tr key={item.card_id} className="text-warm-body">
                      <td className="px-4 py-3 font-semibold text-warm-brown">{item.word}</td>
                      <td className="max-w-md px-4 py-3 text-warm-brown-soft">
                        {item.definition}
                      </td>
                      <td className="px-4 py-3">{item.level ?? "—"}</td>
                      <td className="px-4 py-3">
                        {item.categories.length > 0 ? item.categories.join(" · ") : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <WordProgress item={item} />
                      </td>
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
              onClick={() => setPage((current) => current - 1)}
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
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </div>
        )}
      </main>
    </PageShell>
  );
}
