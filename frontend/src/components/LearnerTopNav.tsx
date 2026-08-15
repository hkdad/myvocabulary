import { Link } from "react-router-dom";

import { useAuthStore } from "../stores/authStore";

type LearnerTopNavProps = {
  showHome?: boolean;
};

export default function LearnerTopNav({ showHome = true }: LearnerTopNavProps) {
  const logout = useAuthStore((state) => state.logout);

  return (
    <div className="flex shrink-0 items-center gap-2">
      {showHome && (
        <Link to="/app/home" className="warm-btn warm-btn-secondary text-sm">
          Home
        </Link>
      )}
      <button
        type="button"
        onClick={() => void logout()}
        className="warm-btn warm-btn-ghost text-sm"
      >
        👋 Bye
      </button>
    </div>
  );
}
