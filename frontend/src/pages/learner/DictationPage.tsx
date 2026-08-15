import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  getDictationHint,
  getDictationPrompt,
  giveUpDictation,
  startDictationSession,
  submitDictationAnswer,
  type DictationAnswerResult,
  type DictationPrompt,
  type DictationSession,
} from "../../api/dictation";
import { listAssignedWordLists, type WordListSummary } from "../../api/wordLists";
import DictationAudioPlayer from "../../components/DictationAudioPlayer";
import DictationTeachingPanel from "../../components/DictationTeachingPanel";
import LearnerTopNav from "../../components/LearnerTopNav";
import PageShell from "../../components/PageShell";

type Phase = "setup" | "active" | "done";
type DictationMode = "typed" | "choice";

type DictationPageProps = {
  mode: DictationMode;
};

const COPY: Record<
  DictationMode,
  {
    label: string;
    title: string;
    subtitle: string;
    startButton: string;
    activePrompt: string;
    correctFeedback: string;
    completeTitle: string;
  }
> = {
  typed: {
    label: "Dictation ✍️",
    title: "Listen and spell",
    subtitle: "Bonus spelling practice — type what you hear.",
    startButton: "Start dictation",
    activePrompt: "Listen, then type the word.",
    correctFeedback: "Correct!",
    completeTitle: "Dictation complete!",
  },
  choice: {
    label: "Listen & Pick 🎧",
    title: "Listen and pick",
    subtitle: "Pick the right word — hints are OK!",
    startButton: "Start Listen & Pick",
    activePrompt: "Listen carefully, then pick the word!",
    correctFeedback: "Yes! You got it! 🌟",
    completeTitle: "Listen & Pick complete!",
  },
};

