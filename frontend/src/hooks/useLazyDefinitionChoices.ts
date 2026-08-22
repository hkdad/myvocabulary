import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { ensureDefinitions, ensureZhHant } from "../api/dictionary";
import type { SrsCard } from "../api/reviews";
import {
  applyZhToChoices,
  generateDefinitionChoices,
  type DefinitionChoice,
} from "../lib/definitionChoices";
import { isPlaceholderDefinition } from "../lib/placeholderDefinition";

function applyZhUpdates(
  setCards: Dispatch<SetStateAction<SrsCard[]>>,
  setZhByEntryId: Dispatch<SetStateAction<Record<number, string>>>,
  items: { id: number; definition_zh_hant: string }[],
) {
  if (items.length === 0) {
    return;
  }
  const updates: Record<number, string> = {};
  for (const item of items) {
    updates[item.id] = item.definition_zh_hant;
  }
  setZhByEntryId((prev) => ({ ...prev, ...updates }));
  setCards((prev) =>
    prev.map((card) => {
      const zh = updates[card.dictionary_entry.id];
      if (!zh) {
        return card;
      }
      return {
        ...card,
        dictionary_entry: {
          ...card.dictionary_entry,
          definition_zh_hant: zh,
        },
      };
    }),
  );
}

function entryNeedsDefinition(card: SrsCard): boolean {
  return isPlaceholderDefinition(card.dictionary_entry.definition);
}

/**
 * Lazy Traditional Chinese for review/challenge MCQ.
 * English choices render immediately; zh fills in for every option that has an entry_id.
 * Prefetches the next card so Chinese is often ready before the kid advances.
 *
 * Placeholder glosses (book/bank imports) are fetched before MCQ options are built.
 *
 * Choice order is locked per card view; reshuffles when the card, index, or shuffleKey changes.
 * Chinese updates must never reshuffle.
 */
