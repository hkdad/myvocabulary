import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getMyStats, type LearnerMeStats } from "../../api/dashboard";
import { getLoopToday, type DailyMix } from "../../api/loop";
import LearnerPageHeader from "../../components/LearnerPageHeader";
import LevelProgressCard from "../../components/LevelProgressCard";
import PageShell from "../../components/PageShell";
import { useAuthStore } from "../../stores/authStore";

type LearningTile = {
  emoji: string;
  title: string;
  hint: string;
  to?: string;
  soon?: boolean;
};

const LEARNING_TILES: LearningTile[] = [
  { emoji: "📝", title: "Practice mistakes", hint: "Recognize + Listen & Pick, up to 5", to: "/app/challenge?mistakes=1" },
  { emoji: "🔍", title: "Dictionary", hint: "Definitions & examples", to: "/app/dictionary" },
  { emoji: "🎧", title: "Listen & Pick", hint: "Recognition practice", to: "/app/dictation/pick" },
  { emoji: "🧠", title: "SRS Review", hint: "Spaced repetition", to: "/app/review" },
  { emoji: "✍️", title: "Dictation", hint: "Bonus spelling practice", to: "/app/dictation" },
  { emoji: "📚", title: "Word lists", hint: "Your assigned lists", to: "/app/lists" },
  { emoji: "🗺️", title: "Quests", hint: "Theme packs & badges", to: "/app/quests" },
  { emoji: "🎯", title: "Challenges", hint: "Level-up & badges", to: "/app/challenges" },
];

function practiceProgress(dailyMix: DailyMix | null): number {
  if (!dailyMix) {
    return 0;
  }
  if (dailyMix.completed_today) {
    return 100;
  }
  if (dailyMix.dictation_completed && !dailyMix.srs_completed) {
    return 60;
  }
  if (dailyMix.srs_completed && !dailyMix.dictation_completed) {
    return 40;
  }
  if (dailyMix.cards.length === 0) {
    return 0;
  }
  return 20;
}

