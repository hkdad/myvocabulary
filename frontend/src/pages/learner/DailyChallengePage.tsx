import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
  getDictationPrompt,
  giveUpDictation,
  startDictationSession,
  submitDictationAnswer,
  type DictationAnswerResult,
  type DictationPrompt,
  type DictationSession,
} from "../../api/dictation";
import { getMyStats } from "../../api/dashboard";
import {
  completeDailyChallengeSrs,
  getLoopToday,
  type DailyMix,
} from "../../api/loop";
import {
  answerCard,
  completeMistakeChallenge,
  getDueCards,
  initializeMistakeReviews,
  type SrsCard,
} from "../../api/reviews";
import ChallengeRegenPicker from "../../components/ChallengeRegenPicker";
import DictationAudioPlayer from "../../components/DictationAudioPlayer";
import DictationTeachingPanel from "../../components/DictationTeachingPanel";
import FlashcardDeck, { type DefinitionPickFeedback } from "../../components/FlashcardDeck";
import LearnerTopNav from "../../components/LearnerTopNav";
import PageShell from "../../components/PageShell";
import { useLazyDefinitionChoices } from "../../hooks/useLazyDefinitionChoices";
import { AUTO_QUALITY_ADVANCE_MS, qualityFromDefinitionPick } from "../../lib/autoQuality";
import { definitionsMatch } from "../../lib/definitionChoices";
import { shuffleArray } from "../../lib/shuffle";
import { useAuthStore } from "../../stores/authStore";

const MISTAKE_WORD_LIMIT = 5;

type Phase = "loading" | "empty" | "srs" | "dictation" | "done";

