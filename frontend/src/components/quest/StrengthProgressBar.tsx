import { inProgressCount, strengthSegments, type StrengthCounts } from "../../lib/strengthStyles";

type Props = {
  counts: StrengthCounts;
  barClassName?: string;
  showTags?: boolean;
  ariaLabel: string;
};

export default function StrengthProgressBar({
  counts,
  barClassName = "h-3",
  showTags = true,
  ariaLabel,
}: Props) {
  const total = counts.bank_total;
  const segments = strengthSegments(counts, total);
  const progress = inProgressCount(counts);

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
