export const STRENGTH_STYLES = {
  learning: { fill: "bg-amber-400", tag: "bg-amber-400 text-white" },
  familiar: { fill: "bg-blue-400", tag: "bg-blue-400 text-white" },
  mastered: { fill: "bg-emerald-500", tag: "bg-emerald-500 text-white" },
} as const;

export function segmentPercent(count: number, total: number): number {
  if (total <= 0 || count <= 0) {
    return 0;
  }
  return (count / total) * 100;
}

export type StrengthCounts = {
  bank_total: number;
  released?: number;
  learning: number;
  familiar: number;
  mastered: number;
};

export function inProgressCount(counts: StrengthCounts): number {
  return counts.learning + counts.familiar + counts.mastered;
}

export function strengthSegments(counts: StrengthCounts, total: number) {
  return [
    {
      key: "learning" as const,
      label: "Learning",
      count: counts.learning,
      pct: segmentPercent(counts.learning, total),
      ...STRENGTH_STYLES.learning,
    },
    {
      key: "familiar" as const,
      label: "Familiar",
      count: counts.familiar,
      pct: segmentPercent(counts.familiar, total),
      ...STRENGTH_STYLES.familiar,
    },
    {
      key: "mastered" as const,
      label: "Mastered",
      count: counts.mastered,
      pct: segmentPercent(counts.mastered, total),
      ...STRENGTH_STYLES.mastered,
    },
  ];
}
