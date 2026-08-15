import { useEffect, useState } from "react";

import {
  acceptLevelSuggestion,
  dismissLevelSuggestion,
  getLearnerReadiness,
  runLevelAssessment,
  shouldSuggestAssessment,
  type AssessmentSuggestion,
  type LevelSuggestion,
  type ReadinessResponse,
} from "../api/levelAssessment";

type Props = {
  learnerId: number;
  learnerName: string;
  initialSuggestion?: LevelSuggestion | null;
  onUpdated?: () => void;
};

const STATUS_CONFIG = {
  excellent: { emoji: "🌟", color: "text-green-700" },
  strong: { emoji: "💪", color: "text-green-600" },
  good: { emoji: "👍", color: "text-blue-600" },
  fair: { emoji: "📈", color: "text-amber-600" },
  weak: { emoji: "⚠️", color: "text-red-600" },
};

const RECOMMENDATION_CONFIG = {
  ready: {
    emoji: "🎯",
    text: "Ready for level-up!",
    color: "text-green-700",
  },
  progressing: {
    emoji: "📊",
    text: "Progressing well",
    color: "text-blue-700",
  },
  keep_practicing: {
    emoji: "💪",
    text: "Keep practicing",
    color: "text-amber-700",
  },
};

export default function LevelSuggestionCard({
  learnerId,
  learnerName,
  initialSuggestion = null,
  onUpdated,
}: Props) {
  const [suggestion, setSuggestion] = useState<LevelSuggestion | null>(initialSuggestion);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [autoSuggest, setAutoSuggest] = useState<AssessmentSuggestion | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [readinessLoading, setReadinessLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSuggestion(initialSuggestion);
  }, [initialSuggestion]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setReadinessLoading(true);
      try {
        const [ready, nudge] = await Promise.all([
          getLearnerReadiness(learnerId),
          shouldSuggestAssessment(learnerId),
        ]);
        if (!cancelled) {
          setReadiness(ready);
          setAutoSuggest(nudge);
        }
      } catch {
        if (!cancelled) {
          setReadiness(null);
          setAutoSuggest(null);
        }
      } finally {
        if (!cancelled) {
          setReadinessLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [learnerId, suggestion?.status]);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const result = await runLevelAssessment(learnerId);
      setSuggestion(result);
      const ready = await getLearnerReadiness(learnerId);
      setReadiness(ready);
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assessment failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleAccept() {
    if (!suggestion?.id) return;
    setLoading(true);
    setError(null);
    try {
      await acceptLevelSuggestion(suggestion.id);
      setSuggestion({ ...suggestion, status: "accepted" });
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept");
    } finally {
      setLoading(false);
    }
  }

  async function handleDismiss() {
    if (!suggestion?.id) return;
    setLoading(true);
    setError(null);
    try {
      await dismissLevelSuggestion(suggestion.id);
      setSuggestion({ ...suggestion, status: "dismissed" });
      onUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not dismiss");
    } finally {
      setLoading(false);
    }
  }

  const pending =
    suggestion?.status === "pending" &&
    suggestion.suggested_level !== suggestion.current_level;

  const scorePercent = readiness ? Math.round(readiness.overall_score * 100) : null;
  const recConfig = readiness ? RECOMMENDATION_CONFIG[readiness.recommendation] : null;

  return (
    <article className="overflow-hidden rounded-2xl border border-warm-input-border bg-white/80">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            {readinessLoading && (
              <p className="text-sm text-warm-brown-soft">Loading readiness for {learnerName}…</p>
            )}
            {!readinessLoading && readiness && recConfig && scorePercent !== null && (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{recConfig.emoji}</span>
                  <div>
                    <p className="font-bold text-warm-brown">{learnerName}</p>
                    <p className={`text-sm font-semibold ${recConfig.color}`}>{recConfig.text}</p>
                  </div>
                </div>
                <div className="mt-3 flex items-end justify-between gap-3">
                  <div className="flex-1">
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-warm-cream">
                      <div
                        className={`h-full rounded-full transition-all ${
                          scorePercent >= 75
                            ? "bg-green-500"
                            : scorePercent >= 60
                              ? "bg-blue-500"
                              : "bg-amber-500"
                        }`}
                        style={{ width: `${scorePercent}%` }}
                      />
                    </div>
                    <p className="mt-1 text-xs text-warm-muted">
                      Readiness {scorePercent}% · Level {readiness.metadata.current_level} · Streak{" "}
                      {readiness.metadata.streak_days}d
                    </p>
                  </div>
                  <p className="text-3xl font-extrabold text-warm-brown">{scorePercent}%</p>
                </div>
              </>
            )}
            {!readinessLoading && !readiness && (
              <p className="font-bold text-warm-brown">{learnerName}</p>
            )}
          </div>
          <button
            type="button"
            onClick={() => void handleRun()}
            className="warm-btn warm-btn-secondary shrink-0 text-xs"
            disabled={loading}
          >
            {loading ? "…" : "Run check"}
          </button>
        </div>

        {autoSuggest?.should_suggest && !pending && (
          <div className="mt-3 rounded-xl bg-green-50 px-3 py-2 text-sm text-green-800">
            <strong>Ready for a check?</strong> {autoSuggest.reason}
          </div>
        )}

        {!autoSuggest?.should_suggest && autoSuggest?.reason && (
          <p className="mt-2 text-xs text-warm-muted">{autoSuggest.reason}</p>
        )}

        {error && <p className="mt-2 text-sm text-red-700">{error}</p>}

        {suggestion?.reason && suggestion.status !== "none" && (
          <p className="mt-3 text-sm text-warm-body">{suggestion.reason}</p>
        )}
        {suggestion?.status === "none" && suggestion.reason && (
          <p className="mt-3 text-sm text-warm-body">{suggestion.reason}</p>
        )}

        {pending && suggestion && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-amber-100 px-3 py-1 text-sm font-bold text-amber-900">
              {suggestion.current_level} → {suggestion.suggested_level}
            </span>
            <span className="text-xs text-warm-muted">via {suggestion.source}</span>
            <button
              type="button"
              onClick={() => void handleAccept()}
              className="warm-btn warm-btn-primary text-xs"
              disabled={loading}
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => void handleDismiss()}
              className="warm-btn warm-btn-ghost text-xs"
              disabled={loading}
            >
              Dismiss
            </button>
          </div>
        )}

        {suggestion?.status === "accepted" && (
          <p className="mt-2 text-sm font-semibold text-green-700">
            Level updated to {suggestion.suggested_level}. A level-up challenge was unlocked for{" "}
            {learnerName}.
          </p>
        )}

        {readiness && (
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="mt-3 text-xs font-semibold text-warm-muted hover:text-warm-brown"
          >
            {expanded ? "Hide details ▲" : "Show details ▼"}
          </button>
        )}
      </div>

      {expanded && readiness && (
        <div className="border-t border-warm-cream bg-warm-cream/20 p-4">
          <h4 className="mb-2 text-sm font-bold text-warm-brown">Dimension breakdown</h4>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(readiness.dimensions).map(([key, dim]) => {
              const config = STATUS_CONFIG[dim.status as keyof typeof STATUS_CONFIG];
              const dimPercent = Math.round(dim.score * 100);
              return (
                <div key={key} className="rounded-lg bg-white/70 p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">{config?.emoji ?? "•"}</span>
                      <div>
                        <p className="text-xs font-semibold capitalize text-warm-brown">
                          {key.replace(/_/g, " ")}
                        </p>
                        <p className={`text-xs ${config?.color ?? "text-warm-muted"}`}>
                          {dim.status}
                        </p>
                      </div>
                    </div>
                    <p className="font-bold text-warm-brown">{dimPercent}%</p>
                  </div>
                  <p className="mt-1 text-xs text-warm-brown-soft">{dim.description}</p>
                </div>
              );
            })}
          </div>

          {readiness.focus_areas.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-sm font-bold text-warm-brown">Focus areas</h4>
              <ul className="space-y-1.5">
                {readiness.focus_areas.map((area) => (
                  <li key={area} className="flex gap-2 text-sm text-warm-body">
                    <span className="text-amber-600">•</span>
                    <span>{area}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-lg bg-white/70 p-2.5">
              <p className="text-warm-brown-soft">Review samples</p>
              <p className="font-bold text-warm-brown">{readiness.metadata.review_samples}</p>
            </div>
            <div className="rounded-lg bg-white/70 p-2.5">
              <p className="text-warm-brown-soft">Est. weeks to ready</p>
              <p className="font-bold text-warm-brown">
                {readiness.estimated_weeks_to_ready === 0
                  ? "Ready now!"
                  : `~${readiness.estimated_weeks_to_ready} weeks`}
              </p>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
