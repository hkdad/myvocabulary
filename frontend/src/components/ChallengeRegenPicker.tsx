import { useEffect, useRef, useState } from "react";

import {
  getChallengeSourceOptions,
  regenerateDailyMix,
  type ChallengeSourceOptions,
  type DailyMix,
  type RegenerateDailyMixRequest,
} from "../api/loop";

type Props = {
  disabled?: boolean;
  onRegenerated: (mix: DailyMix) => void;
};

export default function ChallengeRegenPicker({ disabled = false, onRegenerated }: Props) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ChallengeSourceOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"random" | "category" | "list">("random");
  const [category, setCategory] = useState("");
  const [listId, setListId] = useState<number | "">("");
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    void getChallengeSourceOptions()
      .then((data) => {
        setOptions(data);
        setCategory((current) => current || data.categories[0]?.name || "");
        setListId((current) =>
          current === "" && data.my_lists[0] ? data.my_lists[0].id : current,
        );
      })
      .catch((err: Error) => setError(err.message));
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node;
      if (panelRef.current && !panelRef.current.contains(target)) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open]);

  async function handleConfirm() {
    if (disabled || loading) {
      return;
    }
    if (options && !options.can_regenerate) {
      setError("Today's challenge is already complete.");
      return;
    }
    const body: RegenerateDailyMixRequest =
      mode === "category"
        ? { mode, category }
        : mode === "list"
          ? { mode, word_list_id: typeof listId === "number" ? listId : undefined }
          : { mode: "random" };

    if (mode === "category" && !category.trim()) {
      setError("Pick a category");
      return;
    }
    if (mode === "list" && typeof listId !== "number") {
      setError("Pick one of your lists");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const mix = await regenerateDailyMix(body);
      setOpen(false);
      onRegenerated(mix);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rebuild challenge");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        className="warm-btn warm-btn-ghost text-sm"
        disabled={disabled || loading}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        Change words
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Rebuild daily challenge"
          className="fixed inset-x-4 bottom-4 z-30 rounded-2xl border border-warm-border bg-white p-4 shadow-lg sm:absolute sm:inset-auto sm:right-0 sm:bottom-auto sm:mt-2 sm:w-72"
        >
          <p className="text-sm font-extrabold text-warm-brown">New daily mix</p>
          <p className="mt-1 text-xs font-semibold text-warm-muted">
            Rebuilds today&apos;s words. Progress so far today resets. Up to 5 rebuilds per day.
          </p>

          <div className="mt-3 flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm font-semibold text-warm-body">
              <input
                type="radio"
                name="regen-mode"
                checked={mode === "random"}
                onChange={() => setMode("random")}
              />
              Total random
            </label>
            <label className="flex items-center gap-2 text-sm font-semibold text-warm-body">
              <input
                type="radio"
                name="regen-mode"
                checked={mode === "category"}
                onChange={() => setMode("category")}
              />
              Category at my level
            </label>
            {mode === "category" && (
              <select
                className="warm-input text-sm"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                disabled={!options?.categories.length}
              >
                {(options?.categories ?? []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} ({item.word_count})
                  </option>
                ))}
              </select>
            )}
            <label className="flex items-center gap-2 text-sm font-semibold text-warm-body">
              <input
                type="radio"
                name="regen-mode"
                checked={mode === "list"}
                onChange={() => setMode("list")}
              />
              My word list
            </label>
            {mode === "list" && (
              <select
                className="warm-input text-sm"
                value={listId === "" ? "" : String(listId)}
                onChange={(event) =>
                  setListId(event.target.value ? Number(event.target.value) : "")
                }
                disabled={!options?.my_lists.length}
              >
                {(options?.my_lists ?? []).length === 0 ? (
                  <option value="">No lists yet</option>
                ) : (
                  options?.my_lists.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} ({item.item_count})
                    </option>
                  ))
                )}
              </select>
            )}
          </div>

          {error && <p className="mt-2 text-xs font-semibold text-red-700">{error}</p>}

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className="warm-btn warm-btn-primary flex-1 text-sm"
              disabled={loading || (options != null && !options.can_regenerate)}
              onClick={() => void handleConfirm()}
            >
              {loading ? "Rebuilding…" : "Rebuild"}
            </button>
            <button
              type="button"
              className="warm-btn warm-btn-secondary text-sm"
              disabled={loading}
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
