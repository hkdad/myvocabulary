import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type LevelSuggestion = {
  id: number | null;
  learner_id: number;
  current_level: string;
  suggested_level: string;
  reason: string | null;
  source: string;
  confidence: number | null;
  status: string;
  assessed_at: string | null;
};

export async function getLevelSuggestion(learnerId: number): Promise<LevelSuggestion> {
  return apiFetch<LevelSuggestion>(
    `/level-assessment/learners/${learnerId}`,
    undefined,
    API_BASE_URL,
  );
}

export async function runLevelAssessment(learnerId: number): Promise<LevelSuggestion> {
  return apiFetch<LevelSuggestion>(
    `/level-assessment/learners/${learnerId}/run`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function acceptLevelSuggestion(assessmentId: number): Promise<{
  assessment_id: number;
  learner_id: number;
  english_level: string;
  status: string;
}> {
  return apiFetch(
    `/level-assessment/${assessmentId}/accept`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function dismissLevelSuggestion(assessmentId: number): Promise<{
  assessment_id: number;
  learner_id: number;
  english_level: string;
  status: string;
}> {
  return apiFetch(
    `/level-assessment/${assessmentId}/dismiss`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export type DimensionScore = {
  score: number;
  weight: number;
  status: string;
  description: string;
};

export type ReadinessMetadata = {
  current_level: string;
  streak_days: number;
  review_samples: number;
  total_mistakes: number;
};

export type ReadinessResponse = {
  overall_score: number;
  dimensions: Record<string, DimensionScore>;
  recommendation: "ready" | "progressing" | "keep_practicing";
  focus_areas: string[];
  estimated_weeks_to_ready: number;
  metadata: ReadinessMetadata;
};

export async function getLearnerReadiness(learnerId: number): Promise<ReadinessResponse> {
  return apiFetch<ReadinessResponse>(
    `/level-assessment/learners/${learnerId}/readiness`,
    undefined,
    API_BASE_URL,
  );
}

export type AssessmentSuggestion = {
  should_suggest: boolean;
  reason: string | null;
  cooldown_days_remaining: number;
};

export async function shouldSuggestAssessment(learnerId: number): Promise<AssessmentSuggestion> {
  return apiFetch<AssessmentSuggestion>(
    `/level-assessment/learners/${learnerId}/should-suggest`,
    undefined,
    API_BASE_URL,
  );
}