export default function DailyChallengePage() {
  const [searchParams] = useSearchParams();
  const mistakesMode = searchParams.get("mistakes") === "1";
  const dictationMode = "choice";

  const learner = useAuthStore((state) => state.user)?.learner;
  const shellVariant = learner?.ui_mode === "kid" ? "kid" : "teen";

  const [phase, setPhase] = useState<Phase>("loading");
  const [practiceAgain, setPracticeAgain] = useState(false);
  const [cards, setCards] = useState<SrsCard[]>([]);
  const [mistakeEntryIds, setMistakeEntryIds] = useState<number[]>([]);
  const [mistakesCleared, setMistakesCleared] = useState(0);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [pickFeedback, setPickFeedback] = useState<DefinitionPickFeedback | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alreadyCompleted, setAlreadyCompleted] = useState(false);
  const [canRegenerate, setCanRegenerate] = useState(false);
  const [bookTitle, setBookTitle] = useState<string | null>(null);
  const [unresolvedMistakes, setUnresolvedMistakes] = useState(0);
  const [attemptCorrect, setAttemptCorrect] = useState(0);
  const [attemptTotal, setAttemptTotal] = useState(0);
  const [attemptPassed, setAttemptPassed] = useState(true);
  const advanceTimerRef = useRef<number | null>(null);
  const clearedRef = useRef(false);
  const attemptCorrectRef = useRef(0);
  const [shuffleKey, setShuffleKey] = useState(0);

  function clearAdvanceTimer() {
    if (advanceTimerRef.current != null) {
      window.clearTimeout(advanceTimerRef.current);
      advanceTimerRef.current = null;
    }
  }

  useEffect(() => clearAdvanceTimer, []);

  useEffect(() => {
    getMyStats()
      .then((stats) => setUnresolvedMistakes(stats.unresolved_mistakes))
      .catch(() => setUnresolvedMistakes(0));
  }, [mistakesMode, phase]);

  const [session, setSession] = useState<DictationSession | null>(null);
  const [prompt, setPrompt] = useState<DictationPrompt | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<DictationAnswerResult | null>(null);
  const [awaitingAdvance, setAwaitingAdvance] = useState(false);
  const [pendingDone, setPendingDone] = useState(false);
  const [teaching, setTeaching] = useState<{ word: string; syllables: string[] } | null>(null);
  const [loadingDictation, setLoadingDictation] = useState(false);

  const finishSession = useCallback(
    async (entryIds: number[]) => {
      if (mistakesMode) {
        if (entryIds.length > 0 && !clearedRef.current) {
          clearedRef.current = true;
          try {
            const result = await completeMistakeChallenge(entryIds);
            setMistakesCleared(result.entry_count);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Could not clear mistake book");
          }
        }
        setPhase("done");
        return;
      }

      setSession(null);
      setPrompt(null);
      setError(null);
      try {
        const mix = await getLoopToday();
        let nextCards = mix.cards ?? [];
        if (nextCards.length === 0) {
          const due = await getDueCards({ dailyChallenge: true });
          nextCards = due.cards;
        }
        if (nextCards.length === 0) {
          setCards([]);
          setPhase("empty");
          return;
        }
        setCards(shuffleArray(nextCards));
        setIndex(0);
        setRevealed(false);
        setPickFeedback(null);
        setAttemptCorrect(0);
        setAttemptTotal(0);
        setAttemptPassed(true);
        attemptCorrectRef.current = 0;
        setShuffleKey((key) => key + 1);
        setPhase("srs");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load recognition review");
      }
    },
    [mistakesMode],
  );

  const applyMix = useCallback(async (mix: DailyMix, forcePractice = false) => {
    setAlreadyCompleted(mix.completed_today);
    setCanRegenerate(Boolean(mix.can_regenerate) && !mix.completed_today);
    setBookTitle(mix.book_title ?? null);
    if (mix.completed_today && !forcePractice) {
      setPhase("done");
      return;
    }

    async function prepareSrsCards(): Promise<boolean> {
      let nextCards = mix.cards ?? [];
      if (nextCards.length === 0) {
        const due = await getDueCards({ dailyChallenge: true });
        nextCards = due.cards;
      }
      if (nextCards.length === 0) {
        setCards([]);
        setPhase("empty");
        return false;
      }
      setCards(shuffleArray(nextCards));
      setIndex(0);
      setRevealed(false);
      setPickFeedback(null);
      setSession(null);
      setPrompt(null);
      setAttemptCorrect(0);
      setAttemptTotal(0);
      setAttemptPassed(true);
      attemptCorrectRef.current = 0;
      setShuffleKey((key) => key + 1);
      return true;
    }

    if (forcePractice) {
      const ok = await prepareSrsCards();
      if (ok) {
        setPhase("srs");
      }
      return;
    }

    if (!mix.dictation_completed) {
      setSession(null);
      setPrompt(null);
      setPhase("dictation");
      return;
    }

    if (!mix.srs_completed) {
      const ok = await prepareSrsCards();
      if (ok) {
        setPhase("srs");
      }
      return;
    }

    setSession(null);
    setPrompt(null);
    setPhase("dictation");
  }, []);

  const loadMistakeChallenge = useCallback(async () => {
    setPhase("loading");
    setError(null);
    setMistakesCleared(0);
    clearedRef.current = false;
    setCanRegenerate(false);
    setAlreadyCompleted(false);
    try {
      await initializeMistakeReviews();
      const due = await getDueCards({ mistakesOnly: true, limit: MISTAKE_WORD_LIMIT });
      if (due.cards.length === 0) {
        setCards([]);
        setMistakeEntryIds([]);
        setPhase("empty");
        return;
      }
      const entryIds = due.cards.map((card) => card.dictionary_entry.id);
      setMistakeEntryIds(entryIds);
      setCards(shuffleArray(due.cards));
      setIndex(0);
      setRevealed(false);
      setPickFeedback(null);
      setSession(null);
      setPrompt(null);
      setAttemptCorrect(0);
      setAttemptTotal(0);
      setAttemptPassed(true);
      attemptCorrectRef.current = 0;
      setShuffleKey((key) => key + 1);
      setPhase("srs");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load mistake words");
      setPhase("empty");
    }
  }, []);

  const loadChallenge = useCallback(
    async (forcePractice = false) => {
      if (mistakesMode) {
        await loadMistakeChallenge();
        return;
      }
      setPhase("loading");
      setError(null);
      try {
        const mix = await getLoopToday();
        await applyMix(mix, forcePractice);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load daily challenge");
        setPhase("empty");
      }
    },
    [applyMix, loadMistakeChallenge, mistakesMode],
  );

  useEffect(() => {
    void loadChallenge();
  }, [loadChallenge]);

  async function handleRegenerated(mix: DailyMix) {
    setPracticeAgain(false);
    setSession(null);
    setPrompt(null);
    setPhase("loading");
    setError(null);
    try {
      await applyMix(mix, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load daily challenge");
      setPhase("empty");
    }
  }

  // Listen & Pick for daily challenge and mistake practice.
  useEffect(() => {
    if (phase !== "dictation" || session) {
      return;
    }
    void (async () => {
      setLoadingDictation(true);
      setError(null);
      try {
        const started = await startDictationSession({
          source: mistakesMode ? "mistakes" : "daily_challenge",
          mode: "choice",
          max_words: mistakesMode ? MISTAKE_WORD_LIMIT : 30,
          entry_ids: mistakesMode ? mistakeEntryIds : undefined,
        });
        setSession(started);
        const nextPrompt = await getDictationPrompt(started.id);
        setPrompt(nextPrompt);
        if (nextPrompt.session_complete) {
          await finishSession(mistakeEntryIds);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not start Listen & Pick");
      } finally {
        setLoadingDictation(false);
      }
    })();
  }, [phase, session, mistakesMode, mistakeEntryIds, finishSession]);

  const currentCard = cards[index];
  const { choices: definitionChoices, clearZhForEntry } = useLazyDefinitionChoices(
    cards,
    index,
    setCards,
    shuffleKey,
  );

  function handleZhCleared(entryId: number) {
    clearZhForEntry(entryId);
    setCards((prev) =>
      prev.map((card) =>
        card.dictionary_entry.id === entryId
          ? {
              ...card,
              dictionary_entry: { ...card.dictionary_entry, definition_zh_hant: null },
            }
          : card,
      ),
    );
  }

  function resetCardState() {
    clearAdvanceTimer();
    setRevealed(false);
    setPickFeedback(null);
  }

  function restartSrsAttempt(nextCards: SrsCard[]) {
    setCards(shuffleArray(nextCards));
    setIndex(0);
    resetCardState();
    attemptCorrectRef.current = 0;
    setShuffleKey((key) => key + 1);
  }

  async function handleRate(quality: number) {
    if (!currentCard || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await answerCard(currentCard.id, quality);
      const scoredCorrect = quality >= 3;
      if (scoredCorrect) {
        attemptCorrectRef.current += 1;
      }
      const nextIndex = index + 1;
      if (nextIndex >= cards.length) {
        const total = cards.length;
        const correct = attemptCorrectRef.current;
        const passed = total > 0 && correct / total >= 0.8;
        setAttemptCorrect(correct);
        setAttemptTotal(total);
        setAttemptPassed(passed);
        if (mistakesMode) {
          setSession(null);
          setPrompt(null);
          setPhase("dictation");
        } else if (alreadyCompleted) {
          if (!passed) {
            restartSrsAttempt(cards);
            setError(
              `Need at least 80% correct (${correct}/${total}) — keep practicing`,
            );
            return;
          }
          setPhase("done");
        } else {
          try {
            await completeDailyChallengeSrs();
            setPhase("done");
          } catch (err) {
            restartSrsAttempt(cards);
            setError(
              err instanceof Error
                ? err.message
                : "Need at least 80% correct — keep practicing",
            );
          }
        }
      } else {
        setIndex(nextIndex);
        resetCardState();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save answer");
    } finally {
      setSubmitting(false);
    }
  }

  function handlePickDefinition(definition: string) {
    if (!currentCard || pickFeedback || submitting) {
      return;
    }
    const isCorrect = definitionsMatch(definition, currentCard.dictionary_entry.definition);
    setPickFeedback({ selected: definition, isCorrect });
    setRevealed(true);
    if (isCorrect) {
      const quality = qualityFromDefinitionPick(isCorrect);
      clearAdvanceTimer();
      advanceTimerRef.current = window.setTimeout(() => {
        void handleRate(quality);
      }, AUTO_QUALITY_ADVANCE_MS);
    }
  }

  function handleSrsContinue() {
    if (!pickFeedback || pickFeedback.isCorrect || submitting) {
      return;
    }
    void handleRate(qualityFromDefinitionPick(false));
  }

  async function loadPrompt(sessionId: number) {
    const nextPrompt = await getDictationPrompt(sessionId);
    setPrompt(nextPrompt);
    setAnswer("");
    setFeedback(null);
    setAwaitingAdvance(false);
    setPendingDone(false);
    setTeaching(null);
    if (nextPrompt.session_complete) {
      await finishSession(mistakesMode ? mistakeEntryIds : []);
    }
  }

  async function handleSubmit(submittedAnswer: string) {
    if (!session || !submittedAnswer.trim() || awaitingAdvance) {
      return;
    }
    setLoadingDictation(true);
    setError(null);
    try {
      const result = await submitDictationAnswer(session.id, {
        answer: submittedAnswer,
        hint_used: false,
      });
      setFeedback(result);
      setSession((current) =>
        current
          ? { ...current, correct_count: result.correct_count, completed: result.session_complete }
          : current,
      );
      if (result.is_correct) {
        if (result.session_complete) {
          await finishSession(mistakesMode ? mistakeEntryIds : []);
        } else {
          setAwaitingAdvance(true);
          clearAdvanceTimer();
          const sessionId = session.id;
          advanceTimerRef.current = window.setTimeout(() => {
            void loadPrompt(sessionId);
          }, AUTO_QUALITY_ADVANCE_MS);
        }
      } else if (result.can_retry || (dictationMode === "choice" && result.retries_remaining > 0)) {
        setAnswer("");
        setFeedback(null);
        if (dictationMode === "choice" && session) {
          await loadPrompt(session.id);
        }
      } else if (result.session_complete) {
        if (result.expected_word && result.syllables) {
          setTeaching({ word: result.expected_word, syllables: result.syllables });
          setPendingDone(true);
        } else {
          await finishSession(mistakesMode ? mistakeEntryIds : []);
        }
      } else if (result.expected_word) {
        setAwaitingAdvance(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit answer");
    } finally {
      setLoadingDictation(false);
    }
  }

  async function handleGiveUp() {
    if (!session || teaching || loadingDictation) {
      return;
    }
    setLoadingDictation(true);
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
      setLoadingDictation(false);
    }
  }

  async function handleContinue() {
    clearAdvanceTimer();
    if (!session) {
      return;
    }
    if (teaching) {
      setTeaching(null);
      if (pendingDone) {
        setPendingDone(false);
        await finishSession(mistakesMode ? mistakeEntryIds : []);
      } else {
        await loadPrompt(session.id);
      }
      return;
    }
    if (pendingDone) {
      setPendingDone(false);
      setAwaitingAdvance(false);
      await finishSession(mistakesMode ? mistakeEntryIds : []);
      return;
    }
    await loadPrompt(session.id);
  }

  const challengeLabel = mistakesMode ? "Daily challenge · Mistakes" : "Daily challenge";

  // Always offer this on the normal daily challenge — not gated on a stats race.
  const practiceMistakesLink = !mistakesMode ? (
    <Link to="/app/challenge?mistakes=1" className="warm-btn warm-btn-primary text-sm">
      Practice mistakes
      {unresolvedMistakes > 0 ? ` (${Math.min(unresolvedMistakes, 5)})` : ""}
    </Link>
  ) : null;

  if (phase === "loading") {
    return (
      <PageShell variant={shellVariant}>
        <main className="mx-auto max-w-2xl p-8">
          <p className="text-warm-brown-soft">
            {mistakesMode ? "Loading mistake words…" : "Loading today\u2019s challenge…"}
          </p>
        </main>
      </PageShell>
    );
  }

  if (phase === "empty") {
    return (
      <PageShell variant={shellVariant}>
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-6 text-center">
          <span className="text-6xl">{mistakesMode ? "✨" : "📭"}</span>
          <h1 className="text-3xl font-extrabold text-warm-brown">
            {mistakesMode ? "No mistakes to clear" : "No challenge words yet"}
          </h1>
          <p className="font-semibold text-warm-body">
            {mistakesMode
              ? "Your mistake book is empty — keep practicing!"
              : "Ask a parent to upload the family word bank, or rebuild from a category / your list."}
          </p>
          {error && <p className="text-red-700">{error}</p>}
          <div className="flex flex-wrap items-center justify-center gap-3">
            {!mistakesMode && canRegenerate && (
              <ChallengeRegenPicker onRegenerated={handleRegenerated} />
            )}
            {practiceMistakesLink}
            <Link to="/app/home" className="warm-btn warm-btn-primary">
              Back home
            </Link>
          </div>
        </main>
      </PageShell>
    );
  }

  if (phase === "done") {
    const score =
      session && session.total_words > 0
        ? Math.round((session.correct_count / session.total_words) * 100)
        : null;
    const attemptScore =
      attemptTotal > 0 ? Math.round((attemptCorrect / attemptTotal) * 100) : null;
    const title = mistakesMode
      ? "Mistake words cleared!"
      : alreadyCompleted && !practiceAgain
        ? "Challenge already done today"
        : attemptPassed
          ? "Challenge complete!"
          : "Keep practicing";
    const body = mistakesMode
      ? mistakesCleared > 0
        ? `You cleared ${mistakesCleared} word${mistakesCleared === 1 ? "" : "s"} from your mistake book.`
        : "You finished review and Listen & Pick."
      : attemptScore !== null
        ? attemptPassed
          ? `You got ${attemptCorrect}/${attemptTotal} right (${attemptScore}%). Great recognizing!`
          : `You got ${attemptCorrect}/${attemptTotal} right (${attemptScore}%). Need at least 80% to finish the day.`
        : "You matched today\u2019s words to their meanings. Great recognizing!";
    return (
      <PageShell variant={shellVariant}>
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-6 text-center">
          <span className="text-6xl">{attemptPassed || mistakesMode ? "🌟" : "💪"}</span>
          <h1 className="text-3xl font-extrabold text-warm-brown">{title}</h1>
          <p className="font-semibold text-warm-body">
            {body}
            {score !== null ? ` Dictation score: ${score}%.` : ""}
          </p>
          {error && <p className="text-red-700">{error}</p>}
          <div className="flex flex-col items-center gap-3">
            {!mistakesMode && attemptPassed && (
              <div className="flex w-full max-w-xs flex-col gap-2">
                <p className="text-sm font-bold text-warm-muted">Bonus practice (optional)</p>
                <Link to="/app/dictation" className="warm-btn warm-btn-secondary">
                  ✍️ Spell today&apos;s words
                </Link>
              </div>
            )}
            <button
              type="button"
              className={`warm-btn w-full max-w-xs ${
                mistakesMode || !attemptPassed ? "warm-btn-primary" : "warm-btn-secondary"
              }`}
              onClick={() => {
                setPracticeAgain(true);
                setAlreadyCompleted(true);
                setSession(null);
                setPrompt(null);
                void loadChallenge(true);
              }}
            >
              {mistakesMode
                ? "Check for more mistakes"
                : attemptPassed
                  ? "Practice again"
                  : "Try again"}
            </button>
            <div className="flex flex-wrap justify-center gap-3">
              <Link to="/app/home" className="warm-btn warm-btn-secondary">
                Home
              </Link>
              {!mistakesMode && (
                <Link to="/app/challenge?mistakes=1" className="warm-btn warm-btn-secondary">
                  Practice mistakes
                  {unresolvedMistakes > 0 ? ` (${Math.min(unresolvedMistakes, 5)})` : ""}
                </Link>
              )}
            </div>
          </div>
        </main>
      </PageShell>
    );
  }

  if (phase === "srs") {
    return (
      <PageShell variant={shellVariant}>
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
          <header className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-warm-muted">
                {mistakesMode
                  ? `${challengeLabel} · Step 1 · Recognition`
                  : `${challengeLabel} · Step 2 · Recognition`}
              </p>
              <h1 className="text-2xl font-extrabold text-warm-brown">
                Review {index + 1} of {cards.length}
              </h1>
              <p className="mt-1 text-sm font-semibold text-warm-brown-soft">
                {mistakesMode
                  ? `Up to ${MISTAKE_WORD_LIMIT} mistake words, then Listen & Pick`
                  : bookTitle
                    ? `New words from ${bookTitle} · bank retention stays warm`
                    : "Step 2: match each word to its meaning (need 80% correct)"}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {!mistakesMode && canRegenerate && !practiceAgain && (
                <ChallengeRegenPicker
                  disabled={submitting}
                  onRegenerated={handleRegenerated}
                />
              )}
              {practiceMistakesLink}
              <LearnerTopNav />
            </div>
          </header>

          {error && <p className="font-semibold text-red-700">{error}</p>}

          {currentCard && (
            <>
              <FlashcardDeck
                card={currentCard}
                revealed={revealed}
                definitionChoices={definitionChoices}
                pickFeedback={pickFeedback}
                onPickDefinition={handlePickDefinition}
                showAudio={false}
                onZhCleared={handleZhCleared}
                onWrongContinue={
                  pickFeedback && !pickFeedback.isCorrect && !submitting
                    ? handleSrsContinue
                    : undefined
                }
              />
              {submitting && (
                <p className="text-center text-sm font-semibold text-warm-muted">Saving…</p>
              )}
            </>
          )}
        </main>
      </PageShell>
    );
  }

  const inputLocked =
    awaitingAdvance || Boolean(teaching) || Boolean(feedback?.is_correct);

  return (
    <PageShell variant={shellVariant}>
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">
              {mistakesMode
                ? `${challengeLabel} · Step 2 · Listen & Pick`
                : `${challengeLabel} · Step 1 · Listen & Pick`}
            </p>
            <h1 className="text-2xl font-extrabold text-warm-brown">Listen & Pick</h1>
            <p className="mt-1 text-sm font-semibold text-warm-brown-soft">
              {mistakesMode
                ? "Listen carefully, then pick the right word"
                : "Step 1: listen carefully, then pick the right word"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {practiceMistakesLink}
            <LearnerTopNav />
          </div>
        </header>

        {error && <p className="font-semibold text-red-700">{error}</p>}
        {loadingDictation && !prompt && (
          <p className="text-warm-brown-soft">
            Starting Listen & Pick…
          </p>
        )}

        {session && prompt && !prompt.session_complete && (
          <section className="warm-card flex flex-col gap-4 p-5">
            <p className="text-sm font-bold text-warm-muted">
              Word {prompt.word_index} of {prompt.total_words}
              {session.correct_count > 0 ? ` · ${session.correct_count} correct` : ""}
            </p>
            <DictationAudioPlayer
              key={`${session.id}-${prompt.word_index}`}
              sessionId={session.id}
              wordIndex={prompt.word_index}
              autoPlay
            />
            {teaching ? (
              <DictationTeachingPanel
                word={teaching.word}
                syllables={teaching.syllables}
                continueLabel="Next word"
                onContinue={() => void handleContinue()}
              />
            ) : dictationMode === "choice" && prompt.choices ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  {prompt.choices.map((choice, choiceIndex) => (
                    <button
                      key={`${prompt.word_index}-${choiceIndex}-${choice}`}
                      type="button"
                      disabled={inputLocked || loadingDictation}
                      onClick={() => void handleSubmit(choice)}
                      className="warm-btn warm-btn-secondary py-4 text-lg font-extrabold disabled:opacity-50"
                    >
                      {choice}
                    </button>
                  ))}
                </div>
                {feedback?.is_correct && (
                  <p className="font-semibold text-green-700">
                    Yes! You got it!
                    {awaitingAdvance ? " Next word…" : ""}
                  </p>
                )}
                {feedback && !feedback.is_correct && (
                  <p className="font-semibold text-amber-800">
                    {feedback.retries_remaining > 0
                      ? `Try again — ${feedback.retries_remaining} left`
                      : "Not quite — listen again and pick another."}
                  </p>
                )}
                {awaitingAdvance && (
                  <button
                    type="button"
                    className="warm-btn warm-btn-primary"
                    onClick={() => void handleContinue()}
                  >
                    Next word
                  </button>
                )}
              </>
            ) : (
              <>
                <input
                  className="warm-input text-lg"
                  value={answer}
                  disabled={inputLocked || loadingDictation}
                  placeholder="Type what you hear"
                  onChange={(event) => setAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      void handleSubmit(answer);
                    }
                  }}
                />
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="warm-btn warm-btn-primary"
                    disabled={inputLocked || !answer.trim()}
                    onClick={() => void handleSubmit(answer)}
                  >
                    Check
                  </button>
                  <button
                    type="button"
                    className="warm-btn warm-btn-secondary"
                    disabled={inputLocked}
                    onClick={() => void handleGiveUp()}
                  >
                    Give up
                  </button>
                </div>
                {feedback?.is_correct && (
                  <p className="font-semibold text-green-700">Correct!</p>
                )}
                {feedback && !feedback.is_correct && feedback.can_retry && (
                  <p className="font-semibold text-amber-800">
                    Try again — {feedback.retries_remaining} left
                  </p>
                )}
                {awaitingAdvance && (
                  <button
                    type="button"
                    className="warm-btn warm-btn-primary"
                    onClick={() => void handleContinue()}
                  >
                    Next word
                  </button>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </PageShell>
  );
}
