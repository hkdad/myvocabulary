import { type FormEvent, useEffect, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { getLoginPicks, type LoginPick } from "../api/auth";
import BrandMark from "../components/BrandMark";
import LearnerAvatar from "../components/LearnerAvatar";
import PageShell from "../components/PageShell";
import { useAuthStore } from "../stores/authStore";

const FALLBACK_PICKS: LoginPick[] = [
  { emoji: "👨‍👩‍👧‍👦", label: "Parent", role: "parent" },
  { emoji: "🌸", label: "Mia", role: "learner" },
  { emoji: "🚀", label: "Leo", role: "learner" },
  { emoji: "🐶", label: "Max", role: "learner" },
];

/** Local dev only — not exposed by the login-picks API. */
const DEV_USERNAME_HINTS: Record<string, string> = {
  Parent: "parent",
  Mia: "mia",
  Leo: "leo",
  Max: "max",
};

const IS_DEV = import.meta.env.DEV;

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const initialized = useAuthStore((state) => state.initialized);
  const login = useAuthStore((state) => state.login);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [quickPicks, setQuickPicks] = useState<LoginPick[]>(FALLBACK_PICKS);

  useEffect(() => {
    getLoginPicks()
      .then((picks) => {
        if (picks.length > 0) {
          setQuickPicks(picks);
        }
      })
      .catch(() => {
        // Keep fallback picks when API is unavailable.
      });
  }, []);

  const redirectPath =
    (location.state as { from?: string } | null)?.from ??
    (user?.role === "parent" ? "/parent/dashboard" : "/app/home");

  if (initialized && user) {
    return <Navigate to={redirectPath} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const loggedInUser = await login(username, password);
      navigate(loggedInUser.role === "parent" ? "/parent/dashboard" : "/app/home");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Login failed";
      if (message === "AUTH_INVALID_CREDENTIALS") {
        setError(
          IS_DEV
            ? "Wrong username or password — try mia/mia, leo/leo, max/max, or parent/parent123"
            : "Wrong username or password.",
        );
      } else if (message === "RATE_LIMITED" || message.includes("429")) {
        setError("Too many login attempts — wait a minute and try again.");
      } else {
        setError(message);
      }
    } finally {
      setSubmitting(false);
    }
  }

  function pickAccount(pick: LoginPick) {
    setSelectedLabel(pick.label);
    setError(null);
    if (IS_DEV) {
      const hinted = DEV_USERNAME_HINTS[pick.label];
      if (hinted) {
        setUsername(hinted);
        setPassword(hinted === "parent" ? "parent123" : hinted);
      }
    }
  }

  return (
    <PageShell>
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6 sm:p-8">
        <div className="text-center">
          <div className="mb-6 flex justify-center">
            <BrandMark />
          </div>
          <h1 className="text-2xl font-extrabold text-warm-brown">Who&apos;s learning today?</h1>
          <p className="mt-2 text-warm-brown-soft">Pick your name, then sign in 🎉</p>
        </div>

        <div className="flex flex-wrap justify-center gap-3">
          {quickPicks.map((pick) => (
            <button
              key={`${pick.role}-${pick.label}`}
              type="button"
              onClick={() => pickAccount(pick)}
              className={`warm-card flex min-w-[5.5rem] flex-col items-center gap-2 px-4 py-3 transition ${
                selectedLabel === pick.label ? "ring-2 ring-warm-coral" : "hover:scale-105"
              }`}
            >
              <LearnerAvatar emoji={pick.emoji} size="md" className="bg-white/80 shadow-none" />
              <span className="text-sm font-bold text-warm-brown">{pick.label}</span>
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="warm-card space-y-4 p-6">
          <label className="block text-sm font-bold text-warm-body">
            <span className="mb-1 flex items-center gap-2">
              <span>👤</span> Username
            </span>
            <input
              className="warm-input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="Your username"
              required
            />
          </label>

          <label className="block text-sm font-bold text-warm-body">
            <span className="mb-1 flex items-center gap-2">
              <span>🔑</span> Password
            </span>
            <input
              type="password"
              className="warm-input"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          {error && (
            <p className="rounded-xl bg-red-50 px-3 py-2 text-sm font-semibold text-red-600">
              😅 {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="warm-btn warm-btn-primary w-full py-3 text-lg disabled:opacity-60"
          >
            {submitting ? "Opening the door… 🚪" : "Let's go! 🌟"}
          </button>
        </form>

        <p className="text-center text-sm text-warm-muted">
          Family words, little wins, big smiles 💛
        </p>
      </main>
    </PageShell>
  );
}
