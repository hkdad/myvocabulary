import { useState } from "react";
import { Link } from "react-router-dom";

import {
  THEME_PACK_LEVEL_OPTIONS,
  themePackWordsUrl,
  type QuestsSummary,
  type ThemePackLevelFilter,
  type ThemePackQuest,
} from "../../api/loop";
import QuestLevelAccordion from "./QuestLevelAccordion";
import QuestOverallCard from "./QuestOverallCard";

type Props = {
  quests: QuestsSummary;
  packLinks?: boolean;
  emptyPackMessage?: string;
};

function ThemePackCard({
  pack,
  packLevel,
  packLinks,
}: {
  pack: ThemePackQuest;
  packLevel: ThemePackLevelFilter;
  packLinks: boolean;
}) {
  const content = (
    <>
      <p className="text-2xl">{pack.emoji}</p>
      <p className="mt-1 font-extrabold text-warm-brown">{pack.title}</p>
      <p className="text-sm text-warm-brown-soft">
        {pack.strong_words} / {pack.total_words} strong words
      </p>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
        <div
          className="h-full rounded-full bg-gradient-to-r from-green-400 to-teal-300"
          style={{ width: `${pack.progress_percent}%` }}
        />
      </div>
      {pack.completed && (
        <p className="mt-2 text-sm font-semibold text-green-700">Pack complete ✓</p>
      )}
    </>
  );

  if (packLinks) {
    return (
      <Link
        to={themePackWordsUrl(pack, packLevel)}
        className="warm-card block p-4 transition hover:bg-warm-cream/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-warm-accent"
        aria-label={`View ${pack.title} words in My words`}
      >
        {content}
      </Link>
    );
  }

  return <article className="warm-card p-4">{content}</article>;
}

export default function QuestsSummaryView({
  quests,
  packLinks = true,
  emptyPackMessage,
}: Props) {
  const [packLevel, setPackLevel] = useState<ThemePackLevelFilter>("Overall");

  const packsForLevel =
    quests.packs_by_level[packLevel] ?? (packLevel === "Overall" ? quests.packs : undefined);
  const activePacks = packsForLevel?.filter((pack) => pack.total_words > 0) ?? [];

  return (
    <>
      {quests.newly_earned_badges.length > 0 && (
        <section className="warm-card bg-gradient-to-br from-amber-50 to-yellow-50 p-4">
          <p className="font-extrabold text-warm-brown">New badge earned! 🎉</p>
          <p className="text-sm text-warm-body">
            {quests.newly_earned_badges.map((b) => b.replace(/_/g, " ")).join(", ")}
          </p>
        </section>
      )}

      <QuestOverallCard overall={quests.overall} />

      {quests.levels.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-extrabold text-warm-brown">By level</h2>
          {quests.levels.map((levelQuest) => (
            <QuestLevelAccordion
              key={levelQuest.level}
              levelQuest={levelQuest}
              defaultOpen={levelQuest.is_current}
            />
          ))}
        </section>
      )}

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-lg font-extrabold text-warm-brown">Theme packs</h2>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Strong = familiar or mastered in that category
              {packLevel !== "Overall" ? ` · Level ${packLevel}` : ""}
            </p>
          </div>
          <select
            className="warm-input max-w-[10rem]"
            aria-label="Filter theme packs by level"
            value={packLevel}
            onChange={(event) => setPackLevel(event.target.value as ThemePackLevelFilter)}
          >
            {THEME_PACK_LEVEL_OPTIONS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>
        {activePacks.length === 0 ? (
          <p className="text-warm-brown-soft">
            {emptyPackMessage ??
              (packLevel === "Overall"
                ? "No theme packs yet — ask parent to upload words with categories."
                : `No ${packLevel} words in theme packs yet.`)}
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {activePacks.map((pack) => (
              <ThemePackCard
                key={pack.slug}
                pack={pack}
                packLevel={packLevel}
                packLinks={packLinks}
              />
            ))}
          </div>
        )}
      </section>
    </>
  );
}
