import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  addWordToList,
  getWordList,
  removeWordFromList,
  type WordListDetail,
} from "../../api/wordLists";
import { initializeReviews } from "../../api/reviews";
import PageShell from "../../components/PageShell";
import LearnerTopNav from "../../components/LearnerTopNav";
import WordCard from "../../components/WordCard";

export default function LearnerListDetailPage() {
  const { id } = useParams();
  const listId = Number(id);
  const navigate = useNavigate();
  const [list, setList] = useState<WordListDetail | null>(null);
  const [word, setWord] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [initializing, setInitializing] = useState(false);
  const [addingWord, setAddingWord] = useState(false);
  const [initMessage, setInitMessage] = useState<string | null>(null);

  const isMyList = list?.source === "learner";

  const load = useCallback(async () => {
    if (!listId) {
      return;
    }
    setError(null);
    try {
      const detail = await getWordList(listId);
      setList(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load list");
    }
  }, [listId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleStartLearning() {
    if (!listId) {
      return;
    }
    setInitializing(true);
    setInitMessage(null);
    try {
      const result = await initializeReviews(listId);
      if (result.created_count > 0) {
        setInitMessage(`Added ${result.created_count} new flashcards!`);
      } else {
        setInitMessage("Your flashcards are ready — let's review!");
      }
      navigate(`/app/review?list_id=${listId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start learning");
    } finally {
      setInitializing(false);
    }
  }

  async function handleAddWord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!list || !word.trim()) {
      return;
    }
    setAddingWord(true);
    setError(null);
    try {
      await addWordToList(list.id, { word: word.trim() });
      setWord("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add word");
    } finally {
      setAddingWord(false);
    }
  }

  async function handleRemoveWord(itemId: number) {
    if (!list) {
      return;
    }
    setError(null);
    try {
      await removeWordFromList(list.id, itemId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove word");
    }
  }

  if (!list) {
    return (
      <PageShell variant="teen">
        <main className="mx-auto max-w-3xl p-8">
          <p className="text-warm-brown-soft">{error ?? "Loading…"}</p>
        </main>
      </PageShell>
    );
  }

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">
              {isMyList ? "My school list" : "Word list"}
            </p>
            <h1 className="text-3xl font-extrabold text-warm-brown">{list.name}</h1>
            <p className="mt-1 font-semibold text-warm-brown-soft">
              {list.item_count} words{list.level_tag ? ` · ${list.level_tag}` : ""}
            </p>
          </div>
          <LearnerTopNav />
        </header>

        {error && <p className="font-semibold text-red-600">{error}</p>}

        {isMyList && (
          <section className="warm-card p-6">
            <h2 className="text-lg font-extrabold text-warm-brown">Add a word</h2>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Type each spelling word from your school list.
            </p>
            <form onSubmit={handleAddWord} className="mt-4 flex flex-wrap gap-2">
              <input
                className="warm-input flex-1"
                placeholder="Type a word"
                value={word}
                onChange={(event) => setWord(event.target.value)}
              />
              <button
                type="submit"
                disabled={addingWord || !word.trim()}
                className="warm-btn warm-btn-primary text-sm disabled:opacity-50"
              >
                {addingWord ? "Adding…" : "Add ✨"}
              </button>
            </form>
          </section>
        )}

        <section className="warm-card flex flex-col gap-4 bg-amber-50/80 p-4 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <div className="text-sm font-semibold text-warm-body">
            {initMessage ??
              (isMyList
                ? "Review practices every word on this list — not just what's due today."
                : "Tap Review this list to turn these words into flashcards, then practice.")}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void handleStartLearning()}
              disabled={initializing || list.item_count === 0}
              className="warm-btn warm-btn-primary shrink-0"
            >
              {initializing ? "Starting…" : "Review this list"}
            </button>
            <Link
              to={`/app/dictation/pick?list_id=${listId}`}
              className="warm-btn warm-btn-primary shrink-0"
            >
              Listen & Pick
            </Link>
            <Link
              to={`/app/dictation?list_id=${listId}`}
              className="warm-btn warm-btn-secondary shrink-0"
            >
              Spell (bonus)
            </Link>
          </div>
        </section>

        <div className="flex flex-col gap-4">
          {list.items.length === 0 ? (
            <p className="text-center text-warm-brown-soft">
              {isMyList
                ? "No words yet — add your first school word above!"
                : "This list has no words yet."}
            </p>
          ) : (
            list.items.map((item) => (
              <div key={item.id} className="relative">
                <WordCard
                  compact
                  entry={{
                    id: item.dictionary_entry.id,
                    word: item.dictionary_entry.word,
                    phonetic: item.dictionary_entry.phonetic,
                    part_of_speech: item.dictionary_entry.part_of_speech,
                    definition: item.dictionary_entry.definition,
                    definition_zh_hant: item.dictionary_entry.definition_zh_hant ?? null,
                    example_sentence: null,
                    synonyms: [],
                    source: list.source,
                    has_audio: item.dictionary_entry.has_audio,
                  }}
                  onEntryUpdate={(updated) => {
                    setList((prev) => {
                      if (!prev) {
                        return prev;
                      }
                      return {
                        ...prev,
                        items: prev.items.map((listItem) =>
                          listItem.dictionary_entry.id === updated.id
                            ? {
                                ...listItem,
                                dictionary_entry: {
                                  ...listItem.dictionary_entry,
                                  definition_zh_hant: null,
                                },
                              }
                            : listItem,
                        ),
                      };
                    });
                  }}
                />
                {isMyList && (
                  <button
                    type="button"
                    onClick={() => void handleRemoveWord(item.id)}
                    className="absolute right-4 top-4 text-sm font-semibold text-red-600"
                  >
                    Remove
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </main>
    </PageShell>
  );
}
