import { apiFetch, apiFetchForm, apiFetchFormWithProgress } from "./client";
import { API_BASE_URL } from "../lib/constants";
import type { SrsCard } from "./reviews";

export type LoopProgress = {
  learning_count: number;
  familiar_count: number;
  mastered_count: number;
  due_count: number;
  new_released_today: number;
  daily_new_goal: number;
  new_remaining_today: number;
  new_released_this_week?: number;
  weekly_new_target?: number;
  bank_total: number;
  bank_at_level: number;
  daily_challenge_completed: boolean;
  daily_challenge_srs_completed?: boolean;
  daily_challenge_dictation_completed?: boolean;
};

export type DailyMix = {
  cards: SrsCard[];
  new_count: number;
  retention_count: number;
  learning_retention_count?: number;
  mastered_retention_count?: number;
  daily_new_goal: number;
  daily_learning_retention_goal: number;
  daily_mastered_retention_goal: number;
  daily_retention_goal: number;
  new_released_today: number;
  completed_today: boolean;
  srs_completed?: boolean;
  dictation_completed?: boolean;
  suggested: boolean;
  source_kind?: string | null;
  source_ref?: string | null;
  can_regenerate?: boolean;
  book_title?: string | null;
  study_progress_percent?: number | null;
  page_coverage_percent?: number | null;
  ready_to_read?: boolean | null;
  book_study_total?: number | null;
  book_learning_count?: number | null;
  book_familiar_count?: number | null;
  book_mastered_count?: number | null;
};

export type ChallengeSourceOptions = {
  english_level: string;
  categories: { name: string; word_count: number }[];
  my_lists: { id: number; name: string; item_count: number }[];
  can_regenerate: boolean;
  source_kind: string;
  source_ref: string | null;
};

export type RegenerateDailyMixRequest = {
  mode: "random" | "category" | "list";
  category?: string;
  word_list_id?: number;
};

export type DailyChallengePhase = {
  srs_completed: boolean;
  dictation_completed: boolean;
  completed: boolean;
  completed_at: string | null;
};

