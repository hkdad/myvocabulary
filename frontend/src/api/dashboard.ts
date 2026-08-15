import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type LearnerProgressSummary = {
  learner_id: number;
  display_name: string;
  username: string;
  english_level: string;
  ui_mode: string;
  emoji: string;
  due_count: number;
  reviewed_today: number;
  daily_practice_goal: number;
  daily_new_word_goal: number;
  daily_learning_retention_goal: number;
  daily_mastered_retention_goal: number;
  daily_retention_goal: number;
  review_accuracy_percent: number;
  streak_days: number;
  dictation_sessions_completed: number;
  unresolved_mistakes: number;
  assigned_lists: number;
  learning_count: number;
  familiar_count: number;
  mastered_count: number;
  new_released_today: number;
  new_remaining_today: number;
  daily_challenge_completed: boolean;
  bank_at_level: number;
  due_overloaded: boolean;
};

export type LearnerMeStats = {
  english_level: string;
  display_name: string;
  due_count: number;
  reviewed_today: number;
  daily_practice_goal: number;
  daily_new_word_goal: number;
  daily_learning_retention_goal: number;
  daily_mastered_retention_goal: number;
  daily_retention_goal: number;
  review_accuracy_percent: number;
  streak_days: number;
  dictation_sessions_completed: number;
  unresolved_mistakes: number;
  learning_count: number;
  familiar_count: number;
  mastered_count: number;
  new_released_today: number;
  new_remaining_today: number;
  new_released_this_week: number;
  weekly_new_target: number;
  daily_challenge_completed: boolean;
  daily_challenge_srs_completed: boolean;
  daily_challenge_dictation_completed: boolean;
};

export type TrendDayPoint = {
  date: string;
  reviews: number;
  correct_reviews: number;
  accuracy_percent: number;
  new_words: number;
  challenge_completed: boolean;
  learning_count: number;
  familiar_count: number;
  mastered_count: number;
};

export type LearnerTrendSeries = {
  learner_id: number;
  display_name: string;
  emoji: string;
  days: TrendDayPoint[];
};

export type FamilyTrends = {
  days: number;
  learners: LearnerTrendSeries[];
};

export async function getDashboardOverview(): Promise<LearnerProgressSummary[]> {
  const response = await apiFetch<{ learners: LearnerProgressSummary[] }>(
    "/dashboard/overview",
    {},
    API_BASE_URL,
  );
  return response.learners;
}

export async function getFamilyTrends(days = 14): Promise<FamilyTrends> {
  const search = new URLSearchParams({ days: String(days) });
  return apiFetch<FamilyTrends>(`/dashboard/trends?${search}`, {}, API_BASE_URL);
}

export async function getMyStats(): Promise<LearnerMeStats> {
  return apiFetch<LearnerMeStats>("/dashboard/me", {}, API_BASE_URL);
}
