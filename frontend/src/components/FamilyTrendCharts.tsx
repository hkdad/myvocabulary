import type { FamilyTrends, LearnerTrendSeries } from "../api/dashboard";

const LEARNER_COLORS = ["#016CBA", "#D97706", "#059669", "#7C3AED"] as const;
const STRENGTH_COLORS = {
  learning: "#016CBA",
  familiar: "#D97706",
  mastered: "#059669",
} as const;

type Props = {
  trends: FamilyTrends;
};

function hasAnyActivity(trends: FamilyTrends): boolean {
  return trends.learners.some((learner) =>
    learner.days.some(
      (day) =>
        day.reviews > 0 ||
        day.new_words > 0 ||
        day.challenge_completed ||
        day.learning_count + day.familiar_count + day.mastered_count > 0,
    ),
  );
}

function formatShortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

function FamilyReviewsChart({ learners }: { learners: LearnerTrendSeries[] }) {
  const days = learners[0]?.days ?? [];
  const width = 560;
  const height = 160;
  const pad = { top: 12, right: 12, bottom: 28, left: 28 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const maxReviews = Math.max(
    1,
    ...learners.flatMap((learner) => learner.days.map((day) => day.reviews)),
  );
  const groupWidth = innerW / Math.max(days.length, 1);
  const barWidth = Math.max(3, (groupWidth * 0.7) / Math.max(learners.length, 1));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-40 w-full" role="img" aria-label="Reviews per day">
      <line
        x1={pad.left}
        y1={pad.top + innerH}
        x2={pad.left + innerW}
        y2={pad.top + innerH}
        stroke="#E2E8F0"
      />
      {days.map((day, dayIndex) => {
        const labelX = pad.left + dayIndex * groupWidth + groupWidth / 2;
        return (
          <g key={day.date}>
            {learners.map((learner, learnerIndex) => {
              const value = learner.days[dayIndex]?.reviews ?? 0;
              const barH = (value / maxReviews) * innerH;
              const x =
                pad.left +
                dayIndex * groupWidth +
                groupWidth * 0.15 +
                learnerIndex * barWidth;
              const y = pad.top + innerH - barH;
              return (
                <rect
                  key={`${learner.learner_id}-${day.date}`}
                  x={x}
                  y={y}
                  width={barWidth}
                  height={Math.max(barH, value > 0 ? 2 : 0)}
                  rx={2}
                  fill={LEARNER_COLORS[learnerIndex % LEARNER_COLORS.length]}
                >
                  <title>
                    {learner.display_name}: {value} review{value === 1 ? "" : "s"} on{" "}
                    {formatShortDate(day.date)}
                  </title>
                </rect>
              );
            })}
            {(dayIndex === 0 ||
              dayIndex === days.length - 1 ||
              dayIndex === Math.floor(days.length / 2)) && (
              <text
                x={labelX}
                y={height - 8}
                textAnchor="middle"
                className="fill-warm-muted text-[10px]"
              >
                {formatShortDate(day.date)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function VocabularyStackChart({ learner }: { learner: LearnerTrendSeries }) {
  const width = 520;
  const height = 140;
  const pad = { top: 8, right: 8, bottom: 28, left: 28 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const days = learner.days;
  const barWidth = innerW / Math.max(days.length, 1);
  const maxTotal = Math.max(
    1,
    ...days.map((day) => day.learning_count + day.familiar_count + day.mastered_count),
  );

  return (
    <div className="rounded-2xl bg-white/70 p-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-extrabold text-warm-brown">
          <span className="mr-1" aria-hidden>
            {learner.emoji}
          </span>
          {learner.display_name} · words accumulated
        </p>
        <div className="flex flex-wrap gap-2 text-xs font-semibold text-warm-body">
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: STRENGTH_COLORS.learning }}
            />
            Learning
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: STRENGTH_COLORS.familiar }}
            />
            Familiar
          </span>
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: STRENGTH_COLORS.mastered }}
            />
            Mastered
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-36 w-full"
        role="img"
        aria-label={`${learner.display_name} vocabulary growth`}
      >
        <line
          x1={pad.left}
          y1={pad.top + innerH}
          x2={pad.left + innerW}
          y2={pad.top + innerH}
          stroke="#E2E8F0"
        />
        {days.map((day, index) => {
          const x = pad.left + index * barWidth + barWidth * 0.12;
          const w = barWidth * 0.76;
          const total = day.learning_count + day.familiar_count + day.mastered_count;
          const scale = innerH / maxTotal;
          const masteredH = day.mastered_count * scale;
          const familiarH = day.familiar_count * scale;
          const learningH = day.learning_count * scale;
          const baseY = pad.top + innerH;
          const masteredY = baseY - masteredH;
          const familiarY = masteredY - familiarH;
          const learningY = familiarY - learningH;
          return (
            <g key={day.date}>
              {day.mastered_count > 0 && (
                <rect
                  x={x}
                  y={masteredY}
                  width={w}
                  height={Math.max(masteredH, 2)}
                  fill={STRENGTH_COLORS.mastered}
                  rx={2}
                />
              )}
              {day.familiar_count > 0 && (
                <rect
                  x={x}
                  y={familiarY}
                  width={w}
                  height={Math.max(familiarH, 2)}
                  fill={STRENGTH_COLORS.familiar}
                  rx={2}
                />
              )}
              {day.learning_count > 0 && (
                <rect
                  x={x}
                  y={learningY}
                  width={w}
                  height={Math.max(learningH, 2)}
                  fill={STRENGTH_COLORS.learning}
                  rx={2}
                />
              )}
              <title>
                {formatShortDate(day.date)}: {day.learning_count} learning ·{" "}
                {day.familiar_count} familiar · {day.mastered_count} mastered ({total} total)
              </title>
              {(index === 0 ||
                index === days.length - 1 ||
                index === Math.floor(days.length / 2)) && (
                <text
                  x={x + w / 2}
                  y={height - 8}
                  textAnchor="middle"
                  className="fill-warm-muted text-[10px]"
                >
                  {formatShortDate(day.date)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function LearnerStripChart({
  learner,
  color,
}: {
  learner: LearnerTrendSeries;
  color: string;
}) {
  const width = 520;
  const height = 72;
  const pad = { top: 10, right: 8, bottom: 18, left: 8 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const n = Math.max(learner.days.length - 1, 1);

  const points = learner.days
    .map((day, index) => {
      const x = pad.left + (index / n) * innerW;
      const y = pad.top + innerH - (day.accuracy_percent / 100) * innerH;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="rounded-2xl bg-white/70 p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <p className="text-sm font-extrabold text-warm-brown">
          <span className="mr-1" aria-hidden>
            {learner.emoji}
          </span>
          {learner.display_name}
        </p>
        <p className="text-xs font-semibold text-warm-muted">Accuracy + challenge</p>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-16 w-full"
        role="img"
        aria-label={`${learner.display_name} accuracy trend`}
      >
        <line
          x1={pad.left}
          y1={pad.top + innerH}
          x2={pad.left + innerW}
          y2={pad.top + innerH}
          stroke="#E2E8F0"
        />
        <polyline fill="none" stroke={color} strokeWidth="2.5" points={points} />
        {learner.days.map((day, index) => {
          const x = pad.left + (index / n) * innerW;
          const y = pad.top + innerH - (day.accuracy_percent / 100) * innerH;
          return (
            <g key={day.date}>
              <circle cx={x} cy={y} r={day.reviews > 0 ? 3 : 1.5} fill={color} opacity={0.9}>
                <title>
                  {formatShortDate(day.date)}: {day.accuracy_percent}% · {day.reviews} reviews ·{" "}
                  {day.new_words} new
                </title>
              </circle>
              {day.challenge_completed && (
                <circle cx={x} cy={pad.top + 2} r={3.5} fill="#059669">
                  <title>Daily challenge completed {formatShortDate(day.date)}</title>
                </circle>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default function FamilyTrendCharts({ trends }: Props) {
  if (!hasAnyActivity(trends)) {
    return (
      <p className="mt-4 text-sm font-semibold text-warm-brown-soft">
        Practice a few days to see trends — reviews, new words, and daily challenges will show
        here.
      </p>
    );
  }

  return (
    <div className="mt-5 space-y-4">
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-extrabold text-warm-brown">
            Reviews · last {trends.days} days
          </p>
          <div className="flex flex-wrap gap-3">
            {trends.learners.map((learner, index) => (
              <span
                key={learner.learner_id}
                className="flex items-center gap-1.5 text-xs font-semibold text-warm-body"
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: LEARNER_COLORS[index % LEARNER_COLORS.length] }}
                />
                {learner.display_name}
              </span>
            ))}
          </div>
        </div>
        <FamilyReviewsChart learners={trends.learners} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {trends.learners.map((learner) => (
          <VocabularyStackChart key={learner.learner_id} learner={learner} />
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {trends.learners.map((learner, index) => (
          <LearnerStripChart
            key={learner.learner_id}
            learner={learner}
            color={LEARNER_COLORS[index % LEARNER_COLORS.length]}
          />
        ))}
      </div>
      <p className="text-xs font-semibold text-warm-muted">
        Vocabulary chart shows end-of-day totals by strength. Green dots mark daily challenge
        completion. Accuracy line uses reviews rated 3+ / 5.
      </p>
    </div>
  );
}
