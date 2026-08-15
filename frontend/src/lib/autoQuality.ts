/** Map a definition pick to SM-2 quality (0–5). */
export function qualityFromDefinitionPick(isCorrect: boolean): number {
  // Wrong → fail / short interval; correct → Good (solid pass without claiming Easy).
  return isCorrect ? 4 : 1;
}

export const AUTO_QUALITY_ADVANCE_MS = 700;
