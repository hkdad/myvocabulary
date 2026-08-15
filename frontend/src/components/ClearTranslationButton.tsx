import { useState, type MouseEvent } from "react";

import { clearZhHant } from "../api/dictionary";

type ClearTranslationButtonProps = {
  entryId: number;
  onCleared?: () => void;
  disabled?: boolean;
  compact?: boolean;
};

export default function ClearTranslationButton({
  entryId,
  onCleared,
  disabled = false,
  compact = false,
}: ClearTranslationButtonProps) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function handleClick(event: MouseEvent<HTMLButtonElement>) {
    event.stopPropagation();
    event.preventDefault();
    if (loading || disabled) {
      return;
    }
    setLoading(true);
    setMessage(null);
    try {
      await clearZhHant(entryId);
      onCleared?.();
      setMessage("Cleared. We'll translate again next time.");
    } catch {
      setMessage("Could not clear translation. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <span className={compact ? "inline-block" : "block"}>
      <button
        type="button"
        onClick={(event) => void handleClick(event)}
        disabled={disabled || loading}
        className={`font-semibold text-warm-muted underline-offset-2 hover:text-warm-coral hover:underline disabled:opacity-50 ${
          compact ? "text-xs" : "text-sm"
        }`}
      >
        {loading ? "Clearing…" : "Clear translation"}
      </button>
      {message && (
        <span className={`text-warm-muted ${compact ? "text-xs" : "text-sm"}`}>{message}</span>
      )}
    </span>
  );
}
