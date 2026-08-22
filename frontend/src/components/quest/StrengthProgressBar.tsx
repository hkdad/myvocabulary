import { inProgressCount, strengthSegments, type StrengthCounts } from "../../lib/strengthStyles";

type Props = {
  counts: StrengthCounts;
  /** Override bar segment scale (defaults to in-progress count, else bank_total). */
  barDenominator?: number;
  barClassName?: string;
  showTags?: boolean;
  ariaLabel: string;
};

export default function StrengthProgressBar({
  counts,
  barDenominator,
  barClassName = "h-3",
  showTags = true,
  ariaLabel,
}: Props) {
  const total = counts.bank_total;
  const progress = inProgressCount(counts);
  // Scale bar to in-progress words so tiny bank slices do not render as stray slivers.
  const barTotal = barDenominator ?? (progress > 0 ? progress : total);
  const segments = strengthSegments(counts, barTotal);

  return (
    <div>
      <div
        className={`flex overflow-hidden rounded-full bg-white/70 ${barClassName}`}
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={ariaLabel}
      >
        {segments.map(
          (segment) =>
            segment.pct > 0 && (
              <div
                key={segment.key}
                className={`h-full ${segment.fill}`}
                style={{ width: `${segment.pct}%` }}
                title={`${segment.label}: ${segment.count}`}
              />
            ),
        )}
      </div>
      {showTags && (
        <div className="mt-2 flex flex-wrap gap-2 text-xs font-semibold">
          {segments.map((segment) => (
            <span key={segment.key} className={`rounded-full px-2.5 py-1 ${segment.tag}`}>
              {segment.label} {segment.count}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
