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
  learning_count: number;
  familiar_count: number;
  mastered_count: number;
};

export type BookSummary = {
  id: number;
  title: string;
  title_source?: string;
  title_needs_review?: boolean;
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
  title?: string,
): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}/confirm`,
    {
      method: "POST",
      body: JSON.stringify({ coverage_target: coverageTarget ?? null, title: title ?? null }),
    },
    API_BASE_URL,
  );
}

export async function updateBookTitle(bookId: number, title: string): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}`,
    { method: "PATCH", body: JSON.stringify({ title }) },
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

export async function deleteBook(bookId: number): Promise<void> {
  await apiFetch<void>(`/books/${bookId}`, { method: "DELETE" }, API_BASE_URL);
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

export type SuspiciousLemma = {
  id: number;
  lemma: string;
  frequency: number;
  rank: number;
  in_study_set: boolean;
  is_hidden: boolean;
  reason: string;
};

export async function getSuspiciousLemmas(
  bookId: number,
  includeHidden = false,
): Promise<SuspiciousLemma[]> {
  const params = includeHidden ? "?include_hidden=true" : "";
  const response = await apiFetch<{ items: SuspiciousLemma[]; total: number }>(
    `/books/${bookId}/suspicious-lemmas${params}`,
    {},
    API_BASE_URL,
  );
  return response.items;
}

export async function bulkHideBookLemmas(
  bookId: number,
  lemmaIds: number[],
  hidden: boolean,
): Promise<BookSummary> {
  return apiFetch<BookSummary>(
    `/books/${bookId}/lemmas/bulk-hide`,
    { method: "POST", body: JSON.stringify({ lemma_ids: lemmaIds, hidden }) },
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

export type BookDefinitionsSummary = {
  needs_refresh_count: number;
  missing_en_count: number;
  missing_zh_count: number;
};

export type DefinitionFillJob = {
  id: number;
  status: string;
  total: number;
  processed: number;
  filled: number;
  failed: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export async function getBooksDefinitionsSummary(): Promise<BookDefinitionsSummary> {
  return apiFetch<BookDefinitionsSummary>("/books/definitions-summary", {}, API_BASE_URL);
}

export async function startBookDefinitionFillJob(): Promise<DefinitionFillJob> {
  return apiFetch<DefinitionFillJob>(
    "/books/fill-definitions",
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function getCurrentBookDefinitionFillJob(): Promise<DefinitionFillJob | null> {
  return apiFetch<DefinitionFillJob | null>(
    "/books/fill-definitions/current",
    {},
    API_BASE_URL,
  );
}

export async function cancelBookDefinitionFillJob(jobId: number): Promise<DefinitionFillJob> {
  return apiFetch<DefinitionFillJob>(
    `/books/fill-definitions/${jobId}/cancel`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export type PlaceholderLemma = {
  id: number;
  book_id: number;
  book_title: string;
  lemma: string;
  frequency: number;
  in_study_set: boolean;
  is_hidden: boolean;
};

export async function getPlaceholderLemmas(
  jobId?: number,
  includeHidden = false,
): Promise<PlaceholderLemma[]> {
  const params = new URLSearchParams();
  if (jobId != null) {
    params.set("job_id", String(jobId));
  }
  if (includeHidden) {
    params.set("include_hidden", "true");
  }
  const query = params.toString();
  const response = await apiFetch<{ items: PlaceholderLemma[]; total: number }>(
    `/books/placeholder-lemmas${query ? `?${query}` : ""}`,
    {},
    API_BASE_URL,
  );
  return response.items;
}
