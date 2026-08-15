type PlaySoundButtonProps = {
  playing: boolean;
  ready: boolean;
  onPlay: () => void;
  error?: string | null;
  size?: "sm" | "md";
};

export default function PlaySoundButton({
  playing,
  ready,
  onPlay,
  error,
  size = "md",
}: PlaySoundButtonProps) {
  const dimension = size === "sm" ? "h-10 w-10 text-lg" : "h-11 w-11 text-xl";

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        aria-label={playing ? "Playing pronunciation" : "Play pronunciation"}
        onClick={onPlay}
        disabled={playing || !ready}
        className={`flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-orange-400 to-amber-500 text-white shadow-md transition hover:scale-105 hover:shadow-lg disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:scale-100 ${dimension}`}
      >
        {playing ? "🔈" : ready ? "🔊" : "…"}
      </button>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </div>
  );
}
