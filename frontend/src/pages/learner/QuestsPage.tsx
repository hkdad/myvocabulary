import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getQuests, type QuestsSummary } from "../../api/loop";
import LearnerPageHeader from "../../components/LearnerPageHeader";
import QuestsSummaryView from "../../components/quest/QuestsSummaryView";
import PageShell from "../../components/PageShell";
import { useAuthStore } from "../../stores/authStore";

export default function QuestsPage() {
  const learner = useAuthStore((state) => state.user?.learner);
  const [quests, setQuests] = useState<QuestsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const shellVariant = learner?.ui_mode === "kid" ? "kid" : "teen";

  useEffect(() => {
    getQuests()
      .then(setQuests)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load quests"));
  }, []);

  return (
    <PageShell variant={shellVariant}>
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <LearnerPageHeader
          eyebrow="Your adventure map"
          title="Quests 🗺️"
          subtitle={
            quests
              ? `Level ${quests.english_level} · ${quests.completed_pack_quests} / ${quests.total_pack_quests} theme packs done`
              : undefined
          }
        />

        {error && <p className="font-semibold text-red-600">{error}</p>}

        {quests && <QuestsSummaryView quests={quests} />}

        <Link to="/app/home" className="warm-btn warm-btn-secondary text-center text-sm">
          Back to home
        </Link>
      </main>
    </PageShell>
  );
}