export default function DictationPage({ mode }: DictationPageProps) {
  const copy = COPY[mode];
  const [searchParams] = useSearchParams();
  const listIdParam = searchParams.get("list_id");

  const [phase, setPhase] = useState<Phase>("setup");
  const [lists, setLists] = useState<WordListSummary[]>([]);
  const [selectedListId, setSelectedListId] = useState<
    number | "mistakes" | "daily_challenge" | null
  >("daily_challenge");
  const [session, setSession] = useState<DictationSession | null>(null);
  const [prompt, setPrompt] = useState<DictationPrompt | null>(null);
  const [answer, setAnswer] = useState("");
  const [hint, setHint] = useState<string | null>(null);
  const [hintUsed, setHintUsed] = useState(false);
  const [feedback, setFeedback] = useState<DictationAnswerResult | null>(null);
  const [awaitingAdvance, setAwaitingAdvance] = useState(false);
  const [pendingDone, setPendingDone] = useState(false);
  const [teaching, setTeaching] = useState<{ word: string; syllables: string[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAssignedWordLists()
      .then((assigned) => {
        setLists(assigned);
        if (listIdParam) {
          setSelectedListId(Number(listIdParam));
        }
      })
      .catch((err: Error) => setError(err.message));
  }, [listIdParam]);

  const loadPrompt = useCallback(async (sessionId: number) => {
    const nextPrompt = await getDictationPrompt(sessionId);
    setPrompt(nextPrompt);
    setAnswer("");
    setHint(null);
    setHintUsed(false);
    setFeedback(null);
    setAwaitingAdvance(false);
    setPendingDone(false);
    setTeaching(null);
    if (nextPrompt.session_complete) {
      setPhase("done");
    }
  }, []);

  async function handleStart() {
    if (selectedListId === null) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const payload =
        selectedListId === "mistakes"
          ? { source: "mistakes" as const, mode }
          : selectedListId === "daily_challenge"
            ? { source: "daily_challenge" as const, mode, max_words: 30 }
            : { word_list_id: selectedListId, source: "word_list" as const, mode };
      const started = await startDictationSession(payload);
      setSession(started);
      setPhase("active");
      await loadPrompt(started.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start session");
    } finally {
      setLoading(false);
    }
  }

  async function handleHint() {
    if (!session || mode !== "choice") {
      return;
    }
    try {
      const hintText = await getDictationHint(session.id);
      setHint(hintText);
      setHintUsed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load hint");
    }
  }

  async function handleSubmit(submittedAnswer: string) {
    if (!session || !submittedAnswer.trim() || awaitingAdvance) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await submitDictationAnswer(session.id, {
        answer: submittedAnswer,
        hint_used: hintUsed,
      });
      setFeedback(result);
      setSession((current) =>
        current
          ? { ...current, correct_count: result.correct_count, completed: result.session_complete }
          : current,
      );
      if (result.is_correct) {
        if (result.session_complete) {
          setPhase("done");
        } else {
          setAwaitingAdvance(true);
        }
      } else if (mode === "typed" && result.can_retry) {
        setAnswer("");
      } else if (result.session_complete) {
        if (result.expected_word && result.syllables) {
          setTeaching({
            word: result.expected_word,
            syllables: result.syllables,
          });
          setPendingDone(true);
        } else {
          setPhase("done");
        }
      } else if (result.expected_word) {
        setAwaitingAdvance(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit answer");
    } finally {
      setLoading(false);
    }
  }

  async function handleGiveUp() {
    if (!session || mode !== "typed" || teaching || loading) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await giveUpDictation(session.id);
      setSession((current) =>
        current
          ? { ...current, correct_count: result.correct_count, completed: result.session_complete }
          : current,
      );
      setFeedback(null);
      setAnswer("");
      setTeaching({
        word: result.expected_word ?? "",
        syllables: result.syllables ?? (result.expected_word ? [result.expected_word] : []),
      });
      setPendingDone(result.session_complete);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not give up");
    } finally {
      setLoading(false);
    }
  }

  async function handleContinue() {
    if (!session) {
      return;
    }
    if (teaching) {
      setTeaching(null);
      if (pendingDone) {
        setPendingDone(false);
        setPhase("done");
      } else {
        await loadPrompt(session.id);
      }
      return;
    }
    if (pendingDone) {
      setPendingDone(false);
      setAwaitingAdvance(false);
      setPhase("done");
      return;
    }
    await loadPrompt(session.id);
  }

  const triesLeft =
    feedback && !feedback.is_correct && feedback.retries_remaining > 0
      ? feedback.retries_remaining
      : (prompt?.retries_remaining ?? 0);

  const inputLocked =
    loading || awaitingAdvance || Boolean(teaching) || Boolean(feedback?.is_correct);

  const selectedList =
    typeof selectedListId === "number" ? lists.find((list) => list.id === selectedListId) : null;
  const canStartDictation =
    selectedListId === "mistakes" ||
    selectedListId === "daily_challenge" ||
    (selectedList != null && selectedList.item_count > 0);

  if (phase === "setup") {
    return (
      <PageShell variant="teen">
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
          <header className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-warm-muted">{copy.label}</p>
              <h1 className="text-3xl font-extrabold text-warm-brown">{copy.title}</h1>
              <p className="mt-1 font-semibold text-warm-brown-soft">{copy.subtitle}</p>
            </div>
            <LearnerTopNav />
          </header>

          <section className="warm-card flex flex-col gap-4 p-5">
            <label className="text-sm font-bold text-warm-body" htmlFor="dictation-source">
              Choose words
            </label>
            <select
              id="dictation-source"
              value={selectedListId ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                if (value === "mistakes" || value === "daily_challenge") {
                  setSelectedListId(value);
                } else {
                  setSelectedListId(Number(value));
                }
              }}
              className="rounded-xl border border-amber-200 bg-white px-4 py-3 font-semibold text-warm-brown"
            >
              <option value="daily_challenge">Today&apos;s challenge</option>
              {lists.map((list) => (
                <option key={list.id} value={list.id}>
                  {list.name} ({list.item_count} words)
                </option>
              ))}
              <option value="mistakes">Practice my mistakes</option>
            </select>
            <button
              type="button"
              onClick={() => void handleStart()}
              disabled={loading || selectedListId === null || !canStartDictation}
              className="warm-btn warm-btn-primary"
            >
              {loading ? "Starting…" : copy.startButton}
            </button>
            {selectedList && selectedList.item_count === 0 && (
              <p className="text-sm font-semibold text-amber-800">
                Add words to this list before starting dictation.
              </p>
            )}
          </section>

          {error && <p className="text-red-700">{error}</p>}
          <Link to="/app/home" className="warm-btn warm-btn-secondary text-center">
            Back home
          </Link>
        </main>
      </PageShell>
    );
  }

  if (phase === "done" && session) {
    const score =
      session.total_words > 0
        ? Math.round((session.correct_count / session.total_words) * 100)
        : 0;
    return (
      <PageShell variant="teen">
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-6 text-center">
          <span className="text-6xl">{score >= 80 ? "🎉" : "💪"}</span>
          <h1 className="text-3xl font-extrabold text-warm-brown">{copy.completeTitle}</h1>
          <p className="text-lg font-semibold text-warm-body">
            {session.correct_count} / {session.total_words} correct ({score}%)
          </p>
          <p className="text-sm text-warm-brown-soft">
            {score < 100
              ? "Mistakes were added to your review queue."
              : "Perfect round — amazing work!"}
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={() => {
                setPhase("setup");
                setSession(null);
                setPrompt(null);
                setFeedback(null);
                setAwaitingAdvance(false);
                setPendingDone(false);
                setTeaching(null);
              }}
              className="warm-btn warm-btn-primary"
            >
              Try again
            </button>
            <Link to="/app/review" className="warm-btn warm-btn-secondary">
              Review cards
            </Link>
            <Link to="/app/home" className="warm-btn warm-btn-ghost">
              Home
            </Link>
          </div>
        </main>
      </PageShell>
    );
  }

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">{copy.label}</p>
            <h1 className="text-2xl font-extrabold text-warm-brown">
              Word {prompt?.word_index ?? 0} of {prompt?.total_words ?? session?.total_words ?? 0}
            </h1>
          </div>
          <LearnerTopNav />
        </header>

        <section className="warm-card flex flex-col items-center gap-4 p-6 text-center">
          <p className="font-semibold text-warm-body">{copy.activePrompt}</p>
          {session && prompt && !teaching && (
            <DictationAudioPlayer
              key={`${session.id}-${prompt.word_index}`}
              sessionId={session.id}
              wordIndex={prompt.word_index}
              autoPlay
            />
          )}
        </section>

        {teaching && (
          <DictationTeachingPanel
            word={teaching.word}
            syllables={teaching.syllables}
            onContinue={() => void handleContinue()}
            continueLabel={pendingDone ? "See results" : "Next word →"}
          />
        )}

        {!teaching && mode === "choice" && prompt?.choices && (
          <section className="grid grid-cols-2 gap-3">
            {prompt.choices.map((choice) => (
              <button
                key={choice}
                type="button"
                disabled={inputLocked}
                onClick={() => void handleSubmit(choice)}
                className="warm-btn warm-btn-secondary py-4 text-lg font-extrabold disabled:opacity-50"
              >
                {choice}
              </button>
            ))}
          </section>
        )}

        {!teaching && mode === "typed" && (
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void handleSubmit(answer);
            }}
          >
            <input
              value={answer}
              onChange={(event) => {
                setAnswer(event.target.value);
                if (feedback && !feedback.is_correct) {
                  setFeedback(null);
                }
              }}
              placeholder="Type the word you heard"
              className="rounded-xl border border-amber-200 bg-white px-4 py-3 text-lg text-warm-brown disabled:opacity-50"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              disabled={inputLocked}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={inputLocked || !answer.trim()}
                className="warm-btn warm-btn-primary flex-1 disabled:opacity-50"
              >
                Check spelling
              </button>
              <button
                type="button"
                onClick={() => void handleGiveUp()}
                disabled={loading || Boolean(teaching)}
                className="warm-btn warm-btn-ghost shrink-0 disabled:opacity-50"
              >
                Give up
              </button>
            </div>
          </form>
        )}

        {!teaching && mode === "choice" && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => void handleHint()}
              disabled={inputLocked || Boolean(hint)}
              className="warm-btn warm-btn-ghost text-sm disabled:opacity-50"
            >
              💡 Need a hint?
            </button>
            <p className="text-sm font-semibold text-warm-brown-soft">Tries left: {triesLeft}</p>
          </div>
        )}

        {hint && (
          <p className="warm-card bg-amber-50/80 p-4 text-center font-semibold text-warm-body">
            {hint}
          </p>
        )}

        {!teaching && feedback && (
          <section
            className={`warm-card p-4 text-center font-semibold ${
              feedback.is_correct ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
            }`}
          >
            {feedback.is_correct
              ? copy.correctFeedback
              : feedback.expected_word
                ? `Not quite — it was “${feedback.expected_word}”`
                : "Not quite — try again!"}
          </section>
        )}

        {!teaching && awaitingAdvance && (
          <button
            type="button"
            onClick={() => void handleContinue()}
            className="warm-btn warm-btn-primary"
          >
            {pendingDone ? "See results" : "Next word →"}
          </button>
        )}

        {error && <p className="text-red-700">{error}</p>}
      </main>
    </PageShell>
  );
}