export type WordBankSummary = {
  bank_id: number | null;
  name: string;
  total_items: number;
  placeholder_count: number;
  by_level: Record<string, number>;
  by_category: Record<string, number>;
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

export type WordBankImportResult = {
  bank_id: number;
  created: number;
  updated: number;
  skipped: number;
  placeholder_count: number;
  needs_level_count: number;
  invalid_category_count: number;
  total_items: number;
  errors: string[];
};

export async function getLoopToday(): Promise<DailyMix> {
  return apiFetch<DailyMix>("/loop/today", {}, API_BASE_URL);
}

export async function getChallengeSourceOptions(): Promise<ChallengeSourceOptions> {
  return apiFetch<ChallengeSourceOptions>("/loop/today/options", {}, API_BASE_URL);
}

export async function regenerateDailyMix(
  body: RegenerateDailyMixRequest,
): Promise<DailyMix> {
  return apiFetch<DailyMix>(
    "/loop/today/regenerate",
    { method: "POST", body: JSON.stringify(body) },
    API_BASE_URL,
  );
}

export async function completeDailyChallengeSrs(): Promise<DailyChallengePhase> {
  return apiFetch<DailyChallengePhase>("/loop/today/srs-complete", { method: "POST" }, API_BASE_URL);
}

export async function completeDailyChallenge(): Promise<{
  completed: boolean;
  completed_at: string | null;
  srs_completed?: boolean;
  dictation_completed?: boolean;
}> {
  return apiFetch("/loop/today/complete", { method: "POST" }, API_BASE_URL);
}

export async function getLoopProgress(): Promise<LoopProgress> {
  return apiFetch<LoopProgress>("/loop/progress", {}, API_BASE_URL);
}

export async function getWordBankSummary(): Promise<WordBankSummary> {
  return apiFetch<WordBankSummary>("/word-bank", {}, API_BASE_URL);
}

export type WordBankItem = {
  id: number;
  word: string;
  definition: string;
  part_of_speech: string | null;
  phonetic: string | null;
  has_audio: boolean;
  level: string | null;
  categories: string[];
  sort_order: number;
};

export type WordBankItemsPage = {
  items: WordBankItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export const BANK_CATEGORIES = [
  "Daily life",
  "School",
  "Food",
  "Animals / nature",
  "Science",
  "Feelings / people",
  "Places / travel",
  "General",
] as const;

const CEFR_LEVEL_ORDER = ["A1", "A2", "B1", "B2"] as const;

/** Levels and book names present in the summary, sorted A1 → B2 then other keys. */
export function bankLevelsFromSummary(byLevel: Record<string, number>): string[] {
  return Object.entries(byLevel)
    .filter(([, count]) => count > 0)
    .map(([level]) => level)
    .sort((a, b) => {
      const aIndex = CEFR_LEVEL_ORDER.indexOf(a as (typeof CEFR_LEVEL_ORDER)[number]);
      const bIndex = CEFR_LEVEL_ORDER.indexOf(b as (typeof CEFR_LEVEL_ORDER)[number]);
      if (aIndex === -1 && bIndex === -1) {
        return a.localeCompare(b);
      }
      if (aIndex === -1) {
        return 1;
      }
      if (bIndex === -1) {
        return -1;
      }
      return aIndex - bIndex;
    });
}

/** Categories present in the bank summary, sorted A → Z. */
export function bankCategoriesFromSummary(byCategory: Record<string, number>): string[] {
  return Object.entries(byCategory)
    .filter(([, count]) => count > 0)
    .map(([category]) => category)
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

export async function getWordBankItems(params: {
  level?: string;
  category?: string;
  q?: string;
  page?: number;
  page_size?: number;
  placeholders_only?: boolean;
}): Promise<WordBankItemsPage> {
  const search = new URLSearchParams();
  if (params.level) search.set("level", params.level);
  if (params.category) search.set("category", params.category);
  if (params.q) search.set("q", params.q);
  if (params.placeholders_only) search.set("placeholders_only", "true");
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 50));
  const query = search.toString();
  return apiFetch<WordBankItemsPage>(`/word-bank/items?${query}`, {}, API_BASE_URL);
}

export async function startDefinitionFillJob(): Promise<DefinitionFillJob> {
  return apiFetch<DefinitionFillJob>(
    "/word-bank/fill-definitions",
    { method: "POST" },
    API_BASE_URL,
  );
}

export async function getCurrentDefinitionFillJob(): Promise<DefinitionFillJob | null> {
  return apiFetch<DefinitionFillJob | null>(
    "/word-bank/fill-definitions/current",
    {},
    API_BASE_URL,
  );
}

export async function cancelDefinitionFillJob(jobId: number): Promise<DefinitionFillJob> {
  return apiFetch<DefinitionFillJob>(
    `/word-bank/fill-definitions/${jobId}/cancel`,
    { method: "POST" },
    API_BASE_URL,
  );
}

export type ThemePackQuest = {
  slug: string;
  category: string;
  emoji: string;
  title: string;
  badge_type: string;
  total_words: number;
  started_words: number;
  strong_words: number;
  progress_percent: number;
  completed: boolean;
};

export type MilestoneQuest = {
  tier: string;
  label: string;
  badge_type: string;
  current: number;
  target: number;
  earned: boolean;
  progress_percent: number;
};

export type QuestStrengthSummary = {
  bank_total: number;
  released: number;
  learning: number;
  familiar: number;
  mastered: number;
};

export type LevelQuest = {
  level: string;
  is_current: boolean;
  bank_total: number;
  released: number;
  learning: number;
  familiar: number;
  mastered: number;
  readiness_score: number;
  milestones: MilestoneQuest[];
};

export const THEME_PACK_LEVEL_OPTIONS = [
  "Overall",
  "PRE-A1",
  "A1",
  "A2",
  "B1",
  "B2",
  "C1",
  "C2",
] as const;

export type ThemePackLevelFilter = (typeof THEME_PACK_LEVEL_OPTIONS)[number];

export function themePackWordsUrl(
  pack: ThemePackQuest,
  packLevel: ThemePackLevelFilter,
): string {
  const params = new URLSearchParams();
  params.set("category", pack.category);
  if (packLevel !== "Overall") {
    params.set("level", packLevel);
  }
  return `/app/words?${params.toString()}`;
}

export type QuestsSummary = {
  english_level: string;
  overall: QuestStrengthSummary;
  levels: LevelQuest[];
  packs: ThemePackQuest[];
  packs_by_level: Record<string, ThemePackQuest[]>;
  earned_pack_badges: number;
  earned_milestone_badges: number;
  total_pack_quests: number;
  completed_pack_quests: number;
  newly_earned_badges: string[];
};

export async function getQuests(): Promise<QuestsSummary> {
  return apiFetch<QuestsSummary>("/loop/quests", {}, API_BASE_URL);
}

export async function getLearnerQuests(learnerId: number): Promise<QuestsSummary> {
  return apiFetch<QuestsSummary>(`/learners/${learnerId}/quests`, {}, API_BASE_URL);
}

export type LearnerWordStrength = "learning" | "familiar" | "mastered";

export type LearnerWordItem = {
  card_id: number;
  word: string;
  definition: string;
  level: string | null;
  levels: string[];
  categories: string[];
  strength: LearnerWordStrength | "new";
  distinct_review_days: number;
  released_at: string | null;
  interval_days: number;
  repetitions: number;
  state: string;
};

export type LearnerWordsPage = {
  items: LearnerWordItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  by_level: Record<string, number>;
  by_bank_level: Record<string, number>;
  by_book: Record<string, number>;
  by_category: Record<string, number>;
  by_strength: Record<string, number>;
};

export async function getLearnerWords(params: {
  level?: string;
  category?: string;
  q?: string;
  strength?: string;
  page?: number;
  page_size?: number;
}): Promise<LearnerWordsPage> {
  const search = new URLSearchParams();
  if (params.level) search.set("level", params.level);
  if (params.category) search.set("category", params.category);
  if (params.q) search.set("q", params.q);
  if (params.strength) search.set("strength", params.strength);
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 50));
  return apiFetch<LearnerWordsPage>(`/loop/words?${search.toString()}`, {}, API_BASE_URL);
}

export async function importWordBank(file: File): Promise<WordBankImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetchForm<WordBankImportResult>("/word-bank/import", formData, API_BASE_URL);
}

export async function importWordBankWithProgress(
  file: File,
  onProgress: (percent: number) => void,
): Promise<WordBankImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetchFormWithProgress<WordBankImportResult>(
    "/word-bank/import",
    formData,
    API_BASE_URL,
    onProgress,
  );
}

export type WordBankDeleteResult = {
  deleted_items: number;
  deleted_cards: number;
};

export async function deleteWordBank(): Promise<WordBankDeleteResult> {
  return apiFetch<WordBankDeleteResult>("/word-bank", { method: "DELETE" }, API_BASE_URL);
}
