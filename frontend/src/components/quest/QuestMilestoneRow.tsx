import type { MilestoneQuest } from "../../api/loop";

type Props = {
  milestone: MilestoneQuest;
};

export default function QuestMilestoneRow({ milestone }: Props) {
  if (milestone.earned) {
    return (
      <p className="flex items-center gap-2 text-sm font-semibold text-green-700">
        <span aria-hidden>✓</span>
        <span>{milestone.label}</span>
        <span className="text-warm-muted">
          {milestone.current}/{milestone.target}
        </span>
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-sm">
        <p className="font-semibold text-warm-brown">{milestone.label}</p>
        <p className="text-warm-brown-soft">
          {milestone.current}/{milestone.target}
        </p>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/70">
        <div
          className="h-full rounded-full bg-purple-400 transition-all"
          style={{ width: `${milestone.progress_percent}%` }}
        />
      </div>
    </div>
  );
}
