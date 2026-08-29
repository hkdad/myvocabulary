export const STRENGTH_STYLES = {
  new: { fill: "bg-violet-400", tag: "bg-violet-400 text-white" },
  learning: { fill: "bg-sky-400", tag: "bg-sky-400 text-white" },
  familiar: { fill: "bg-amber-400", tag: "bg-amber-400 text-white" },
  mastered: { fill: "bg-emerald-500", tag: "bg-emerald-500 text-white" },
} as const;

export type CardStrength = keyof typeof STRENGTH_STYLES;

export function strengthLabel(strength: string): string {
  if (strength === "familiar") return "Familiar";
  if (strength === "mastered") return "Mastered";
  if (strength === "new") return "New";
  return "Learning";
}

export function strengthTagClass(strength: string): string {
  if (strength === "mastered") return STRENGTH_STYLES.mastered.tag;
  if (strength === "familiar") return STRENGTH_STYLES.familiar.tag;
  if (strength === "new") return STRENGTH_STYLES.new.tag;
  return STRENGTH_STYLES.learning.tag;
}

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
