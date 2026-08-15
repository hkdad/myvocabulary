import { useState } from "react";

import type { LevelQuest } from "../../api/loop";
import { inProgressCount } from "../../lib/strengthStyles";
import QuestMilestoneRow from "./QuestMilestoneRow";
import StrengthProgressBar from "./StrengthProgressBar";

type Props = {
  levelQuest: LevelQuest;
  defaultOpen?: boolean;
};

export default function QuestLevelAccordion({ levelQuest, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const inProgress = inProgressCount(levelQuest);
  const readinessPct = Math.round(levelQuest.readiness_score * 100);
  const readinessTone =
    readinessPct >= 75
      ? "text-emerald-700"
      : readinessPct >= 60
        ? "text-amber-700"
        : "text-warm-brown-soft";

  return (
    <article className="warm-card overflow-hidden">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-4 text-left"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <div>
          <p className="font-extrabold text-warm-brown">
            Level {levelQuest.level}
            {levelQuest.is_current ? (
              <span className="ml-2 text-xs font-bold text-warm-accent">Current</span>
            ) : null}
          </p>
          <p className="mt-0.5 text-sm text-warm-brown-soft">
            <span className="font-semibold text-warm-body">{inProgress}</span> of{" "}
            <span className="font-semibold text-warm-body">{levelQuest.bank_total}</span> words in
            progress —{" "}
            <span className="font-semibold text-warm-body">{levelQuest.mastered}</span> mastered
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-bold tabular-nums ${readinessTone}`}>
            {readinessPct}% ready
          </span>
          <span className="text-warm-muted" aria-hidden>
            {open ? "▾" : "▸"}
          </span>
        </div>
      </button>

      {open && (
        <div className="space-y-4 border-t border-white/60 px-4 pb-4 pt-3">
          <StrengthProgressBar
            counts={levelQuest}
            barClassName="h-2.5"
            ariaLabel={`Level ${levelQuest.level} progress`}
          />
          <div className="space-y-3">
            {levelQuest.milestones.map((milestone) => (
              <QuestMilestoneRow key={milestone.badge_type} milestone={milestone} />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
