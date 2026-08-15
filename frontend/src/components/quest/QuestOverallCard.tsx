import type { QuestStrengthSummary } from "../../api/loop";
import { inProgressCount } from "../../lib/strengthStyles";
import StrengthProgressBar from "./StrengthProgressBar";

type Props = {
  overall: QuestStrengthSummary;
};

export default function QuestOverallCard({ overall }: Props) {
  const inProgress = inProgressCount(overall);

  return (
    <section className="warm-card bg-gradient-to-br from-blue-50/90 to-indigo-50/90 p-5">
      <h2 className="text-lg font-extrabold text-warm-brown">Overall progress</h2>
      <p className="mt-1 text-sm text-warm-body">
        All levels · <strong>{inProgress}</strong> words in progress across{" "}
        <strong>{overall.bank_total}</strong> bank words
      </p>
      <div className="mt-3">
        <StrengthProgressBar
          counts={overall}
          ariaLabel={`Overall progress: ${overall.learning} learning, ${overall.familiar} familiar, ${overall.mastered} mastered`}
        />
      </div>
    </section>
  );
}
