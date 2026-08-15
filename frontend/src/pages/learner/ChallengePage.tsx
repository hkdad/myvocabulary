import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getMyStats, type LearnerMeStats } from "../../api/dashboard";
import {
  getAvailableChallenges,
  getChallengeBadges,
  startChallenge,
  submitChallenge,
  type ChallengeResult,
  type ChallengeSession,
  type ChallengeSummary,
  type LearnerBadge,
} from "../../api/challenges";
import PageShell from "../../components/PageShell";
import LearnerTopNav from "../../components/LearnerTopNav";

type Phase = "list" | "active" | "done";

export default function ChallengePage() {
  const [phase, setPhase] = useState<Phase>("list");
  const [challenges, setChallenges] = useState<ChallengeSummary[]>([]);
  const [badges, setBadges] = useState<LearnerBadge[]>([]);
  const [stats, setStats] = useState<LearnerMeStats | null>(null);
  const [session, setSession] = useState<ChallengeSession | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<ChallengeResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [available, badgeData, meStats] = await Promise.all([
        getAvailableChallenges(),
        getChallengeBadges(),
        getMyStats(),
      ]);
      setChallenges(available.challenges);
      setBadges(badgeData.badges);
      setStats(meStats);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load challenges");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleStart(challenge: ChallengeSummary) {
    setLoading(true);
    setError(null);
    try {
      const started = await startChallenge({
        challenge_type: challenge.challenge_type,
        challenge_id: challenge.id,
        target_level: challenge.target_level,
      });
      setSession(started);
      setAnswers({});
      setResult(null);
      setPhase("active");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start challenge");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const payload = session.words.map((word) => ({
        dictionary_entry_id: word.dictionary_entry_id,
        answer: answers[word.dictionary_entry_id] ?? "",
      }));
      const outcome = await submitChallenge(session.id, payload);
      setResult(outcome);
      setPhase("done");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit challenge");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">
              Challenges 🎯
            </p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Level-up & more</h1>
          </div>
          <LearnerTopNav />
        </header>

        {error && <p className="text-red-700">{error}</p>}
        {loading && phase === "list" && (
          <p className="text-warm-brown-soft">Loading challenges…</p>
        )}

        {phase === "list" && !loading && (
          <>
            {stats && stats.unresolved_mistakes > 0 && (
              <section
                className="warm-card border-2 border-amber-300 bg-gradient-to-br from-amber-50/90 to-orange-50/90 p-5"
              >
                <p className="text-sm font-bold text-warm-muted">Mistake challenge 📝</p>
                <p className="mt-1 font-extrabold text-warm-brown">
                  {stats.unresolved_mistakes} word{stats.unresolved_mistakes === 1 ? "" : "s"} in your mistake book
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
              </section>
            )}

            <section className="grid gap-3">
              {challenges.length === 0 ? (
                <p className="warm-card p-5 text-warm-body">
                  No challenges right now — keep reviewing and come back soon!
                </p>
              ) : (
                challenges.map((challenge) => {
                  const readinessPct =
                    challenge.readiness_score != null
                      ? Math.round(challenge.readiness_score * 100)
                      : null;
                  return (
                    <article key={challenge.challenge_type} className="warm-card p-5">
                      <p className="font-extrabold text-warm-brown">{challenge.title}</p>
                      <p className="mt-1 text-sm text-warm-brown-soft">{challenge.description}</p>
                      {challenge.target_level && (
                        <p className="mt-1 text-sm font-semibold text-warm-accent">
                          Target: {challenge.target_level}
                        </p>
                      )}
                      {!challenge.can_start && challenge.lock_reason && (
                        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2">
                          <p className="text-sm font-semibold text-amber-900">
                            {challenge.lock_reason}
                          </p>
                          {readinessPct != null && (
                            <div className="mt-2 h-2 overflow-hidden rounded-full bg-amber-100">
                              <div
                                className="h-full rounded-full bg-amber-400 transition-all"
                                style={{ width: `${Math.min(100, readinessPct)}%` }}
                              />
                            </div>
                          )}
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => void handleStart(challenge)}
                        className="warm-btn warm-btn-primary mt-4 text-sm"
                        disabled={!challenge.can_start}
                      >
                        {challenge.can_start ? "Start challenge" : "Locked"}
                      </button>
                    </article>
                  );
                })
              )}
            </section>

            {badges.length > 0 && (
              <section className="warm-card p-5">
                <h2 className="font-extrabold text-warm-brown">Your badges 🏅</h2>
                <ul className="mt-3 space-y-2 text-sm text-warm-body">
                  {badges.map((badge) => (
                    <li key={badge.id}>
                      {badge.badge_type.replace(/_/g, " ")} ·{" "}
                      {new Date(badge.earned_at).toLocaleDateString()}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        {phase === "active" && session && (
          <section className="warm-card space-y-4 p-5">
            <p className="font-bold text-warm-brown-soft">
              Pick the right word for each meaning ({session.total_words} words)
            </p>
            {session.words.map((word) => (
              <div key={word.dictionary_entry_id} className="rounded-2xl bg-white/70 p-4">
                <p className="text-sm font-semibold text-warm-body">
                  {word.word_index}. {word.definition ?? "Pick the word"}
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  {word.choices.map((choice) => {
                    const selected = answers[word.dictionary_entry_id] === choice;
                    return (
                      <button
                        key={choice}
                        type="button"
                        onClick={() =>
                          setAnswers((current) => ({
                            ...current,
                            [word.dictionary_entry_id]: choice,
                          }))
                        }
                        className={`warm-btn text-sm font-bold ${
                          selected ? "warm-btn-primary" : "warm-btn-secondary"
                        }`}
                      >
                        {choice}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => void handleSubmit()}
              className="warm-btn warm-btn-primary w-full"
              disabled={loading || Object.keys(answers).length < session.total_words}
            >
              {loading ? "Checking…" : "Submit answers"}
            </button>
          </section>
        )}

        {phase === "done" && result && (
          <section
            className={`warm-card p-6 text-center ${
              result.passed
                ? "bg-gradient-to-br from-green-50 to-amber-50"
                : "bg-gradient-to-br from-red-50 to-orange-50"
            }`}
          >
            <p className="text-4xl">{result.passed ? "✅" : "💪"}</p>
            <h2 className="mt-2 text-2xl font-extrabold text-warm-brown">
              {result.passed ? "You passed!" : "Keep practicing!"}
            </h2>
            <p className="mt-2 text-warm-body">
              Score: {Math.round(result.score * 100)}% ({result.correct_count}/{result.total_words})
            </p>
            {result.badge_earned && (
              <p className="mt-2 font-bold text-warm-accent">
                Badge earned: {result.badge_earned.replace(/_/g, " ")}
              </p>
            )}
            {result.new_english_level && (
              <p className="mt-2 font-bold text-warm-brown">
                New level: {result.new_english_level}
              </p>
            )}
            <button
              type="button"
              onClick={() => {
                setPhase("list");
                setSession(null);
                setResult(null);
              }}
              className="warm-btn warm-btn-secondary mt-4"
            >
              Back to challenges
            </button>
          </section>
        )}
      </main>
    </PageShell>
  );
}
