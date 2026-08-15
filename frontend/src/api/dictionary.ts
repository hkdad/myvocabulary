import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type DictionaryEntry = {
  id: number;
  word: string;
  phonetic: string | null;
  part_of_speech: string | null;
  definition: string;
  definition_zh_hant: string | null;
  example_sentence: string | null;
  synonyms: string[];
  source: string;
  has_audio: boolean;
};

export type DictionarySearchResponse = {
  query: string;
  results: DictionaryEntry[];
};

export type DictionarySuggestResponse = {
  query: string;
  suggestions: DictionaryEntry[];
};

export async function searchDictionary(
  query: string,
  limit = 20,
): Promise<DictionarySearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return apiFetch<DictionarySearchResponse>(`/dictionary/search?${params}`, {}, API_BASE_URL);
}

export async function suggestDictionary(
  query: string,
  limit = 5,
): Promise<DictionarySuggestResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  return apiFetch<DictionarySuggestResponse>(`/dictionary/suggest?${params}`, {}, API_BASE_URL);
}

export async function lookupWord(word: string): Promise<DictionaryEntry> {
  return apiFetch<DictionaryEntry>(
    `/dictionary/words/${encodeURIComponent(word)}`,
    {},
    API_BASE_URL,
  );
}

export type EnsureZhItem = {
  id: number;
  definition_zh_hant: string;
};

export async function ensureZhHant(entryIds: number[]): Promise<EnsureZhItem[]> {
  const uniqueIds = [...new Set(entryIds.filter((id) => id > 0))];
  if (uniqueIds.length === 0) {
    return [];
  }
  const response = await apiFetch<{ items: EnsureZhItem[] }>(
    "/dictionary/ensure-zh",
    {
      method: "POST",
      body: JSON.stringify({ entry_ids: uniqueIds.slice(0, 20) }),
    },
    API_BASE_URL,
  );
  return response.items;
}

export async function clearZhHant(entryId: number): Promise<void> {
  await apiFetch<{ id: number; definition_zh_hant: string | null }>(
    `/dictionary/entries/${entryId}/zh-hant`,
    { method: "DELETE" },
    API_BASE_URL,
  );
}
