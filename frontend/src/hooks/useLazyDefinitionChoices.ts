import { useCallback, useEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { ensureZhHant } from "../api/dictionary";
import type { SrsCard } from "../api/reviews";
import {
  applyZhToChoices,
  generateDefinitionChoices,
  type DefinitionChoice,
} from "../lib/definitionChoices";

/**
 * Lazy Traditional Chinese for review/challenge MCQ.
 * English choices render immediately; zh fills in for every option that has an entry_id.
 * Prefetches the next card so Chinese is often ready before the kid advances.
 *
 * Choice order is locked per card view; reshuffles when the card, index, or shuffleKey changes.
 * Chinese updates must never reshuffle.
 */
export function useLazyDefinitionChoices(
  cards: SrsCard[],
  currentIndex: number,
  setCards: Dispatch<SetStateAction<SrsCard[]>>,
  shuffleKey = 0,
): { choices: DefinitionChoice[]; clearZhForEntry: (entryId: number) => void } {
  const currentCard = cards[currentIndex];
  const cardsRef = useRef(cards);
  cardsRef.current = cards;

  const inFlightRef = useRef<Set<number>>(new Set());
  const [zhByEntryId, setZhByEntryId] = useState<Record<number, string>>({});
  const [lockedChoices, setLockedChoices] = useState<DefinitionChoice[]>([]);

  // Shuffle only when the kid lands on a different card — never when zh fills cards.
  useEffect(() => {
    const card = cardsRef.current[currentIndex];
    if (!card) {
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
      .filter((item) => Boolean(item.definition));

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
  }, [currentCard?.id, currentIndex, shuffleKey]);

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
        (card) => card.dictionary_entry.id === choice.entry_id,
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

    const nextCard = cards[currentIndex + 1];
    if (nextCard) {
      const entry = nextCard.dictionary_entry;
      const hasZh =
        Boolean(entry.definition_zh_hant?.trim()) || Boolean(zhByEntryId[entry.id]);
      if (!hasZh && !inFlightRef.current.has(entry.id)) {
        needed.add(entry.id);
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
      })
      .catch(() => {
        for (const id of ids) {
          inFlightRef.current.delete(id);
        }
      });
  }, [lockedChoices, cards, currentCard, currentIndex, setCards, zhByEntryId]);

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

  return { choices, clearZhForEntry };
}
