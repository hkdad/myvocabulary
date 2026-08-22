import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getMyStats, type LearnerMeStats } from "../../api/dashboard";
import PageShell from "../../components/PageShell";
import LearnerPageHeader from "../../components/LearnerPageHeader";

export default function StatsPage() {
  const [stats, setStats] = useState<LearnerMeStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getMyStats()
      .then(setStats)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
        <LearnerPageHeader eyebrow="Your progress 📈" title="Stats" />

        {error && <p className="text-red-700">{error}</p>}
        {loading && <p className="text-warm-brown-soft">Loading stats…</p>}

        {stats && (
          <div className="grid gap-4 sm:grid-cols-2">
            <article
              className="warm-card border-2 border-amber-300 bg-gradient-to-br from-amber-50/90 to-orange-50/90 p-5 sm:col-span-2"
            >
              <p className="text-sm font-bold text-warm-muted">Practice mistakes 📝</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.unresolved_mistakes}
                <span className="text-lg font-bold text-warm-muted">
                  {" "}
                  word{stats.unresolved_mistakes === 1 ? "" : "s"} to clear
                </span>
              </p>
              <p className="mt-1 text-sm text-warm-brown-soft">
                Recognition review, then spelling — up to 5 words. Completing clears them.
              </p>
              <Link
                to="/app/challenge?mistakes=1"
                className="warm-btn warm-btn-primary mt-4 inline-block text-sm"
              >
                Practice mistakes
              </Link>
            </article>

            <article className="warm-card p-5 sm:col-span-2">
              <p className="text-sm font-bold text-warm-muted">Word strength</p>
              <div className="mt-3 grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="text-2xl font-extrabold text-warm-brown">{stats.learning_count}</p>
                  <p className="text-sm font-semibold text-warm-body">Learning</p>
                </div>
                <div>
                  <p className="text-2xl font-extrabold text-warm-brown">{stats.familiar_count}</p>
                  <p className="text-sm font-semibold text-warm-body">Familiar</p>
                </div>
                <div>
                  <p className="text-2xl font-extrabold text-warm-brown">{stats.mastered_count}</p>
                  <p className="text-sm font-semibold text-warm-body">Mastered</p>
                </div>
              </div>
              <p className="mt-3 text-sm text-warm-brown-soft">
                All released words — strength grows each day you recognize a meaning: Familiar
                after 2 practice days, Mastered after 3+. Spelling is bonus practice.
              </p>
              <Link to="/app/words" className="warm-btn warm-btn-secondary mt-4 inline-block text-sm">
                Browse my words
              </Link>
            </article>

            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">New words this week</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.new_released_this_week ?? 0}
                <span className="text-lg font-bold text-warm-muted">
                  {" "}
                  / {stats.weekly_new_target ?? stats.daily_new_word_goal * 5}
                </span>
              </p>
              <p className="mt-1 text-sm text-warm-brown-soft">
                Today: {stats.new_released_today} / {stats.daily_new_word_goal}
              </p>
            </article>

            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">Daily challenge</p>
              <p className="mt-2 text-2xl font-extrabold text-warm-brown">
                {stats.daily_challenge_completed ? "Completed" : "Not done yet"}
              </p>
              <p className="mt-1 text-sm text-warm-brown-soft">
                Review {stats.daily_challenge_srs_completed ? "✓" : "·"} · Listen &amp; Pick{" "}
                {stats.daily_challenge_dictation_completed ? "✓" : "·"}
              </p>
              <Link to="/app/challenge" className="warm-btn warm-btn-secondary mt-3 inline-block text-sm">
                {stats.daily_challenge_completed ? "Practice again" : "Start challenge"}
              </Link>
            </article>

            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">Review accuracy (30d)</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.review_accuracy_percent}%
              </p>
            </article>
            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">Streak</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.streak_days} day{stats.streak_days === 1 ? "" : "s"}
              </p>
            </article>
            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">Due today</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">{stats.due_count}</p>
            </article>
            <article className="warm-card p-5">
              <p className="text-sm font-bold text-warm-muted">Dictation sessions (30d)</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.dictation_sessions_completed}
              </p>
            </article>
            <article className="warm-card p-5 sm:col-span-2">
              <p className="text-sm font-bold text-warm-muted">Mistake book</p>
              <p className="mt-2 text-3xl font-extrabold text-warm-brown">
                {stats.unresolved_mistakes}
                <span className="text-lg font-bold text-warm-muted">
                  {" "}
                  word{stats.unresolved_mistakes === 1 ? "" : "s"}
                </span>
              </p>
              {stats.unresolved_mistakes === 0 ? (
                <p className="mt-2 text-sm text-warm-brown-soft">
                  No mistakes yet — they appear when you miss a word in review or dictation.
                </p>
              ) : (
                <p className="mt-2 text-sm text-warm-brown-soft">
                  Use the banner above to start a mistake challenge.
                </p>
              )}
            </article>
          </div>
        )}
      </main>
    </PageShell>
  );
}
