import { type FormEvent, type MouseEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  createWordList,
  listAssignedWordLists,
  type WordListSummary,
} from "../../api/wordLists";
import { initializeReviews } from "../../api/reviews";
import PageShell from "../../components/PageShell";
import LearnerPageHeader from "../../components/LearnerPageHeader";
import { useAuthStore } from "../../stores/authStore";

function ListRow({ list }: { list: WordListSummary }) {
  const navigate = useNavigate();
  const [reviewing, setReviewing] = useState(false);

  async function handleReview(event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (list.item_count === 0) {
      return;
    }
    setReviewing(true);
    try {
      await initializeReviews(list.id);
      navigate(`/app/review?list_id=${list.id}`);
    } catch {
      navigate(`/app/lists/${list.id}`);
    } finally {
      setReviewing(false);
    }
  }

  return (
    <li className="py-4">
      <Link
        to={`/app/lists/${list.id}`}
        className="block rounded-xl p-2 transition hover:bg-amber-50/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-coral"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xl font-extrabold text-warm-brown">{list.name}</p>
              {list.source === "learner" && (
                <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-bold text-sky-800">
                  My list
                </span>
              )}
            </div>
            <p className="text-sm text-warm-brown-soft">
              {list.level_tag ?? "School words"} · {list.item_count} words
              {list.due_date ? ` · due ${list.due_date}` : ""}
            </p>
          </div>
          {list.item_count > 0 && (
            <button
              type="button"
              onClick={(event) => void handleReview(event)}
              disabled={reviewing}
              className="warm-btn warm-btn-primary shrink-0 text-xs disabled:opacity-50"
            >
              {reviewing ? "Starting…" : "Review"}
            </button>
          )}
        </div>
      </Link>
    </li>
  );
}

export default function LearnerWordListsPage() {
  const user = useAuthStore((state) => state.user);
  const [lists, setLists] = useState<WordListSummary[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);

  async function loadLists() {
    setError(null);
    setLoading(true);
    try {
      const assigned = await listAssignedWordLists();
      setLists(assigned);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load word lists");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLists();
  }, []);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await createWordList({ name: name.trim() });
      setName("");
      await loadLists();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create list");
    } finally {
      setCreating(false);
    }
  }

  const myLists = lists.filter((list) => list.source === "learner");
  const assignedLists = lists.filter((list) => list.source !== "learner");

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <LearnerPageHeader
          eyebrow="📚 My lists"
          title="Word lists"
          subtitle={`Hi ${user?.learner?.display_name ?? user?.username}! Add school spelling lists here ✨`}
        />

        {error && <p className="font-semibold text-red-600">{error}</p>}
        {loading && <p className="text-warm-brown-soft">Loading your lists…</p>}

        {!loading && (
          <>
        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Create your own list</h2>
          <p className="mt-1 text-sm text-warm-brown-soft">
            Type in the words your teacher gave you for school dictation.
          </p>
          <form onSubmit={handleCreate} className="mt-4 flex flex-wrap gap-2">
            <input
              className="warm-input min-w-[12rem] flex-1"
              placeholder="e.g. Week 5 spelling"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <button
              type="submit"
              disabled={creating || !name.trim()}
              className="warm-btn warm-btn-primary text-sm disabled:opacity-50"
            >
              {creating ? "Creating…" : "Create list ✨"}
            </button>
          </form>
        </section>

        {myLists.length > 0 && (
          <section className="warm-card p-6">
            <h2 className="text-lg font-extrabold text-warm-brown">My school lists</h2>
            <ul className="divide-y divide-orange-100">
              {myLists.map((list) => (
                <ListRow key={list.id} list={list} />
              ))}
            </ul>
          </section>
        )}

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">
            {assignedLists.length > 0 ? "Assigned by parent" : "Assigned lists"}
          </h2>
          {assignedLists.length === 0 ? (
            <p className="mt-4 text-warm-body">
              {myLists.length === 0
                ? "No lists yet. Create one above for your school words!"
                : "No parent-assigned lists right now."}
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-orange-100">
              {assignedLists.map((list) => (
                <ListRow key={list.id} list={list} />
              ))}
            </ul>
          )}
        </section>
          </>
        )}
      </main>
    </PageShell>
  );
}
