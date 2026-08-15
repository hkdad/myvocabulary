import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { apiFetch } from "../../api/client";
import { API_BASE_URL } from "../../lib/constants";
import {
  addWordToList,
  assignWordList,
  deleteWordList,
  getWordList,
  removeWordFromList,
  unassignWordList,
  type WordListDetail,
} from "../../api/wordLists";
import PageShell from "../../components/PageShell";

type LearnerSummary = {
  id: number;
  display_name: string;
  username: string;
};

export default function WordListDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const listId = Number(id);
  const [list, setList] = useState<WordListDetail | null>(null);
  const [learners, setLearners] = useState<LearnerSummary[]>([]);
  const [word, setWord] = useState("");
  const [selectedLearnerId, setSelectedLearnerId] = useState<number | "">("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!listId) {
      return;
    }
    setError(null);
    try {
      const [detail, learnerRows] = await Promise.all([
        getWordList(listId),
        apiFetch<LearnerSummary[]>("/learners", {}, API_BASE_URL),
      ]);
      setList(detail);
      setLearners(learnerRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load list");
    }
  }, [listId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAddWord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!word.trim() || !list) {
      return;
    }
    try {
      await addWordToList(list.id, { word: word.trim() });
      setWord("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add word");
    }
  }

  async function handleAssign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!list || selectedLearnerId === "") {
      return;
    }
    try {
      await assignWordList(list.id, { learner_ids: [selectedLearnerId] });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign list");
    }
  }

  async function handleDeleteList() {
    if (!list) {
      return;
    }
    const confirmed = window.confirm(
      `Delete "${list.name}"? Assigned learners will lose access. This cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteWordList(list.id);
      navigate("/parent/word-lists");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete list");
      setDeleting(false);
    }
  }

  async function handleUnassign(learnerId: number) {
    if (!list) {
      return;
    }
    try {
      await unassignWordList(list.id, learnerId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unassign list");
    }
  }

  if (!list) {
    return (
      <PageShell variant="parent">
        <main className="mx-auto max-w-4xl p-8">
          <p className="text-warm-brown-soft">{error ?? "Loading…"}</p>
        </main>
      </PageShell>
    );
  }

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Word list</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">{list.name}</h1>
            <p className="mt-1 font-semibold text-warm-brown-soft">
              {list.source === "custom"
                ? `${list.item_count} words`
                : `${list.level_tag ?? "—"} · ${list.source} · ${list.item_count} words`}
            </p>
          </div>
          <div className="flex flex-wrap items-start justify-end gap-2">
            {list.source === "custom" && (
              <button
                type="button"
                className="text-sm font-semibold text-red-600 disabled:opacity-50"
                disabled={deleting}
                onClick={() => void handleDeleteList()}
              >
                {deleting ? "Deleting…" : "Delete list"}
              </button>
            )}
            <Link to="/parent/word-lists" className="warm-btn warm-btn-secondary text-sm">
              Back to lists
            </Link>
          </div>
        </header>

        {error && <p className="font-semibold text-red-600">{error}</p>}

        {list.source === "custom" && (
          <section className="warm-card p-6">
            <h2 className="text-lg font-extrabold text-warm-brown">Add word</h2>
            <form onSubmit={handleAddWord} className="mt-4 flex flex-wrap gap-2">
              <input
                className="warm-input flex-1"
                placeholder="Type a word"
                value={word}
                onChange={(event) => setWord(event.target.value)}
              />
              <button type="submit" className="warm-btn warm-btn-primary text-sm">Add ✨</button>
            </form>
          </section>
        )}

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Words</h2>
          <ul className="mt-4 divide-y divide-orange-100">
            {list.items.map((item) => (
              <li key={item.id} className="flex items-start justify-between gap-4 py-4">
                <div>
                  <p className="font-extrabold text-warm-brown">{item.dictionary_entry.word}</p>
                  <p className="text-sm text-warm-brown-soft">{item.dictionary_entry.definition}</p>
                </div>
                {list.source === "custom" && (
                  <button
                    type="button"
                    onClick={() => void removeWordFromList(list.id, item.id).then(load)}
                    className="text-sm font-semibold text-red-600"
                  >
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Assignments</h2>
          <p className="mt-1 text-sm text-warm-brown-soft">
            Assigning a list shares it with your child. They still need to tap{" "}
            <strong>Review this list</strong> on their Word lists page to start flashcards.
          </p>
          <form onSubmit={handleAssign} className="mt-4 flex flex-wrap gap-2">
            <select
              className="warm-input max-w-xs"
              value={selectedLearnerId}
              onChange={(event) =>
                setSelectedLearnerId(event.target.value ? Number(event.target.value) : "")
              }
            >
              <option value="">Select learner</option>
              {learners.map((learner) => (
                <option key={learner.id} value={learner.id}>
                  {learner.display_name} (@{learner.username})
                </option>
              ))}
            </select>
            <button type="submit" className="warm-btn warm-btn-primary text-sm">Assign 👧👦</button>
          </form>
          <ul className="mt-4 divide-y divide-orange-100">
            {list.assigned_learner_ids.map((learnerId) => {
              const learner = learners.find((row) => row.id === learnerId);
              return (
                <li key={learnerId} className="flex items-center justify-between py-3">
                  <span className="font-semibold text-warm-brown">
                    {learner?.display_name ?? `Learner #${learnerId}`}
                  </span>
                  <button
                    type="button"
                    onClick={() => void handleUnassign(learnerId)}
                    className="text-sm font-semibold text-red-600"
                  >
                    Unassign
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      </main>
    </PageShell>
  );
}