export default function LearnerHomePage() {
  const user = useAuthStore((state) => state.user);
  const refreshProfile = useAuthStore((state) => state.refreshProfile);
  const learner = user?.learner;
  const [stats, setStats] = useState<LearnerMeStats | null>(null);
  const [dailyMix, setDailyMix] = useState<DailyMix | null>(null);
  const [loading, setLoading] = useState(true);
  const [mixError, setMixError] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.id) {
      return;
    }
    void refreshProfile();
    setLoading(true);
    setMixError(null);

    void getLoopToday()
      .then(setDailyMix)
      .catch((err: Error) => {
        setDailyMix(null);
        setMixError(err.message);
      })
      .finally(() => setLoading(false));

    void getMyStats()
      .then(setStats)
      .catch(() => setStats(null));
  }, [refreshProfile, user?.id]);

  const practiceGoal =
    dailyMix != null
      ? dailyMix.daily_new_goal +
        dailyMix.daily_learning_retention_goal +
        dailyMix.daily_mastered_retention_goal
      : stats?.daily_practice_goal ?? learner?.daily_practice_goal ?? 0;
  const progress = practiceProgress(dailyMix);
  const shellVariant = learner?.ui_mode === "kid" ? "kid" : "teen";

  return (
    <PageShell variant={shellVariant}>
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <LearnerPageHeader
          eyebrow="Welcome back ✨"
          title={learner?.display_name ?? user?.username ?? "Learner"}
          subtitle={`Level ${stats?.english_level ?? learner?.english_level ?? "—"}`}
          showHome={false}
        />

        <section className="warm-card bg-gradient-to-br from-amber-50/90 to-orange-50/90 p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🎯</span>
                <div>
                  <h2 className="text-lg font-extrabold text-warm-brown">Daily challenge</h2>
                  {dailyMix ? (
                    <p className="text-sm text-warm-brown-soft">
                      Up to <strong>{dailyMix.daily_new_goal}</strong> new +{" "}
                      <strong>{dailyMix.daily_learning_retention_goal}</strong> learning/familiar +{" "}
                      <strong>{dailyMix.daily_mastered_retention_goal}</strong> mastered (
                      {practiceGoal} cards)
                    </p>
                  ) : (
                    <p className="text-sm text-warm-brown-soft">
                      Your guided mix of new words and retention reviews
                    </p>
                  )}
                </div>
              </div>

              {loading && (
                <p className="mt-4 text-sm font-semibold text-warm-muted">Loading today&apos;s challenge…</p>
              )}

              {mixError && (
                <p className="mt-4 text-sm font-semibold text-red-600">
                  Could not load daily challenge — check that the server is running.
                </p>
              )}

              {dailyMix && !loading && (
                <>
                  <div className="mt-4 h-3 overflow-hidden rounded-full bg-white/70">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-300 transition-all"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <p className="mt-2 text-sm text-warm-body">
                    Today&apos;s mix: <strong>{dailyMix.cards.length}</strong> words (
                    <strong>{dailyMix.new_count}</strong> new +{" "}
                    <strong>{dailyMix.learning_retention_count ?? dailyMix.retention_count}</strong>{" "}
                    learning/familiar +{" "}
                    <strong>{dailyMix.mastered_retention_count ?? 0}</strong> mastered)
                    {" · "}
                    dripped: <strong>{dailyMix.new_released_today}</strong> / {dailyMix.daily_new_goal}
                    {dailyMix.cards.length === 0 && (
                      <> — no words ready yet; ask a parent to upload the word bank</>
                    )}
                  </p>
                  {dailyMix.completed_today ? (
                    <p className="mt-3 text-sm font-semibold text-green-700">
                      Completed today — nice work!
                    </p>
                  ) : dailyMix.dictation_completed && !dailyMix.srs_completed ? (
                    <p className="mt-3 text-sm font-semibold text-amber-800">
                      Listen &amp; Pick done — finish recognition to complete today
                    </p>
                  ) : dailyMix.srs_completed && !dailyMix.dictation_completed ? (
                    <p className="mt-3 text-sm font-semibold text-amber-800">
                      Review done — finish Listen &amp; Pick to complete today
                    </p>
                  ) : (
                    <p className="mt-3 text-sm text-warm-brown-soft">
                      Two steps: Listen &amp; Pick, then recognition review
                    </p>
                  )}
                </>
              )}

              {stats && (
                <p className="mt-3 text-sm text-warm-brown-soft">
                  <Link to="/app/stats" className="text-warm-accent underline">
                    {stats.due_count} due · streak {stats.streak_days} days · full stats
                  </Link>
                </p>
              )}

            </div>
            <div className="flex shrink-0 flex-col gap-2">
              <Link
                to="/app/challenge"
                className={`warm-btn text-sm ${
                  dailyMix?.completed_today ? "warm-btn-secondary" : "warm-btn-primary"
                }`}
              >
                {dailyMix?.completed_today ? "Practice again" : "Start challenge"}
              </Link>
              <Link
                to="/app/challenge?mistakes=1"
                className="warm-btn warm-btn-primary text-sm"
              >
                Practice mistakes
                {stats && stats.unresolved_mistakes > 0
                  ? ` (${Math.min(stats.unresolved_mistakes, 5)})`
                  : ""}
              </Link>
              {stats && stats.due_count > 0 && (
                <Link to="/app/review" className="warm-btn warm-btn-secondary text-sm">
                  Extra review
                </Link>
              )}
            </div>
          </div>
        </section>

        {dailyMix?.book_title && (
          <section className="warm-card p-6">
            <p className="text-sm font-bold text-warm-muted">Book progress</p>
            <h2 className="mt-1 text-lg font-extrabold text-warm-brown">{dailyMix.book_title}</h2>
            <div className="mt-4 h-3 overflow-hidden rounded-full bg-orange-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-300"
                style={{ width: `${Math.min(100, dailyMix.study_progress_percent ?? 0)}%` }}
              />
            </div>
            <p className="mt-2 text-sm text-warm-body">
              Study set {dailyMix.study_progress_percent ?? 0}% known · page coverage{" "}
              {dailyMix.page_coverage_percent ?? 0}%
              {dailyMix.ready_to_read ? " · ready to read with help" : ""}
            </p>
          </section>
        )}

        <LevelProgressCard
          englishLevel={stats?.english_level ?? learner?.english_level ?? "A1"}
        />

        <section>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-extrabold text-warm-brown">
            <span>🗺️</span> Your learning map
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <Link
              to="/app/challenge"
              className="warm-card col-span-2 block border-2 border-amber-300 bg-gradient-to-br from-amber-50/90 to-orange-50/90 p-4 transition hover:scale-[1.02]"
            >
              <span className="text-3xl">✨</span>
              <p className="mt-2 font-extrabold text-warm-brown">Daily challenge</p>
              <p className="text-sm text-warm-brown-soft">Match today&apos;s words to their meanings</p>
            </Link>
            {LEARNING_TILES.map((tile) => {
              const mistakeHint =
                tile.title === "Practice mistakes" && stats && stats.unresolved_mistakes > 0
                  ? `${stats.unresolved_mistakes} word${stats.unresolved_mistakes === 1 ? "" : "s"} — clear up to 5`
                  : tile.hint;
              const content = (
                <>
                  <span className="text-3xl">{tile.emoji}</span>
                  <p className="mt-2 font-extrabold text-warm-brown">{tile.title}</p>
                  <p className="text-sm text-warm-brown-soft">{mistakeHint}</p>
                  {tile.soon && (
                    <span className="mt-2 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-800">
                      Coming soon ✨
                    </span>
                  )}
                </>
              );

              if (tile.to) {
                return (
                  <Link
                    key={tile.title}
                    to={tile.to}
                    className="warm-card block p-4 transition hover:scale-[1.02]"
                  >
                    {content}
                  </Link>
                );
              }

              return (
                <div key={tile.title} className="warm-card p-4">
                  {content}
                </div>
              );
            })}
          </div>
        </section>

        <p className="text-center text-sm font-semibold text-warm-faint">
          Small steps, big vocabulary 📈
        </p>
      </main>
    </PageShell>
  );
}
