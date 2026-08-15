import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type DictionaryEntrySummary = {
  id: number;
  word: string;
  definition: string;
  definition_zh_hant?: string | null;
  part_of_speech: string | null;
  phonetic: string | null;
  has_audio: boolean;
};

export type WordListItem = {
  id: number;
  sort_order: number;
  notes: string | null;
  dictionary_entry: DictionaryEntrySummary;
};

export type WordListSummary = {
  id: number;
  name: string;
  description: string | null;
  level_tag: string | null;
  source: string;
  source_url: string | null;
  is_active: boolean;
  item_count: number;
  assigned_learner_ids: number[];
  created_by_learner_id?: number | null;
  created_at: string;
  updated_at: string;
  due_date?: string | null;
};

export type WordListDetail = WordListSummary & {
  items: WordListItem[];
};

export type LearnerSummary = {
  id: number;
  username: string;
  display_name: string;
};

export async function listWordLists(): Promise<WordListSummary[]> {
  return apiFetch<WordListSummary[]>("/word-lists", {}, API_BASE_URL);
}

export async function listCatalog(level?: string): Promise<WordListSummary[]> {
  const params = level ? `?level=${encodeURIComponent(level)}` : "";
  const response = await apiFetch<{ lists: WordListSummary[] }>(
    `/word-lists/catalog${params}`,
    {},
    API_BASE_URL,
  );
  return response.lists;
}

export async function listAssignedWordLists(): Promise<WordListSummary[]> {
  const response = await apiFetch<{ lists: WordListSummary[] }>(
    "/word-lists/assigned",
    {},
    API_BASE_URL,
  );
  return response.lists;
}

export async function getWordList(id: number): Promise<WordListDetail> {
  return apiFetch<WordListDetail>(`/word-lists/${id}`, {}, API_BASE_URL);
}

export async function createWordList(payload: {
  name: string;
  description?: string;
  level_tag?: string;
}): Promise<WordListDetail> {
  return apiFetch<WordListDetail>(
    "/word-lists",
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function deleteWordList(listId: number): Promise<void> {
  return apiFetch<void>(`/word-lists/${listId}`, { method: "DELETE" }, API_BASE_URL);
}

export async function addWordToList(
  listId: number,
  payload: { word: string; notes?: string },
): Promise<WordListItem> {
  return apiFetch<WordListItem>(
    `/word-lists/${listId}/items`,
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function removeWordFromList(listId: number, itemId: number): Promise<void> {
  return apiFetch<void>(`/word-lists/${listId}/items/${itemId}`, { method: "DELETE" }, API_BASE_URL);
}

export async function assignWordList(
  listId: number,
  payload: { learner_ids: number[]; due_date?: string },
): Promise<void> {
  await apiFetch(
    `/word-lists/${listId}/assign`,
    { method: "POST", body: JSON.stringify(payload) },
    API_BASE_URL,
  );
}

export async function unassignWordList(listId: number, learnerId: number): Promise<void> {
  return apiFetch<void>(
    `/word-lists/${listId}/assign/${learnerId}`,
    { method: "DELETE" },
    API_BASE_URL,
  );
}
