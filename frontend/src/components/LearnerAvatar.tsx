import { learnerEmoji } from "../lib/learnerEmoji";

type LearnerLike = {
  emoji?: string | null;
  display_name?: string;
};

type LearnerAvatarProps = {
  learner?: LearnerLike | null;
  emoji?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
};

const SIZE_CLASSES = {
  sm: "h-10 w-10 text-xl",
  md: "h-14 w-14 text-3xl",
  lg: "h-16 w-16 text-4xl",
} as const;

export default function LearnerAvatar({
  learner,
  emoji,
  size = "md",
  className = "",
}: LearnerAvatarProps) {
  const icon = emoji ?? (learner ? learnerEmoji(learner) : "🌟");

  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-2xl bg-orange-50 shadow-sm ${SIZE_CLASSES[size]} ${className}`}
      aria-hidden
    >
      {icon}
    </span>
  );
}
