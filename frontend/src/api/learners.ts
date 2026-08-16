import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type LearnerProfile = {
  id: number;
  user_id: number;
  username: string;
  display_name: string;
  age: number;
  english_level: string;
  ui_mode: "kid" | "teen";
  emoji: string;
  avatar_url: string | null;
  daily_practice_goal: number;
  daily_new_word_goal: number;
  daily_learning_retention_mix: number;
  daily_mastered_retention_mix: number;
  is_active: boolean;
};

export type LearnerCreateInput = {
  username: string;
  password: string;
  display_name: string;
  age: number;
  english_level: string;
  ui_mode?: "kid" | "teen";
  emoji?: string;
  daily_new_word_goal?: number;
  daily_learning_retention_mix?: number;
  daily_mastered_retention_mix?: number;
};

export type LearnerUpdateInput = {
  display_name?: string;
  age?: number;
  english_level?: string;
  ui_mode?: "kid" | "teen";
  emoji?: string;
  daily_new_word_goal?: number;
  daily_learning_retention_mix?: number;
  daily_mastered_retention_mix?: number;
  is_active?: boolean;
};

export async function listLearners(): Promise<LearnerProfile[]> {
  return apiFetch<LearnerProfile[]>("/learners", {}, API_BASE_URL);
}

export async function createLearner(payload: LearnerCreateInput): Promise<LearnerProfile> {
  return apiFetch<LearnerProfile>(
    "/learners",
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function updateLearner(
  learnerId: number,
  payload: LearnerUpdateInput,
): Promise<LearnerProfile> {
  return apiFetch<LearnerProfile>(
    `/learners/${learnerId}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function deactivateLearner(learnerId: number): Promise<void> {
  await updateLearner(learnerId, { is_active: false });
}

export async function deleteLearner(learnerId: number): Promise<void> {
  await apiFetch<void>(
    `/learners/${learnerId}`,
    { method: "DELETE" },
    API_BASE_URL,
  );
}

export async function resetLearnerPassword(
  learnerId: number,
  password: string,
): Promise<void> {
  await apiFetch<void>(
    `/learners/${learnerId}/reset-password`,
    { method: "POST", body: JSON.stringify({ password }) },
    API_BASE_URL,
  );
}

export function defaultDailyPractice(uiMode: "kid" | "teen") {
  if (uiMode === "teen") {
    return {
      daily_new_word_goal: 8,
      daily_learning_retention_mix: 1,
      daily_mastered_retention_mix: 1,
    };
  }
  return {
    daily_new_word_goal: 5,
    daily_learning_retention_mix: 1,
    daily_mastered_retention_mix: 1,
  };
}

export function dailyPracticeTotal(goals: {
  daily_new_word_goal: number;
  daily_learning_retention_mix: number;
  daily_mastered_retention_mix: number;
}) {
  return (
    goals.daily_new_word_goal +
    goals.daily_learning_retention_mix +
    goals.daily_mastered_retention_mix
  );
}
