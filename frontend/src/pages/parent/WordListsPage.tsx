import { type ChangeEvent, type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  createWordList,
  deleteWordList,
  listCatalog,
  listWordLists,
  type WordListSummary,
} from "../../api/wordLists";
import {
  getWordBankSummary,
  importWordBankWithProgress,
  deleteWordBank,
  type WordBankImportResult,
  type WordBankSummary,
} from "../../api/loop";
import { validateBankCsvFile } from "../../lib/bankCsv";
import PageShell from "../../components/PageShell";

function formatImportResult(result: WordBankImportResult): string {
  const parts = [
    `Imported ${result.created} new, ${result.updated} updated (${result.total_items} total).`,
  ];
  if (result.skipped > 0) {
    parts.push(`${result.skipped} row(s) skipped.`);
  }
  if (result.needs_level_count > 0) {
    parts.push(`${result.needs_level_count} invalid level(s).`);
  }
  if (result.invalid_category_count > 0) {
    parts.push(`${result.invalid_category_count} invalid category(ies).`);
  }
  if (result.errors.length > 0) {
    parts.push(result.errors.slice(0, 3).join(" "));
  }
  return parts.join(" ");
}

export default function WordListsPage() {
  const [lists, setLists] = useState<WordListSummary[]>([]);
  const [catalog, setCatalog] = useState<WordListSummary[]>([]);
  const [catalogLevel, setCatalogLevel] = useState("A2");
  const [name, setName] = useState("");
  const [bankSummary, setBankSummary] = useState<WordBankSummary | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importWarnings, setImportWarnings] = useState<string[]>([]);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deletingListId, setDeletingListId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mine, curated, bank] = await Promise.all([
        listWordLists(),
        listCatalog(catalogLevel),
        getWordBankSummary(),
      ]);
      setLists(mine.filter((item) => item.source === "custom"));
      setCatalog(curated);
      setBankSummary(bank);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load word lists");
    } finally {
      setLoading(false);
    }
  }, [catalogLevel]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    try {
      await createWordList({ name: name.trim() });
      setName("");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create list");
    }
  }

  async function handleBankImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setError(null);
    setImportMessage(null);
    setImportWarnings([]);
    setUploadProgress(null);

    const validation = await validateBankCsvFile(file);
    if (!validation.ok) {
      setError(validation.errors.join(" "));
      event.target.value = "";
      return;
    }
    setImportWarnings(validation.warnings);

    setImporting(true);
    try {
      const result = await importWordBankWithProgress(file, (percent) => {
        setUploadProgress(percent);
      });
      setImportMessage(formatImportResult(result));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
      setUploadProgress(null);
      event.target.value = "";
    }
  }

  async function handleDeleteList(list: WordListSummary) {
    const confirmed = window.confirm(
      `Delete "${list.name}"? Assigned learners will lose access. This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setDeletingListId(list.id);
    try {
      await deleteWordList(list.id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete list");
    } finally {
      setDeletingListId(null);
    }
  }

  async function handleBankDelete() {
    if (!bankSummary?.total_items) {
      return;
    }
    const confirmed = window.confirm(
      `Delete all ${bankSummary.total_items.toLocaleString()} words from the family bank? Kids' review progress for these words will be removed. This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setError(null);
    setImportMessage(null);
    setDeleting(true);
    try {
      const result = await deleteWordBank();
      setImportMessage(
        `Deleted ${result.deleted_items.toLocaleString()} words (${result.deleted_cards} review cards cleared).`,
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete word bank");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Parent</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Word lists 📚</h1>
          </div>
          <Link to="/parent/dashboard" className="warm-btn warm-btn-secondary text-sm">
            Back to dashboard
          </Link>
        </header>

        {error && <p className="font-semibold text-red-600">{error}</p>}
        {importWarnings.length > 0 && (
          <p className="font-semibold text-amber-700">{importWarnings.join(" ")}</p>
        )}
        {importMessage && <p className="font-semibold text-green-700">{importMessage}</p>}
        {uploadProgress !== null && (
          <div className="warm-card p-4">
            <p className="text-sm font-semibold text-warm-brown">Uploading… {uploadProgress}%</p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-orange-100">
              <div
                className="h-full bg-warm-coral transition-all duration-200"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Family word bank</h2>
          <p className="mt-1 text-sm text-warm-brown-soft">
            Upload a CSV with columns: <strong>word</strong>, <strong>level</strong>,{" "}
            <strong>categories</strong>, and optional <strong>definition</strong>. Use{" "}
            <em>and</em>, <em>;</em>, <em>,</em>, or <em>-</em> to separate multiple categories
            in one cell (e.g. <em>Food and Animals</em>, <em>Health, medicine</em>, or{" "}
            <em>Places - town</em>). Aliases like <em>cefr</em>, <em>category</em>, or{" "}
            <em>vocabulary</em> also work.
          </p>
          {bankSummary && bankSummary.total_items > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <p className="text-sm text-warm-body">
                <strong>{bankSummary.total_items.toLocaleString()}</strong> words in bank
              </p>
              <Link to="/parent/word-bank" className="warm-btn warm-btn-secondary text-sm">
                Review bank
              </Link>
              <button
                type="button"
                className="text-sm font-semibold text-red-600 disabled:opacity-50"
                disabled={deleting}
                onClick={() => void handleBankDelete()}
              >
                {deleting ? "Deleting…" : "Delete bank"}
              </button>
            </div>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-3">
          <label
            className={`inline-flex cursor-pointer items-center gap-2 warm-btn warm-btn-primary text-sm ${importing ? "pointer-events-none opacity-60" : ""}`}
          >
            {importing ? "Uploading…" : "Upload CSV"}
            <input
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(event) => void handleBankImport(event)}
            />
          </label>
          </div>
        </section>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Create custom list</h2>
          <form onSubmit={handleCreate} className="mt-4 flex flex-wrap gap-2">
            <input
              className="warm-input min-w-[12rem] flex-1"
              placeholder="List name"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <button type="submit" className="warm-btn warm-btn-primary text-sm">Create ✨</button>
          </form>
        </section>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Custom lists</h2>
          {loading ? (
            <p className="mt-4 text-warm-brown-soft">Loading…</p>
          ) : (
            <ul className="mt-4 divide-y divide-orange-100">
              {lists.map((list) => (
                <li key={list.id} className="flex items-center justify-between gap-4 py-4">
                  <div>
                    <Link
                      to={`/parent/word-lists/${list.id}`}
                      className="font-extrabold text-warm-brown underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-coral"
                    >
                      {list.name}
                    </Link>
                    <p className="text-sm text-warm-brown-soft">
                      {list.item_count} words · assigned to {list.assigned_learner_ids.length}{" "}
                      learner(s)
                    </p>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 text-sm font-semibold text-red-600 disabled:opacity-50"
                    disabled={deletingListId === list.id}
                    onClick={() => void handleDeleteList(list)}
                  >
                    {deletingListId === list.id ? "Deleting…" : "Delete"}
                  </button>
                </li>
              ))}
              {lists.length === 0 && (
                <p className="py-4 text-warm-brown-soft">No custom lists yet.</p>
              )}
            </ul>
          )}
        </section>

        <section className="warm-card p-6">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-lg font-extrabold text-warm-brown">Curated catalog</h2>
            <select
              className="warm-input max-w-[8rem] text-sm"
              value={catalogLevel}
              onChange={(event) => setCatalogLevel(event.target.value)}
            >
              <option value="A2">A2</option>
              <option value="B1">B1</option>
            </select>
          </div>
          <ul className="mt-4 divide-y divide-orange-100">
            {catalog.map((list) => (
              <li key={list.id} className="flex items-center justify-between py-4">
                <div>
                  <Link
                    to={`/parent/word-lists/${list.id}`}
                    className="font-extrabold text-warm-brown underline rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-coral"
                  >
                    {list.name}
                  </Link>
                  <p className="text-sm text-warm-brown-soft">
                    {list.description} · {list.item_count} words
                  </p>
                </div>
                <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-800">
                  curated
                </span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </PageShell>
  );
}
