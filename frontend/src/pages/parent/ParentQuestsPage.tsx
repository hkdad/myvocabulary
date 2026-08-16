import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { getLearnerQuests, type QuestsSummary } from "../../api/loop";
import { listLearners, type LearnerProfile } from "../../api/learners";
import LearnerAvatar from "../../components/LearnerAvatar";
import QuestsSummaryView from "../../components/quest/QuestsSummaryView";
import PageShell from "../../components/PageShell";

export default function ParentQuestsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [learners, setLearners] = useState<LearnerProfile[]>([]);
  const [selectedId, setSelectedId] = useState<number | "">("");
  const [quests, setQuests] = useState<QuestsSummary | null>(null);
  const [loadingLearners, setLoadingLearners] = useState(true);
  const [loadingQuests, setLoadingQuests] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadQuests = useCallback(async (learnerId: number) => {
    setLoadingQuests(true);
    setError(null);
    try {
      setQuests(await getLearnerQuests(learnerId));
    } catch (err) {
      setQuests(null);
      setError(err instanceof Error ? err.message : "Failed to load quests");
    } finally {
      setLoadingQuests(false);
    }
  }, []);

  useEffect(() => {
    setLoadingLearners(true);
    const queryId = Number(searchParams.get("learner"));
    listLearners()
      .then((rows) => {
        setLearners(rows);
        const initial =
          rows.find((row) => row.id === queryId) ??
          rows.find((row) => row.is_active) ??
          rows[0];
        if (initial) {
          setSelectedId(initial.id);
        }
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load learners");
      })
      .finally(() => setLoadingLearners(false));
  }, []);

  useEffect(() => {
    if (selectedId === "") {
      return;
    }
    void loadQuests(selectedId);
  }, [selectedId, loadQuests]);

  function handleLearnerChange(learnerId: number) {
    setSelectedId(learnerId);
    setSearchParams({ learner: String(learnerId) }, { replace: true });
  }

  const selectedLearner = learners.find((row) => row.id === selectedId);

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Family quests</p>
            <h1 className="text-2xl font-extrabold text-warm-brown">Quests 🗺️</h1>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Theme packs, milestones, and level progress per child.
            </p>
          </div>
          <Link to="/parent/dashboard" className="warm-btn warm-btn-secondary text-sm">
            Dashboard
          </Link>
        </header>

        {loadingLearners ? (
          <p className="text-warm-brown-soft">Loading learners…</p>
        ) : learners.length === 0 ? (
          <div className="warm-card p-6 text-center">
            <p className="font-bold text-warm-brown">No learners yet</p>
            <Link to="/parent/learners" className="warm-btn warm-btn-primary mt-4 text-sm">
              Add a learner
            </Link>
          </div>
        ) : (
          <section className="warm-card p-5">
            <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
              View quests for
              <div className="flex flex-wrap items-center gap-3">
                {selectedLearner && (
                  <LearnerAvatar learner={selectedLearner} size="sm" className="rounded-xl" />
                )}
                <select
                  className="warm-input min-w-[12rem] flex-1"
                  value={selectedId}
                  onChange={(event) =>
                    handleLearnerChange(Number(event.target.value))
                  }
                >
                  {learners.map((learner) => (
                    <option key={learner.id} value={learner.id}>
                      {learner.display_name} (@{learner.username})
                      {!learner.is_active ? " — inactive" : ""}
                    </option>
                  ))}
                </select>
              </div>
            </label>
            {selectedLearner && quests && !loadingQuests && (
              <p className="mt-3 text-sm text-warm-brown-soft">
                Level {quests.english_level} · {quests.completed_pack_quests} /{" "}
                {quests.total_pack_quests} theme packs done · {quests.earned_pack_badges} pack badges
                · {quests.earned_milestone_badges} milestone badges
              </p>
            )}
          </section>
        )}

        {error && (
          <p className="rounded-xl bg-red-50 px-4 py-3 font-semibold text-red-600">{error}</p>
        )}

        {loadingQuests && <p className="text-warm-brown-soft">Loading quests…</p>}

        {quests && !loadingQuests && (
          <QuestsSummaryView
            quests={quests}
            packLinks={false}
            emptyPackMessage="No theme packs in the word bank for this level yet."
          />
        )}
      </main>
    </PageShell>
  );
}
