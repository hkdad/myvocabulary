import { useState } from "react";

import type { DictionaryEntry } from "../api/dictionary";
import AudioPlayer from "./AudioPlayer";
import ClearTranslationButton from "./ClearTranslationButton";

type WordCardProps = {
  entry: DictionaryEntry;
  compact?: boolean;
  onEntryUpdate?: (entry: DictionaryEntry) => void;
};

export default function WordCard({ entry, compact = false, onEntryUpdate }: WordCardProps) {
  const [clearNotice, setClearNotice] = useState<string | null>(null);

  return (
    <article className={`warm-card ${compact ? "p-4" : "p-6"}`}>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className={`font-extrabold text-warm-brown ${compact ? "text-xl" : "text-3xl"}`}>
            {entry.word}
          </h2>
          {entry.phonetic && <p className="mt-1 text-warm-brown-soft">{entry.phonetic}</p>}
          {entry.part_of_speech && (
            <p className="mt-1 text-sm font-bold uppercase tracking-wide text-warm-coral">
              {entry.part_of_speech}
            </p>
          )}
        </div>
        {!compact && <AudioPlayer word={entry.word} />}
      </header>

      <p className={`text-warm-body ${compact ? "mt-2 text-sm" : "mt-4 text-lg"}`}>
        {entry.definition}
      </p>

      {entry.definition_zh_hant && (
        <div
          className={`rounded-xl border border-warm-border/60 bg-warm-card/40 ${
            compact ? "mt-2 px-3 py-2" : "mt-4 px-4 py-3"
          }`}
        >
          <p className={compact ? "text-sm text-warm-brown-soft" : "text-base text-warm-brown-soft"}>
            <span className="mr-2 text-xs font-bold uppercase tracking-wide text-warm-muted">
              中文
            </span>
            {entry.definition_zh_hant}
          </p>
          {onEntryUpdate && (
            <div className="mt-3 border-t border-warm-border/40 pt-3">
              <ClearTranslationButton
                entryId={entry.id}
                onCleared={() => {
                  onEntryUpdate({ ...entry, definition_zh_hant: null });
                  setClearNotice("Cleared. We'll translate again next time.");
                }}
              />
            </div>
          )}
        </div>
      )}

      {clearNotice && (
        <p className={`text-warm-muted ${compact ? "mt-2 text-xs" : "mt-3 text-sm"}`} role="status">
          {clearNotice}
        </p>
      )}

      {entry.example_sentence && (
        <p className="mt-3 text-sm italic text-warm-brown-soft">“{entry.example_sentence}”</p>
      )}

      {entry.synonyms.length > 0 && (
        <p className="mt-3 text-sm text-warm-muted">Synonyms: {entry.synonyms.join(", ")}</p>
      )}
    </article>
  );
}
