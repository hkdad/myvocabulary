import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  getDashboardOverview,
  getFamilyTrends,
  type FamilyTrends,
  type LearnerProgressSummary,
} from "../../api/dashboard";
import { getLevelSuggestion, type LevelSuggestion } from "../../api/levelAssessment";
import BrandMark from "../../components/BrandMark";
import FamilyTrendCharts from "../../components/FamilyTrendCharts";
import LearnerAvatar from "../../components/LearnerAvatar";
import LevelSuggestionCard from "../../components/LevelSuggestionCard";
import PageShell from "../../components/PageShell";
import { useAuthStore } from "../../stores/authStore";

const QUICK_LINKS = [
  {
    to: "/parent/learners",
    emoji: "👧👦",
    title: "Your learners",
    hint: "Manage learner profiles",
    color: "from-orange-50 to-amber-50",
  },
  {
    to: "/parent/word-bank",
    emoji: "📖",
    title: "Review word bank",
    hint: "Browse your uploaded CSV",
    color: "from-blue-50 to-indigo-50",
  },
  {
    to: "/parent/word-lists",
    emoji: "📚",
    title: "Word lists & catalog",
    hint: "Assign lists to each child",
    color: "from-green-50 to-teal-50",
  },
];

export default function DashboardPage() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [learners, setLearners] = useState<LearnerProgressSummary[]>([]);
  const [trends, setTrends] = useState<FamilyTrends | null>(null);
  const [suggestions, setSuggestions] = useState<Record<number, LevelSuggestion | null>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadDashboard() {
    setLoading(true);
    setError(null);
    try {
      const [overview, familyTrends] = await Promise.all([
        getDashboardOverview(),
        getFamilyTrends(14),
      ]);
      setLearners(overview);
      setTrends(familyTrends);
      const suggestionEntries = await Promise.all(
        overview.map(async (learner) => {
          try {
            const suggestion = await getLevelSuggestion(learner.learner_id);
            return [learner.learner_id, suggestion] as const;
          } catch {
            return [learner.learner_id, null] as const;
          }
        }),
      );
      setSuggestions(Object.fromEntries(suggestionEntries));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="mb-2 text-sm font-bold text-warm-muted">Parent corner 🏠</p>
            <BrandMark size="sm" />
            <p className="mt-3 text-lg text-warm-body">
              Hi <strong>{user?.username}</strong> — here&apos;s the family learning hub 💛
            </p>
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            className="warm-btn warm-btn-secondary text-sm"
          >
            Sign out 👋
          </button>
        </header>

        <section className="warm-card bg-gradient-to-br from-green-50/90 to-amber-50/90 p-6">
          <div className="flex items-start gap-4">
            <span className="text-4xl">📊</span>
            <div>
              <h2 className="text-xl font-extrabold text-warm-brown">Family progress</h2>
              <p className="mt-1 text-warm-body">
                Live stats and 14-day learning trends from reviews and daily challenges.
              </p>
            </div>
          </div>
          {error && <p className="mt-3 text-sm text-red-700">{error}</p>}
          {loading && <p className="mt-3 text-sm text-warm-brown-soft">Loading family stats…</p>}
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {learners.map((learner) => (
              <article key={learner.learner_id} className="rounded-2xl bg-white/70 p-4">
                <LearnerAvatar learner={learner} size="sm" className="mb-2 rounded-xl" />
                <p className="font-bold text-warm-brown">{learner.display_name}</p>
                <p className="text-sm text-warm-brown-soft">
                  Level {learner.english_level}
                </p>
                <ul className="mt-3 space-y-1 text-sm text-warm-body">
                  <li>
                    <strong>{learner.due_count}</strong> cards due ·{" "}
                    <strong>{learner.reviewed_today}</strong> reviewed today
                  </li>
                  <li>
                    Daily practice: <strong>{learner.daily_new_word_goal}</strong> new +{" "}
                    <strong>{learner.daily_learning_retention_goal}</strong> learning/familiar +{" "}
                    <strong>{learner.daily_mastered_retention_goal}</strong> mastered (
                    {learner.daily_practice_goal} cards)
                  </li>
                  <li>
                    New dripped today: <strong>{learner.new_released_today}</strong> /{" "}
                    {learner.daily_new_word_goal}
                  </li>
                  <li>
                    Learning <strong>{learner.learning_count}</strong> · Familiar{" "}
                    <strong>{learner.familiar_count}</strong> · Mastered{" "}
                    <strong>{learner.mastered_count}</strong>
                  </li>
                  <li>
                    Accuracy: <strong>{learner.review_accuracy_percent}%</strong> · Streak:{" "}
                    <strong>{learner.streak_days}</strong>d
                  </li>
                  {learner.due_overloaded && (
                    <li className="font-semibold text-amber-800">
                      Due queue is high — consider lowering new words/day.
                    </li>
                  )}
                  {learner.daily_challenge_completed && (
                    <li className="text-green-700">
                      Daily challenge completed today ✓ (recognition review)
                    </li>
                  )}
                </ul>
              </article>
            ))}
          </div>
          {!loading && trends && <FamilyTrendCharts trends={trends} />}
        </section>

        <section className="warm-card p-6">
          <h2 className="text-lg font-extrabold text-warm-brown">Level readiness 📊</h2>
          <p className="mt-1 text-sm text-warm-brown-soft">
            Readiness scores and level checks — Accept only when you agree a child should move.
          </p>
          <div className="mt-4 grid gap-3">
            {learners.map((learner) => (
              <LevelSuggestionCard
                key={learner.learner_id}
                learnerId={learner.learner_id}
                learnerName={learner.display_name}
                initialSuggestion={suggestions[learner.learner_id] ?? null}
                onUpdated={() => void loadDashboard()}
              />
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-extrabold text-warm-brown">
            <span>⚡</span> Quick links
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {QUICK_LINKS.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`warm-card block bg-gradient-to-br p-5 transition hover:scale-[1.02] ${link.color}`}
              >
                <span className="text-3xl">{link.emoji}</span>
                <p className="mt-2 font-extrabold text-warm-brown">{link.title}</p>
                <p className="text-sm text-warm-brown-soft">{link.hint}</p>
              </Link>
            ))}
          </div>
        </section>

        <p className="text-center text-sm font-semibold text-warm-faint">
          You&apos;re doing great keeping the kids learning 🌱
        </p>
      </main>
    </PageShell>
  );
}
