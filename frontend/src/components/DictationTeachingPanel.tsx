import { useEffect, useRef, useState } from "react";

import { apiFetchBlob } from "../api/client";
import { API_BASE_URL } from "../lib/constants";

type DictationTeachingPanelProps = {
  word: string;
  syllables: string[];
  onContinue: () => void;
  continueLabel: string;
};

export default function DictationTeachingPanel({
  word,
  syllables,
  onContinue,
  continueLabel,
}: DictationTeachingPanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setPlaying(false);
    setReady(false);
    setError(null);

    async function loadAudio() {
      try {
        // Load by the revealed word — not session "current" audio, which breaks after give-up.
        const blob = await apiFetchBlob(
          `/dictionary/words/${encodeURIComponent(word)}/audio?slow=true`,
          API_BASE_URL,
        );
        if (cancelled) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        if (audioRef.current) {
          audioRef.current.src = objectUrl;
          setReady(true);
        }
      } catch {
        if (!cancelled) {
          setError("Could not load slow audio");
        }
      }
    }

    if (word) {
      void loadAudio();
    }

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [word]);

  async function handleSlowPlay() {
    const audio = audioRef.current;
    if (!audio || !ready) {
      return;
    }
    setError(null);
    try {
      audio.currentTime = 0;
      await audio.play();
      setPlaying(true);
    } catch {
      setError("Could not play audio");
      setPlaying(false);
    }
  }

  return (
    <section className="warm-card flex flex-col items-center gap-5 bg-gradient-to-br from-rose-50/90 to-amber-50/90 p-6 text-center">
      <p className="flex items-center gap-2 text-sm font-extrabold text-warm-error">
        <span aria-hidden>💡</span>
        Learn the correct spelling
      </p>

      <h2 className="text-4xl font-extrabold tracking-tight text-warm-brown">{word}</h2>

      <div className="flex flex-wrap items-center justify-center gap-2">
        {syllables.map((syllable, index) => (
          <span key={`${syllable}-${index}`} className="flex items-center gap-2">
            <span className="rounded-xl border-2 border-warm-pink-border bg-white px-4 py-2 text-xl font-extrabold text-warm-brown">
              {syllable}
            </span>
            {index < syllables.length - 1 && (
              <span className="text-lg font-bold text-warm-pink">·</span>
            )}
          </span>
        ))}
      </div>

      <audio
        ref={audioRef}
        preload="auto"
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />
      <button
        type="button"
        onClick={() => void handleSlowPlay()}
        disabled={!ready || playing}
        className="inline-flex items-center gap-2 rounded-full border-2 border-warm-pink-border bg-white px-5 py-2 text-sm font-extrabold text-warm-error shadow-sm transition hover:bg-rose-50 disabled:opacity-50"
      >
        <span aria-hidden>{playing ? "🔈" : "🔊"}</span>
        Slow playback
      </button>
      {error && <p className="text-sm text-red-700">{error}</p>}

      <button type="button" onClick={onContinue} className="warm-btn warm-btn-primary w-full sm:w-auto">
        {continueLabel}
      </button>
    </section>
  );
}
