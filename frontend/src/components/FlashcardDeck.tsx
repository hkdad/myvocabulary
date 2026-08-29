import { useState } from "react";

import type { SrsCard } from "../api/reviews";
import type { DefinitionChoice } from "../lib/definitionChoices";
import { definitionsMatch } from "../lib/definitionChoices";
import { strengthLabel, strengthTagClass } from "../lib/strengthStyles";
import AudioPlayer from "./AudioPlayer";
import ClearTranslationButton from "./ClearTranslationButton";

export type DefinitionPickFeedback = {
  selected: string;
  isCorrect: boolean;
};

type FlashcardDeckProps = {
  card: SrsCard;
  revealed: boolean;
  definitionChoices: DefinitionChoice[];
  pickFeedback: DefinitionPickFeedback | null;
  onPickDefinition: (definition: string) => void;
  variant?: "kid" | "teen";
  autoPlayAudio?: boolean;
  showAudio?: boolean;
  onZhCleared?: (entryId: number) => void;
  onWrongContinue?: () => void;
};

export default function FlashcardDeck({
  card,
  revealed,
  definitionChoices,
  pickFeedback,
  onPickDefinition,
  variant = "teen",
  autoPlayAudio = false,
  showAudio = true,
  onZhCleared,
  onWrongContinue,
}: FlashcardDeckProps) {
  const entry = card.dictionary_entry;
  const inputLocked = Boolean(pickFeedback);
  const [clearNotice, setClearNotice] = useState<string | null>(null);

  function handleZhCleared(entryId: number) {
    onZhCleared?.(entryId);
    setClearNotice("Cleared. We'll translate again next time.");
  }

  return (
    <article
      className={`warm-card flex min-h-[280px] flex-col justify-between p-6 sm:min-h-[320px] ${
        variant === "kid"
          ? "bg-gradient-to-br from-sky-50/90 to-amber-50/90"
          : "bg-gradient-to-br from-purple-50/90 to-pink-50/90"
      }`}
    >
      <div className="mb-3 flex flex-wrap gap-2">
        {card.level && (
          <span className="rounded-full bg-slate-200/90 px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide text-warm-brown">
            {card.level}
          </span>
        )}
        {card.books.map((book) => (
          <span
            key={book}
            className="rounded-full bg-orange-100 px-2.5 py-0.5 text-xs font-bold text-warm-brown"
          >
            {book}
          </span>
        ))}
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${strengthTagClass(card.strength)}`}
        >
          {strengthLabel(card.strength)}
        </span>
      </div>
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm font-bold uppercase tracking-wide text-warm-coral">
              {revealed ? "Meaning" : "Word"}
            </p>
            <h2 className="mt-2 text-4xl font-extrabold text-warm-brown">{entry.word}</h2>
            {entry.phonetic && (
              <p className="mt-1 text-lg font-medium text-warm-brown-soft">
                <span className="mr-1 text-sm font-bold text-warm-muted">音标</span>
                {entry.phonetic}
              </p>
            )}
            {entry.part_of_speech && (
              <p className="mt-1 text-sm font-semibold text-warm-muted">{entry.part_of_speech}</p>
            )}
          </div>
          {showAudio && <AudioPlayer word={entry.word} autoPlay={autoPlayAudio} />}
        </div>
      </div>

      {revealed ? (
        <div className="mt-6 space-y-4">
          <p className="text-lg text-warm-body">{entry.definition}</p>
          {entry.definition_zh_hant && (
            <div className="rounded-xl border border-warm-border/60 bg-white/50 px-4 py-3">
              <p className="text-base text-warm-brown-soft">
                <span className="mr-2 text-xs font-bold uppercase tracking-wide text-warm-muted">
                  中文
                </span>
                {entry.definition_zh_hant}
              </p>
              {onZhCleared && (
                <div className="mt-3 border-t border-warm-border/40 pt-3">
                  <ClearTranslationButton
                    entryId={entry.id}
                    onCleared={() => handleZhCleared(entry.id)}
                  />
                </div>
              )}
            </div>
          )}
          {clearNotice && (
            <p className="text-sm text-warm-muted" role="status">
              {clearNotice}
            </p>
          )}
          {pickFeedback && (
            <p
              className={`rounded-xl p-3 text-center text-sm font-semibold ${
                pickFeedback.isCorrect ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800"
              }`}
            >
              {pickFeedback.isCorrect
                ? "Great pick! 🌟"
                : "Not quite — check the meaning above."}
            </p>
          )}
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          <p className="text-center text-sm font-semibold text-warm-body">
            Pick the meaning of this word
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {definitionChoices.map((choice) => {
              const isSelected = pickFeedback?.selected === choice.definition;
              const isCorrectChoice = definitionsMatch(choice.definition, entry.definition);
              let choiceClass = "warm-btn warm-btn-secondary py-4 text-left text-sm font-semibold";
              if (pickFeedback && isSelected) {
                choiceClass = pickFeedback.isCorrect
                  ? "warm-btn warm-btn-primary py-4 text-left text-sm font-semibold"
                  : "rounded-xl border-2 border-red-300 bg-red-50 py-4 px-4 text-left text-sm font-semibold text-red-800";
              } else if (pickFeedback && !pickFeedback.isCorrect && isCorrectChoice) {
                choiceClass =
                  "rounded-xl border-2 border-green-300 bg-green-50 py-4 px-4 text-left text-sm font-semibold text-green-800";
              }

              return (
                <button
                  key={choice.entry_id != null ? `entry-${choice.entry_id}` : choice.definition}
                  type="button"
                  disabled={inputLocked}
                  onClick={() => onPickDefinition(choice.definition)}
                  className={`${choiceClass} disabled:opacity-50`}
                >
                  <span className="block">{choice.definition}</span>
                  {choice.definition_zh_hant && (
                    <span className="mt-1 block text-xs font-semibold text-warm-brown-soft">
                      {choice.definition_zh_hant}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {onWrongContinue && (
        <button
          type="button"
          className="warm-btn warm-btn-primary mt-4 w-full"
          onClick={onWrongContinue}
        >
          Continue
        </button>
      )}
    </article>
  );
}
