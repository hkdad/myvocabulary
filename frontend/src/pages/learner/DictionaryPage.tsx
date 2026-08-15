import { type FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  lookupWord,
  searchDictionary,
  suggestDictionary,
  type DictionaryEntry,
} from "../../api/dictionary";
import { getLoopToday, type DailyMix } from "../../api/loop";
import PageShell from "../../components/PageShell";
import LearnerPageHeader from "../../components/LearnerPageHeader";
import WordCard from "../../components/WordCard";
import { useAuthStore } from "../../stores/authStore";

const SUGGEST_DEBOUNCE_MS = 200;

export default function DictionaryPage() {
  const { word: wordParam } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const isLanding = !wordParam;

  const [query, setQuery] = useState(wordParam ?? "");
  const [results, setResults] = useState<DictionaryEntry[]>([]);
  const [suggestions, setSuggestions] = useState<DictionaryEntry[]>([]);
  const [didYouMean, setDidYouMean] = useState<DictionaryEntry[]>([]);
  const [selected, setSelected] = useState<DictionaryEntry | null>(null);
  const [dailyMix, setDailyMix] = useState<DailyMix | null>(null);
  const [mixLoading, setMixLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suppressSuggest = useRef(false);

  useEffect(() => {
    if (!isLanding) {
      return;
    }
    setMixLoading(true);
    getLoopToday()
      .then(setDailyMix)
      .catch(() => setDailyMix(null))
      .finally(() => setMixLoading(false));
  }, [isLanding, user?.id]);

  useEffect(() => {
    if (!wordParam) {
      setSelected(null);
      setResults([]);
      setDidYouMean([]);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    setDidYouMean([]);
    setResults([]);
    setSuggestions([]);
    setShowSuggestions(false);

    async function loadWord(word: string) {
      try {
        const [entry, search] = await Promise.all([
          lookupWord(word),
          searchDictionary(word),
        ]);
        if (cancelled) {
          return;
        }
        setSelected(entry);
        suppressSuggest.current = true;
        setQuery(entry.word);
        // Keep related hits, but don't repeat the open word itself.
        setResults(search.results.filter((item) => item.word !== entry.word));
      } catch (err) {
        if (cancelled) {
          return;
        }
        setSelected(null);
        setError(err instanceof Error ? err.message : "Search failed");
        try {
          const suggest = await suggestDictionary(word, 3);
          if (!cancelled) {
            setDidYouMean(suggest.suggestions);
          }
        } catch {
          if (!cancelled) {
            setDidYouMean([]);
          }
        }
        try {
          const search = await searchDictionary(word);
          if (!cancelled) {
            setResults(search.results);
          }
        } catch {
          if (!cancelled) {
            setResults([]);
          }
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadWord(wordParam);

    return () => {
      cancelled = true;
    };
  }, [wordParam]);

  useEffect(() => {
    if (suggestTimer.current) {
      clearTimeout(suggestTimer.current);
    }
    const trimmed = query.trim();
    if (suppressSuggest.current) {
      suppressSuggest.current = false;
      return;
    }
    if (trimmed.length < 2 || selected?.word === trimmed.toLowerCase()) {
      setSuggestions([]);
      return;
    }
    suggestTimer.current = setTimeout(() => {
      suggestDictionary(trimmed, 5)
        .then((response) => {
          setSuggestions(response.suggestions);
          setShowSuggestions(true);
        })
        .catch(() => {
          setSuggestions([]);
        });
    }, SUGGEST_DEBOUNCE_MS);
    return () => {
      if (suggestTimer.current) {
        clearTimeout(suggestTimer.current);
      }
    };
  }, [query, selected?.word]);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }
    setSuggestions([]);
    setShowSuggestions(false);
    // Route change loads the word + related results via the wordParam effect.
    navigate(`/app/dictionary/${encodeURIComponent(trimmed)}`);
  }

  function pickSuggestion(word: string) {
    suppressSuggest.current = true;
    setSelected(null);
    setResults([]);
    setDidYouMean([]);
    setError(null);
    setQuery(word);
    setSuggestions([]);
    setShowSuggestions(false);
    navigate(`/app/dictionary/${encodeURIComponent(word)}`);
  }

  const challengeCards = dailyMix?.cards ?? [];
  const typeaheadOpen = showSuggestions && suggestions.length > 0;

  return (
    <PageShell variant="teen">
      <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 p-6 sm:p-8">
        <LearnerPageHeader
          eyebrow="📖 Dictionary"
          title="Look up a word"
          subtitle={`Hi ${user?.learner?.display_name ?? user?.username}! ✨`}
        />

        <form onSubmit={handleSearch} className="warm-card relative z-30 flex flex-wrap gap-2 p-4">
          <div className="relative min-w-[12rem] flex-1">
            <input
              className="warm-input w-full"
              placeholder="Try elephant, aurora, or happy…"
              value={query}
              onChange={(event) => {
                const next = event.target.value;
                setShowSuggestions(true);
                setQuery(next);
                // Drop the open entry while composing a new search so the
                // typeahead is not covered by (or covering) a stale WordCard.
                if (selected && next.trim().toLowerCase() !== selected.word) {
                  setSelected(null);
                  setResults([]);
                  setDidYouMean([]);
                  setError(null);
                  if (wordParam) {
                    navigate("/app/dictionary", { replace: true });
                  }
                }
              }}
              onFocus={() => {
                if (suggestions.length > 0) {
                  setShowSuggestions(true);
                }
              }}
              onBlur={() => {
                window.setTimeout(() => setShowSuggestions(false), 150);
              }}
              autoFocus
              autoComplete="off"
            />
            {typeaheadOpen && (
              <ul className="absolute left-0 right-0 top-full z-40 mt-1 max-h-64 overflow-auto rounded-xl border border-orange-100 bg-white shadow-lg">
                {suggestions.map((entry) => (
                  <li key={entry.id}>
                    <button
                      type="button"
                      className="block w-full px-4 py-3 text-left transition hover:bg-amber-50"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        pickSuggestion(entry.word);
                      }}
                    >
                      <p className="font-bold text-warm-brown">{entry.word}</p>
                      <p className="text-sm text-warm-brown-soft line-clamp-1">{entry.definition}</p>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <button type="submit" disabled={loading} className="warm-btn warm-btn-primary text-sm">
            {loading ? "Searching…" : "Search 🔍"}
          </button>
        </form>

        {error && <p className="font-semibold text-red-600">{error}</p>}

        {didYouMean.length > 0 && !selected && !typeaheadOpen && (
          <section className="warm-card p-4">
            <h2 className="text-sm font-extrabold uppercase tracking-wide text-warm-muted">
              Did you mean?
            </h2>
            <ul className="mt-3 flex flex-wrap gap-2">
              {didYouMean.map((entry) => (
                <li key={entry.id}>
                  <Link
                    to={`/app/dictionary/${encodeURIComponent(entry.word)}`}
                    className="inline-block rounded-xl bg-amber-50 px-3 py-2 text-sm font-bold text-warm-brown underline"
                  >
                    {entry.word}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {selected && !typeaheadOpen && (
          <WordCard entry={selected} onEntryUpdate={setSelected} />
        )}

        {results.length > 0 && !typeaheadOpen && (
          <section className="warm-card p-4">
            <h2 className="text-sm font-extrabold uppercase tracking-wide text-warm-muted">
              Related results
            </h2>
            <ul className="mt-3 divide-y divide-orange-100">
              {results.map((entry) => (
                <li key={entry.id}>
                  <Link
                    to={`/app/dictionary/${encodeURIComponent(entry.word)}`}
                    className="block rounded-xl py-3 transition hover:bg-amber-50/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-coral"
                  >
                    <p className="font-bold text-warm-brown">{entry.word}</p>
                    <p className="text-sm text-warm-brown-soft line-clamp-2">{entry.definition}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {isLanding && !typeaheadOpen && (
          <section className="warm-card p-4">
            <h2 className="text-sm font-extrabold uppercase tracking-wide text-warm-muted">
              Today&apos;s challenge
            </h2>
            {mixLoading && (
              <p className="mt-3 text-sm text-warm-brown-soft">Loading today&apos;s words…</p>
            )}
            {!mixLoading && challengeCards.length === 0 && (
              <p className="mt-3 text-sm text-warm-brown-soft">
                No challenge words yet — ask a parent to upload the word bank.
              </p>
            )}
            {!mixLoading && challengeCards.length > 0 && (
              <ul className="mt-3 divide-y divide-orange-100">
                {challengeCards.map((card) => (
                  <li key={card.id}>
                    <Link
                      to={`/app/dictionary/${encodeURIComponent(card.dictionary_entry.word)}`}
                      className="block rounded-xl py-3 transition hover:bg-amber-50/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-coral"
                    >
                      <p className="font-bold text-warm-brown">{card.dictionary_entry.word}</p>
                      <p className="text-sm text-warm-brown-soft line-clamp-2">
                        {card.dictionary_entry.definition}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </main>
    </PageShell>
  );
}
