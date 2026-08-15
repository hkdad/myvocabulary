export const DEFAULT_LEARNER_EMOJI = "🌟";

export const LEARNER_EMOJI_OPTIONS = [
  "🌟",
  "🌸",
  "🚀",
  "🦊",
  "🐱",
  "🐶",
  "🦄",
  "🦁",
  "🐼",
  "🦋",
  "🐸",
  "🍎",
  "⚽",
  "🏀",
  "🎨",
  "🎮",
  "📚",
  "🎸",
  "🌈",
  "💛",
] as const;

export function learnerEmoji(learner: { emoji?: string | null; display_name?: string }): string {
  if (learner.emoji?.trim()) {
    return learner.emoji.trim();
  }
  return DEFAULT_LEARNER_EMOJI;
}