export function useLazyDefinitionChoices(
  cards: SrsCard[],
  currentIndex: number,
  setCards: Dispatch<SetStateAction<SrsCard[]>>,
  shuffleKey = 0,
): {
  choices: DefinitionChoice[];
  clearZhForEntry: (entryId: number) => void;
  loadingDefinitions: boolean;
  definitionUnavailable: boolean;
} {
  const currentCard = cards[currentIndex];
  const cardsRef = useRef(cards);
  cardsRef.current = cards;

  const inFlightRef = useRef<Set<number>>(new Set());
  const [zhByEntryId, setZhByEntryId] = useState<Record<number, string>>({});
  const [lockedChoices, setLockedChoices] = useState<DefinitionChoice[]>([]);
  const [definitionsReady, setDefinitionsReady] = useState(true);

  // Fetch real English glosses (and zh when configured) before building MCQ options.
  useEffect(() => {
    const sessionCards = cardsRef.current;
    const card = sessionCards[currentIndex];
    if (!card) {
      setDefinitionsReady(true);
      return;
    }

    const sessionIds = sessionCards.map((item) => item.dictionary_entry.id);
    const pendingIds = sessionCards
      .filter(entryNeedsDefinition)
      .map((item) => item.dictionary_entry.id);

    let cancelled = false;

    async function loadDefinitionsAndZh() {
      setDefinitionsReady(false);
      if (pendingIds.length > 0) {
        const items = await ensureDefinitions(pendingIds);
        if (cancelled) {
          return;
        }
        if (items.length > 0) {
          const byId = new Map(items.map((item) => [item.id, item]));
          setCards((prev) =>
            prev.map((row) => {
              const update = byId.get(row.dictionary_entry.id);
              if (!update) {
                return row;
              }
              return {
                ...row,
                dictionary_entry: {
                  ...row.dictionary_entry,
                  definition: update.definition,
                  part_of_speech: update.part_of_speech ?? row.dictionary_entry.part_of_speech,
                  definition_zh_hant:
                    update.definition_zh_hant ?? row.dictionary_entry.definition_zh_hant,
                },
              };
            }),
          );
        }
      }

      const zhItems = await ensureZhHant(sessionIds);
      if (!cancelled) {
        applyZhUpdates(setCards, setZhByEntryId, zhItems);
        setDefinitionsReady(true);
      }
    }

    setDefinitionsReady(false);
    void loadDefinitionsAndZh().catch(() => {
      if (!cancelled) {
        setDefinitionsReady(true);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [currentCard?.id, currentIndex, setCards, shuffleKey]);

  // Shuffle only when the kid lands on a different card — never when zh fills cards.
  useEffect(() => {
    const card = cardsRef.current[currentIndex];
    if (!card || !definitionsReady || entryNeedsDefinition(card)) {
      setLockedChoices([]);
      return;
    }

    const pool = cardsRef.current
      .filter((item) => item.id !== card.id)
      .map((item) => ({
        definition: item.dictionary_entry.definition,
        definition_zh_hant: item.dictionary_entry.definition_zh_hant ?? null,
        entry_id: item.dictionary_entry.id,
      }))
      .filter(
        (item) => Boolean(item.definition) && !isPlaceholderDefinition(item.definition),
      );

    setLockedChoices(
      generateDefinitionChoices(
        {
          definition: card.dictionary_entry.definition,
          definition_zh_hant: card.dictionary_entry.definition_zh_hant ?? null,
          entry_id: card.dictionary_entry.id,
        },
        pool,
        4,
        // No seed → true Math.random every time this card is shown.
      ),
    );
  }, [currentCard?.id, currentIndex, definitionsReady, shuffleKey]);

  const choices = useMemo(() => {
    // Merge zh already on session cards + lazy-fill results (order stays locked).
    const fromCards: Record<number, string> = {};
    for (const card of cards) {
      const zh = card.dictionary_entry.definition_zh_hant?.trim();
      if (zh) {
        fromCards[card.dictionary_entry.id] = zh;
      }
    }
    return applyZhToChoices(lockedChoices, { ...fromCards, ...zhByEntryId });
  }, [lockedChoices, zhByEntryId, cards]);

  useEffect(() => {
    if (!currentCard || lockedChoices.length === 0) {
      return;
    }

    const needed = new Set<number>();

    for (const choice of lockedChoices) {
      if (choice.entry_id == null) {
        continue;
      }
      const fromCard = cards.find(
        (row) => row.dictionary_entry.id === choice.entry_id,
      )?.dictionary_entry.definition_zh_hant?.trim();
      const fromState = zhByEntryId[choice.entry_id];
      const fromChoice = choice.definition_zh_hant?.trim();
      if (fromCard || fromState || fromChoice) {
        continue;
      }
      if (!inFlightRef.current.has(choice.entry_id)) {
        needed.add(choice.entry_id);
      }
    }

    if (needed.size === 0) {
      return;
    }

    const ids = [...needed];
    for (const id of ids) {
      inFlightRef.current.add(id);
    }

    void ensureZhHant(ids)
      .then((items) => {
        for (const id of ids) {
          inFlightRef.current.delete(id);
        }
        applyZhUpdates(setCards, setZhByEntryId, items);
      })
      .catch(() => {
        for (const id of ids) {
          inFlightRef.current.delete(id);
        }
      });
  }, [lockedChoices, cards, currentCard, setCards, zhByEntryId]);

  const clearZhForEntry = useCallback((entryId: number) => {
    setZhByEntryId((prev) => {
      if (!(entryId in prev)) {
        return prev;
      }
      const next = { ...prev };
      delete next[entryId];
      return next;
    });
    inFlightRef.current.delete(entryId);
  }, []);

  const loadingDefinitions = !definitionsReady;
  const definitionUnavailable =
    definitionsReady && currentCard != null && entryNeedsDefinition(currentCard);

  return { choices, clearZhForEntry, loadingDefinitions, definitionUnavailable };
}
