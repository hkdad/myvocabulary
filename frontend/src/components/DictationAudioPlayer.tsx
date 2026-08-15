import { useEffect, useRef, useState } from "react";

import { fetchDictationAudio } from "../api/dictation";
import PlaySoundButton from "./PlaySoundButton";

type DictationAudioPlayerProps = {
  sessionId: number;
  wordIndex: number;
  autoPlay?: boolean;
  size?: "sm" | "md";
};

function isLikelyAudioBlob(blob: Blob): boolean {
  if (blob.size <= 0) {
    return false;
  }
  // Some browsers leave type empty for blob() even when Content-Type was audio/mpeg.
  return (
    blob.type === "" ||
    blob.type.startsWith("audio/") ||
    blob.type === "application/octet-stream"
  );
}

export default function DictationAudioPlayer({
  sessionId,
  wordIndex,
  autoPlay = false,
  size = "md",
}: DictationAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const requestIdRef = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const requestId = ++requestIdRef.current;

    setPlaying(false);
    setReady(false);
    setError(null);

    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }

    async function loadAudio() {
      try {
        const blob = await fetchDictationAudio(sessionId, { wordIndex });
        if (requestId !== requestIdRef.current || !audioRef.current) {
          return;
        }
        if (!isLikelyAudioBlob(blob)) {
          setError("Could not load audio");
          return;
        }

        const objectUrl = URL.createObjectURL(blob);
        objectUrlRef.current = objectUrl;

        const audio = audioRef.current;
        audio.src = objectUrl;

        const handleReady = async () => {
          if (requestId !== requestIdRef.current) {
            return;
          }
          setReady(true);
          if (autoPlay) {
            try {
              await audio.play();
              if (requestId === requestIdRef.current) {
                setPlaying(true);
              }
            } catch {
              if (requestId === requestIdRef.current) {
                setPlaying(false);
              }
            }
          }
        };

        const handleError = () => {
          if (requestId !== requestIdRef.current) {
            return;
          }
          setError("Could not load audio");
          setReady(false);
        };

        audio.addEventListener("loadeddata", handleReady, { once: true });
        audio.addEventListener("error", handleError, { once: true });
        audio.load();
      } catch {
        if (requestId === requestIdRef.current) {
          setError("Could not load audio");
        }
      }
    }

    void loadAudio();

    return () => {
      requestIdRef.current += 1;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [sessionId, wordIndex, autoPlay]);

  async function handlePlay() {
    const audio = audioRef.current;
    if (!audio || !ready) {
      return;
    }
    setError(null);
    try {
      await audio.play();
      setPlaying(true);
    } catch {
      setError("Could not play audio");
      setPlaying(false);
    }
  }

  return (
    <>
      <audio
        ref={audioRef}
        preload="auto"
        onEnded={() => setPlaying(false)}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />
      <PlaySoundButton
        playing={playing}
        ready={ready}
        onPlay={() => void handlePlay()}
        error={error}
        size={size}
      />
    </>
  );
}
