import { useEffect, useState } from "react";

import { getLoopProgress, type LoopProgress } from "../api/loop";
import { inProgressCount } from "../lib/strengthStyles";
import StrengthProgressBar from "./quest/StrengthProgressBar";

type Props = {
  englishLevel: string;
};

export default function LevelProgressCard({ englishLevel }: Props) {
  const [progress, setProgress] = useState<LoopProgress | null>(null);

  useEffect(() => {
    void getLoopProgress()
      .then(setProgress)
      .catch(() => setProgress(null));
  }, []);

  if (!progress || progress.bank_at_level <= 0) {
    return null;
  }

  const familiarOrMastered = progress.familiar_count + progress.mastered_count;
  const inProgress = inProgressCount({
    bank_total: progress.bank_at_level,
    learning: progress.learning_count,
    familiar: progress.familiar_count,
    mastered: progress.mastered_count,
  });
  const breadthPct = Math.round((familiarOrMastered / progress.bank_at_level) * 100);
  const almostReady = breadthPct >= 70 && progress.mastered_count >= 5;

  return (
    <section className="warm-card bg-gradient-to-br from-blue-50/90 to-indigo-50/90 p-5">
      <div className="flex items-start gap-3">
        <span className="text-3xl">📈</span>
        <div className="flex-1">
          <h2 className="text-lg font-extrabold text-warm-brown">
            Level {englishLevel} progress
          </h2>
          <p className="mt-1 text-sm text-warm-body">
            <strong>{inProgress}</strong> of <strong>{progress.bank_at_level}</strong>{" "}
            {englishLevel} words in progress — <strong>{progress.mastered_count}</strong> mastered
          </p>

          <div className="mt-3">
            <StrengthProgressBar
              counts={{
                bank_total: progress.bank_at_level,
                learning: progress.learning_count,
                familiar: progress.familiar_count,
                mastered: progress.mastered_count,
              }}
              ariaLabel={`Level ${englishLevel} progress`}
            />
          </div>

          {almostReady && (
            <p className="mt-3 text-sm font-semibold text-green-700">
              Almost ready for the next level — keep going! 🌟
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
