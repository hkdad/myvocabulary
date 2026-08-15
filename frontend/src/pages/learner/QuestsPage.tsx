import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  getQuests,
  THEME_PACK_LEVEL_OPTIONS,
  themePackWordsUrl,
  type QuestsSummary,
  type ThemePackLevelFilter,
} from "../../api/loop";
import LearnerPageHeader from "../../components/LearnerPageHeader";
import QuestLevelAccordion from "../../components/quest/QuestLevelAccordion";
import QuestOverallCard from "../../components/quest/QuestOverallCard";
import PageShell from "../../components/PageShell";
import { useAuthStore } from "../../stores/authStore";

export default function QuestsPage() {
  const learner = useAuthStore((state) => state.user?.learner);
  const [quests, setQuests] = useState<QuestsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [packLevel, setPackLevel] = useState<ThemePackLevelFilter>("Overall");
  const shellVariant = learner?.ui_mode === "kid" ? "kid" : "teen";

  useEffect(() => {
    getQuests()
      .then(setQuests)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load quests"));
  }, []);

  const packsForLevel =
    quests?.packs_by_level[packLevel] ?? (packLevel === "Overall" ? quests?.packs : undefined);
  const activePacks = packsForLevel?.filter((pack) => pack.total_words > 0) ?? [];

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

        {quests?.newly_earned_badges.length ? (
          <section className="warm-card bg-gradient-to-br from-amber-50 to-yellow-50 p-4">
            <p className="font-extrabold text-warm-brown">New badge earned! 🎉</p>
            <p className="text-sm text-warm-body">
              {quests.newly_earned_badges.map((b) => b.replace(/_/g, " ")).join(", ")}
            </p>
          </section>
        ) : null}

        {quests && <QuestOverallCard overall={quests.overall} />}

        {quests && quests.levels.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-lg font-extrabold text-warm-brown">By level</h2>
            {quests.levels.map((levelQuest) => (
              <QuestLevelAccordion
                key={levelQuest.level}
                levelQuest={levelQuest}
                defaultOpen={levelQuest.is_current}
              />
            ))}
          </section>
        )}

        <section>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-extrabold text-warm-brown">Theme packs</h2>
              <p className="mt-1 text-sm text-warm-brown-soft">
                Strong = familiar or mastered in that category
                {packLevel !== "Overall" ? ` · Level ${packLevel}` : ""}
              </p>
            </div>
            <select
              className="warm-input max-w-[10rem]"
              aria-label="Filter theme packs by level"
              value={packLevel}
              onChange={(event) => setPackLevel(event.target.value as ThemePackLevelFilter)}
            >
              {THEME_PACK_LEVEL_OPTIONS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>
          </div>
          {activePacks.length === 0 ? (
            <p className="text-warm-brown-soft">
              {packLevel === "Overall"
                ? "No theme packs yet — ask parent to upload words with categories."
                : `No ${packLevel} words in theme packs yet.`}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {activePacks.map((pack) => (
                <Link
                  key={pack.slug}
                  to={themePackWordsUrl(pack, packLevel)}
                  className="warm-card block p-4 transition hover:bg-warm-cream/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-accent"
                  aria-label={`View ${pack.title} words in My words`}
                >
                  <p className="text-2xl">{pack.emoji}</p>
                  <p className="mt-1 font-extrabold text-warm-brown">{pack.title}</p>
                  <p className="text-sm text-warm-brown-soft">
                    {pack.strong_words} / {pack.total_words} strong words
                  </p>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-green-400 to-teal-300"
                      style={{ width: `${pack.progress_percent}%` }}
                    />
                  </div>
                  {pack.completed && (
                    <p className="mt-2 text-sm font-semibold text-green-700">Pack complete ✓</p>
                  )}
                </Link>
              ))}
            </div>
          )}
        </section>

        <Link to="/app/home" className="warm-btn warm-btn-secondary text-center text-sm">
          Back to home
        </Link>
      </main>
    </PageShell>
  );
}
