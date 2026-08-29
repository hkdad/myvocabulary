import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";
import type { DictionaryEntrySummary } from "./wordLists";

export type SrsCard = {
  id: number;
  dictionary_entry: DictionaryEntrySummary;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  due_at: string;
  last_reviewed_at: string | null;
  last_quality: number | null;
  state: string;
  word_list_id: number | null;
  level: string | null;
  books: string[];
  strength: string;
};

export type DueCardsResponse = {
  cards: SrsCard[];
  due_count: number;
  daily_goal: number;
};

export type ReviewStats = {
  reviewed_today: number;
  due_count: number;
  daily_goal: number;
  total_cards: number;
};

export type InitializeReviewsResponse = {
  created_count: number;
  skipped_count: number;
  total_cards: number;
};

export type InitializeMistakeReviewsResponse = {
  created_count: number;
  mistake_count: number;
};

export type CompleteMistakeChallengeResponse = {
  resolved_count: number;
  entry_count: number;
};

export async function initializeReviews(wordListId: number): Promise<InitializeReviewsResponse> {
  return apiFetch<InitializeReviewsResponse>(
    `/reviews/initialize?word_list_id=${wordListId}`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function initializeMistakeReviews(): Promise<InitializeMistakeReviewsResponse> {
  return apiFetch<InitializeMistakeReviewsResponse>(
    "/reviews/initialize-mistakes",
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function completeMistakeChallenge(
  dictionaryEntryIds: number[],
): Promise<CompleteMistakeChallengeResponse> {
  return apiFetch<CompleteMistakeChallengeResponse>(
    "/reviews/mistakes/complete",
    {
      method: "POST",
      body: JSON.stringify({ dictionary_entry_ids: dictionaryEntryIds }),
    },
    API_BASE_URL,
  );
}

export async function getDueCards(options?: {
  limit?: number;
  wordListId?: number;
  mistakesOnly?: boolean;
  dailyChallenge?: boolean;
  practiceAll?: boolean;
}): Promise<DueCardsResponse> {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) {
    params.set("limit", String(options.limit));
  }
  if (options?.wordListId !== undefined) {
    params.set("word_list_id", String(options.wordListId));
  }
  if (options?.mistakesOnly) {
    params.set("mistakes_only", "true");
  }
  if (options?.dailyChallenge) {
    params.set("daily_challenge", "true");
  }
  if (options?.practiceAll) {
    params.set("practice_all", "true");
  }
  const query = params.toString();
  return apiFetch<DueCardsResponse>(`/reviews/due${query ? `?${query}` : ""}`, {}, API_BASE_URL);
}

export async function getReviewStats(): Promise<ReviewStats> {
  return apiFetch<ReviewStats>("/reviews/stats", {}, API_BASE_URL);
}

export async function answerCard(cardId: number, quality: number): Promise<SrsCard> {
  const response = await apiFetch<{ card: SrsCard }>(
    `/reviews/${cardId}/answer`,
    { method: "POST", body: JSON.stringify({ quality }) },
    API_BASE_URL,
  );
  return response.card;
}
