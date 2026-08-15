import { apiFetch, apiFetchBlob } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type DictationSession = {
  id: number;
  word_list_id: number | null;
  source?: "word_list" | "mistakes" | "daily_challenge";
  mode: "typed" | "choice";
  ui_mode_snapshot: string;
  total_words: number;
  correct_count: number;
  completed: boolean;
  started_at: string;
  completed_at: string | null;
};

export type DictationPrompt = {
  word_index: number;
  total_words: number;
  mode: "typed" | "choice";
  choices: string[] | null;
  hint: string | null;
  retries_remaining: number;
  session_complete: boolean;
};

export type DictationAnswerResult = {
  is_correct: boolean;
  expected_word: string | null;
  syllables: string[] | null;
  can_retry: boolean;
  retries_remaining: number;
  session_complete: boolean;
  correct_count: number;
  total_words: number;
};

export async function startDictationSession(payload: {
  word_list_id?: number;
  source?: "word_list" | "mistakes" | "daily_challenge";
  mode?: "typed" | "choice";
  max_words?: number;
  entry_ids?: number[];
}): Promise<DictationSession> {
  return apiFetch<DictationSession>(
    "/dictation/sessions",
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function getDictationPrompt(sessionId: number): Promise<DictationPrompt> {
  return apiFetch<DictationPrompt>(
    `/dictation/sessions/${sessionId}/next`,
    {},
    API_BASE_URL,
  );
}

export async function getDictationHint(sessionId: number): Promise<string> {
  const response = await apiFetch<{ hint: string }>(
    `/dictation/sessions/${sessionId}/hint`,
    {},
    API_BASE_URL,
  );
  return response.hint;
}

export async function fetchDictationAudio(
  sessionId: number,
  options?: { slow?: boolean; wordIndex?: number },
): Promise<Blob> {
  const params = new URLSearchParams();
  if (options?.slow) {
    params.set("slow", "true");
  }
  if (options?.wordIndex !== undefined) {
    params.set("word_index", String(options.wordIndex));
  }
  const query = params.toString();
  return apiFetchBlob(
    `/dictation/sessions/${sessionId}/audio${query ? `?${query}` : ""}`,
    API_BASE_URL,
  );
}

export async function submitDictationAnswer(
  sessionId: number,
  payload: { answer: string; hint_used?: boolean },
): Promise<DictationAnswerResult> {
  return apiFetch<DictationAnswerResult>(
    `/dictation/sessions/${sessionId}/answer`,
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function giveUpDictation(sessionId: number): Promise<DictationAnswerResult> {
  return apiFetch<DictationAnswerResult>(
    `/dictation/sessions/${sessionId}/give-up`,
    { method: "POST" },
    API_BASE_URL,
  );
}
