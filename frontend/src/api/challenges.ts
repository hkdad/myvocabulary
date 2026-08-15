import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type ChallengeSummary = {
  id: number | null;
  challenge_type: string;
  title: string;
  description: string;
  target_level: string | null;
  status: string | null;
  can_start: boolean;
  word_count: number | null;
  pass_threshold: number | null;
  readiness_score: number | null;
  lock_reason: string | null;
};

export type ChallengeWord = {
  dictionary_entry_id: number;
  word_index: number;
  total_words: number;
  definition: string | null;
  choices: string[];
};

export type ChallengeSession = {
  id: number;
  challenge_type: string;
  target_level: string | null;
  status: string;
  pass_threshold: number;
  total_words: number;
  words: ChallengeWord[];
  started_at: string | null;
};

export type ChallengeResult = {
  id: number;
  status: string;
  score: number;
  passed: boolean;
  correct_count: number;
  total_words: number;
  badge_earned: string | null;
  new_english_level: string | null;
};

export type LearnerBadge = {
  id: number;
  badge_type: string;
  earned_at: string;
};

export async function getAvailableChallenges(): Promise<{ challenges: ChallengeSummary[] }> {
  return apiFetch("/challenges/available", undefined, API_BASE_URL);
}

export async function startChallenge(payload: {
  challenge_type: string;
  challenge_id?: number | null;
  target_level?: string | null;
}): Promise<ChallengeSession> {
  return apiFetch<ChallengeSession>(
    "/challenges/start",
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function submitChallenge(
  challengeId: number,
  answers: { dictionary_entry_id: number; answer: string }[],
): Promise<ChallengeResult> {
  return apiFetch<ChallengeResult>(
    `/challenges/${challengeId}/submit`,
    { method: "POST", body: JSON.stringify({ answers }) },
    API_BASE_URL,
  );
}

export async function getChallengeBadges(): Promise<{ badges: LearnerBadge[] }> {
  return apiFetch("/challenges/badges", undefined, API_BASE_URL);
}
