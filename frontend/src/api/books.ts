import { apiFetch, apiFetchForm } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type BookLemmaSample = {
  id: number;
  lemma: string;
  frequency: number;
  rank: number;
  in_study_set: boolean;
  is_hidden: boolean;
  matched_baseline: boolean;
};

export type BookProgress = {
  learner_id: number;
  study_known: number;
  study_total: number;
  study_progress_percent: number;
  page_known: number;
  content_total: number;
  page_coverage_percent: number;
  ready_to_read: boolean;
  days_estimate: number;
};

export type BookSummary = {
  id: number;
  title: string;
  original_filename: string;
  status: string;
  coverage_target: number;
  token_count: number;
  unique_lemma_count: number;
  content_lemma_count: number;
  study_lemma_count: number;
  skipped_function_words: number;
  skipped_proper_nouns: number;
  coverage_curve: Record<string, number>;
  days_at_five_new: number;
  word_list_id: number | null;
  assigned_learner_ids: number[];
  analysis_engine: string;
  confirmed_at: string | null;
  created_at: string | null;
  baseline_match_count?: number;
  new_word_count?: number;
  sample_study?: BookLemmaSample[];
  sample_advanced?: BookLemmaSample[];
};

export async function previewBook(file: File): Promise<BookSummary> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetchForm<BookSummary>("/books/preview", formData, API_BASE_URL);
}

export async function listBooks(): Promise<BookSummary[]> {
  const response = await apiFetch<{ books: BookSummary[] }>("/books", {}, API_BASE_URL);
  return response.books;
}

export async function getBook(bookId: number): Promise<BookSummary> {
  return apiFetch<BookSummary>(`/books/${bookId}`, {}, API_BASE_URL);
}

export async function confirmBook(
  bookId: number,
  coverageTarget?: number,
): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}/confirm`,
    { method: "POST", body: JSON.stringify({ coverage_target: coverageTarget ?? null }) },
    API_BASE_URL,
  );
}

export async function assignBook(bookId: number, learnerId: number): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}/assign`,
    { method: "POST", body: JSON.stringify({ learner_id: learnerId }) },
    API_BASE_URL,
  );
}

export async function unassignBook(bookId: number, learnerId: number): Promise<BookSummary> {
  return apiFetch<BookSummary>(`/books/${bookId}/assign/${learnerId}`, { method: "DELETE" }, API_BASE_URL);
}

export async function hideBookLemma(
  bookId: number,
  lemmaId: number,
  hidden: boolean,
): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}/lemmas/${lemmaId}`,
    { method: "PATCH", body: JSON.stringify({ hidden }) },
    API_BASE_URL,
  );
}

export async function getBookProgress(bookId: number, learnerId?: number): Promise<BookProgress[]> {
  const params = learnerId != null ? `?learner_id=${learnerId}` : "";
  return apiFetch<BookProgress[]>(`/books/${bookId}/progress${params}`, {}, API_BASE_URL);
}

export async function getMyBookProgress(): Promise<BookProgress | null> {
  return apiFetch<BookProgress | null>("/loop/book-progress", {}, API_BASE_URL);
}
