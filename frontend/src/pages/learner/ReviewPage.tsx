import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import {
  answerCard,
  getDueCards,
  getReviewStats,
  initializeReviews,
  type ReviewStats,
  type SrsCard,
} from "../../api/reviews";
import { getWordList, listAssignedWordLists, type WordListSummary } from "../../api/wordLists";
import { getMyStats } from "../../api/dashboard";
import FlashcardDeck, { type DefinitionPickFeedback } from "../../components/FlashcardDeck";
import LearnerTopNav from "../../components/LearnerTopNav";
import PageShell from "../../components/PageShell";
import { useLazyDefinitionChoices } from "../../hooks/useLazyDefinitionChoices";
import { AUTO_QUALITY_ADVANCE_MS, qualityFromDefinitionPick } from "../../lib/autoQuality";
import { definitionsMatch } from "../../lib/definitionChoices";

type ReviewSource = "all" | "daily" | number;

export default function ReviewPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const listIdParam = searchParams.get("list_id");
  const wordListId = listIdParam ? Number(listIdParam) : undefined;
  const mistakesOnly = searchParams.get("mistakes") === "1";
  const dailyParam = searchParams.get("daily") === "1";
  const skipSetup = Boolean(wordListId || dailyParam);

  useEffect(() => {
    if (mistakesOnly) {
      navigate("/app/challenge?mistakes=1", { replace: true });
    }
  }, [mistakesOnly, navigate]);

  const [phase, setPhase] = useState<"setup" | "active">(skipSetup ? "active" : "setup");
  const [lists, setLists] = useState<WordListSummary[]>([]);
  const [mistakeWordCount, setMistakeWordCount] = useState(0);
  // Default to today's challenge so Extra review matches Daily Challenge practice.
  const [selectedSource, setSelectedSource] = useState<ReviewSource>(
    dailyParam ? "daily" : wordListId ?? "daily",
  );

  const [cards, setCards] = useState<SrsCard[]>([]);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [pickFeedback, setPickFeedback] = useState<DefinitionPickFeedback | null>(null);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [listName, setListName] = useState<string | null>(null);
  const [loading, setLoading] = useState(skipSetup);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionDone, setSessionDone] = useState(false);
  const [isHomeworkList, setIsHomeworkList] = useState(false);
  const advanceTimerRef = useRef<number | null>(null);

  function clearAdvanceTimer() {
    if (advanceTimerRef.current != null) {
      window.clearTimeout(advanceTimerRef.current);
      advanceTimerRef.current = null;
    }
  }

  useEffect(() => clearAdvanceTimer, []);

  useEffect(() => {
    if (phase !== "setup") {
      return;
    }
    listAssignedWordLists()
      .then(setLists)
      .catch((err: Error) => setError(err.message));
    getMyStats()
      .then((stats) => setMistakeWordCount(stats.unresolved_mistakes))
      .catch(() => setMistakeWordCount(0));
  }, [phase]);

  const loadSession = useCallback(async (source: ReviewSource) => {
    setLoading(true);
    setError(null);
    setPhase("active");
    try {
      let homeworkList = false;
      if (typeof source === "number") {
        await initializeReviews(source);
      }

      if (typeof source === "number") {
        try {
          const list = await getWordList(source);
          setListName(list.name);
          homeworkList = list.source === "learner";
        } catch {
          setListName(null);
        }
      } else if (source === "daily") {
        setListName("Today's challenge");
      } else {
        setListName(null);
      }
      setIsHomeworkList(homeworkList);

      const dueOptions =
        source === "daily"
          ? { dailyChallenge: true as const }
          : typeof source === "number"
            ? { wordListId: source, practiceAll: homeworkList || undefined }
            : undefined;

      const [due, reviewStats] = await Promise.all([
        getDueCards(dueOptions),
        getReviewStats(),
      ]);
      setCards(due.cards);
      setStats(reviewStats);
      setIndex(0);
      setRevealed(false);
      setPickFeedback(null);
      setSessionDone(due.cards.length === 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load review session");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!skipSetup) {
      return;
    }
    void loadSession(dailyParam ? "daily" : wordListId !== undefined ? wordListId : "daily");
  }, [skipSetup, dailyParam, wordListId, loadSession]);

  const currentCard = cards[index];
  const { choices: definitionChoices, clearZhForEntry, loadingDefinitions, definitionUnavailable } =
    useLazyDefinitionChoices(cards, index, setCards);

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

  function goToCard(nextIndex: number) {
    if (nextIndex < 0 || nextIndex >= cards.length) {
      return;
    }
    setIndex(nextIndex);
    resetCardState();
  }

  function handlePrevious() {
    goToCard(index - 1);
  }

  function handleNext() {
    goToCard(index + 1);
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

  function handleReviewContinue() {
    if (!pickFeedback || pickFeedback.isCorrect || submitting) {
      return;
    }
    void handleRate(qualityFromDefinitionPick(false));
  }

  async function handleRate(quality: number) {
    if (!currentCard || submitting) {
      return;
    }
    setSubmitting(true);
    try {
      await answerCard(currentCard.id, quality);
      const nextIndex = index + 1;
      if (nextIndex >= cards.length) {
        const updatedStats = await getReviewStats();
        setStats(updatedStats);
        setSessionDone(true);
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

  if (phase === "setup") {
    return (
      <PageShell variant="teen">
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-6 sm:p-8">
          <header className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-warm-muted">SRS Review 🧠</p>
              <h1 className="text-3xl font-extrabold text-warm-brown">Choose words</h1>
              <p className="mt-1 font-semibold text-warm-brown-soft">
                Starts with today&apos;s challenge — or pick all due cards or a list.
              </p>
            </div>
            <LearnerTopNav />
          </header>

          <section className="warm-card flex flex-col gap-4 p-5">
            <label className="text-sm font-bold text-warm-body" htmlFor="review-source">
              Word source
            </label>
            <select
              id="review-source"
              value={
                selectedSource === "all" || selectedSource === "daily"
                  ? selectedSource
                  : String(selectedSource)
              }
              onChange={(event) => {
                const value = event.target.value;
                if (value === "all" || value === "daily") {
                  setSelectedSource(value);
                } else {
                  setSelectedSource(Number(value));
                }
              }}
              className="rounded-xl border border-amber-200 bg-white px-4 py-3 font-semibold text-warm-brown"
            >
              <option value="daily">Today&apos;s challenge</option>
              <option value="all">All due cards</option>
              {lists.map((list) => (
                <option key={list.id} value={list.id}>
                  {list.name} ({list.item_count} words)
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => void loadSession(selectedSource)}
              className="warm-btn warm-btn-primary"
            >
              Start review
            </button>
          </section>

          {mistakeWordCount > 0 && (
            <section className="warm-card flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-bold text-warm-muted">Mistake challenge 📝</p>
                <p className="mt-1 font-semibold text-warm-body">
                  {mistakeWordCount} mistake word{mistakeWordCount === 1 ? "" : "s"} — daily challenge with up to 5 words.
                </p>
              </div>
              <Link
                to="/app/challenge?mistakes=1"
                className="warm-btn warm-btn-secondary shrink-0"
              >
                Practice mistakes
              </Link>
            </section>
          )}

          {error && <p className="text-red-700">{error}</p>}
          <Link to="/app/home" className="warm-btn warm-btn-secondary text-center">
            Back home
          </Link>
        </main>
      </PageShell>
    );
  }

  if (loading) {
    return (
      <PageShell variant="teen">
        <main className="mx-auto max-w-2xl p-8">
          <p className="text-warm-brown-soft">Loading your cards…</p>
        </main>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell variant="teen">
        <main className="mx-auto max-w-2xl p-8">
          <p className="text-red-700">{error}</p>
          <button
            type="button"
            onClick={() => void loadSession(selectedSource)}
            className="warm-btn warm-btn-primary mt-4"
          >
            Try again
          </button>
        </main>
      </PageShell>
    );
  }

  if (sessionDone) {
    return (
      <PageShell variant="teen">
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-6 text-center">
          <span className="text-6xl">✨</span>
          <h1 className="text-3xl font-extrabold text-warm-brown">
            {cards.length === 0
              ? isHomeworkList
                ? "No words to practice"
                : "No cards due right now"
              : isHomeworkList
                ? "Homework complete!"
                : "Session complete!"}
          </h1>
          <p className="font-semibold text-warm-body">
            {cards.length === 0
              ? selectedSource === "daily"
                ? "No challenge words yet — open Home first."
                : isHomeworkList
                  ? listName
                    ? `No words in “${listName}” yet — add spelling words first.`
                    : "Add spelling words to your school list first."
                  : listName
                    ? `No due cards in “${listName}” yet.`
                    : "Open a word list and tap Start Learning to add flashcards."
              : `You reviewed ${cards.length} card${cards.length === 1 ? "" : "s"}${
                  listName ? ` from “${listName}”` : ""
                }.`}
          </p>
          {stats && (
            <p className="text-sm text-warm-brown-soft">
              Today: {stats.reviewed_today} / {stats.daily_goal} goal
            </p>
          )}
          <div className="flex flex-wrap justify-center gap-3">
            <Link to="/app/home" className="warm-btn warm-btn-secondary">
              Home
            </Link>
            <button
              type="button"
              className="warm-btn warm-btn-primary"
              onClick={() => {
                setPhase("setup");
                setSessionDone(false);
                setError(null);
              }}
            >
              Choose again
            </button>
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
            <p className="text-sm font-bold text-warm-muted">SRS Review 🧠</p>
            <h1 className="text-2xl font-extrabold text-warm-brown">
              {isHomeworkList
                ? `Homework word ${index + 1} of ${cards.length}`
                : `Card ${index + 1} of ${cards.length}`}
            </h1>
            {listName && (
              <p className="mt-1 text-sm font-semibold text-warm-brown-soft">
                {isHomeworkList ? `Homework practice · “${listName}”` : `From “${listName}”`}
              </p>
            )}
          </div>
          <LearnerTopNav />
        </header>

        {stats && (
          <div className="warm-card bg-white/60 p-3 text-center text-sm font-semibold text-warm-body">
            Today: {stats.reviewed_today} reviewed · {stats.due_count} due · goal{" "}
            {stats.daily_goal}
          </div>
        )}

        {currentCard && (
          <>
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                onClick={handlePrevious}
                disabled={index === 0}
                className="warm-btn warm-btn-secondary text-sm disabled:opacity-40"
              >
                ← Previous
              </button>
              <span className="text-sm font-semibold text-warm-brown-soft">
                {index + 1} / {cards.length}
              </span>
              <button
                type="button"
                onClick={handleNext}
                disabled={index >= cards.length - 1}
                className="warm-btn warm-btn-secondary text-sm disabled:opacity-40"
              >
                Next →
              </button>
            </div>

            {loadingDefinitions && !revealed && (
              <p className="text-center text-sm font-semibold text-warm-muted">Loading meanings…</p>
            )}
            {definitionUnavailable && !revealed && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50/90 px-4 py-3 text-center text-sm text-warm-brown">
                <p className="font-semibold">
                  No dictionary meaning for &ldquo;{currentCard.dictionary_entry.word}&rdquo;
                </p>
                <button
                  type="button"
                  className="warm-btn warm-btn-secondary mt-3 text-sm"
                  disabled={submitting}
                  onClick={() => void handleRate(1)}
                >
                  Skip this word
                </button>
              </div>
            )}

            <FlashcardDeck
              card={currentCard}
              revealed={revealed}
              definitionChoices={
                loadingDefinitions || definitionUnavailable ? [] : definitionChoices
              }
              pickFeedback={pickFeedback}
              onPickDefinition={handlePickDefinition}
              onZhCleared={handleZhCleared}
              onWrongContinue={
                pickFeedback && !pickFeedback.isCorrect && !submitting
                  ? handleReviewContinue
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
