/** CEFR bands supported for learner profiles and word-bank matching. */
export const ENGLISH_LEVELS = ["PRE-A1", "A1", "A2", "B1", "B2", "C1", "C2"] as const;

export type EnglishLevel = (typeof ENGLISH_LEVELS)[number];
