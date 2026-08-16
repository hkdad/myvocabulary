import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  createLearner,
  deactivateLearner,
  deleteLearner,
  dailyPracticeTotal,
  defaultDailyPractice,
  listLearners,
  resetLearnerPassword,
  updateLearner,
  type LearnerCreateInput,
  type LearnerProfile,
} from "../../api/learners";
import LearnerAvatar from "../../components/LearnerAvatar";
import PageShell from "../../components/PageShell";
import { DEFAULT_LEARNER_EMOJI, LEARNER_EMOJI_OPTIONS } from "../../lib/learnerEmoji";
import { ENGLISH_LEVELS } from "../../lib/englishLevels";

const LEVELS = ENGLISH_LEVELS;

type FormState = {
  username: string;
  password: string;
  display_name: string;
  age: string;
  english_level: string;
  emoji: string;
  daily_new_word_goal: string;
  daily_learning_retention_mix: string;
  daily_mastered_retention_mix: string;
};

function emptyForm(): FormState {
  const practice = defaultDailyPractice("kid");
  return {
    username: "",
    password: "",
    display_name: "",
    age: "10",
    english_level: "A1",
    emoji: DEFAULT_LEARNER_EMOJI,
    daily_new_word_goal: String(practice.daily_new_word_goal),
    daily_learning_retention_mix: String(practice.daily_learning_retention_mix),
    daily_mastered_retention_mix: String(practice.daily_mastered_retention_mix),
  };
}

function formFromLearner(learner: LearnerProfile): FormState {
  return {
    username: learner.username,
    password: "",
    display_name: learner.display_name,
    age: String(learner.age),
    english_level: learner.english_level,
    emoji: learner.emoji || DEFAULT_LEARNER_EMOJI,
    daily_new_word_goal: String(learner.daily_new_word_goal),
    daily_learning_retention_mix: String(learner.daily_learning_retention_mix),
    daily_mastered_retention_mix: String(learner.daily_mastered_retention_mix),
  };
}

export default function LearnersPage() {
  const [learners, setLearners] = useState<LearnerProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<"list" | "add" | "edit">("list");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [resetPasswordId, setResetPasswordId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLearners(await listLearners());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load learners");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function openAdd() {
    setForm(emptyForm());
    setEditingId(null);
    setMode("add");
    setResetPasswordId(null);
  }

  function openEdit(learner: LearnerProfile) {
    setForm(formFromLearner(learner));
    setEditingId(learner.id);
    setMode("edit");
    setResetPasswordId(null);
  }

  function closeForm() {
    setMode("list");
    setEditingId(null);
    setResetPasswordId(null);
    setNewPassword("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const age = Number(form.age);
      const goals = {
        daily_new_word_goal: Number(form.daily_new_word_goal),
        daily_learning_retention_mix: Number(form.daily_learning_retention_mix),
        daily_mastered_retention_mix: Number(form.daily_mastered_retention_mix),
      };
      const payloadBase = {
        display_name: form.display_name.trim(),
        age,
        english_level: form.english_level,
        emoji: form.emoji.trim() || DEFAULT_LEARNER_EMOJI,
        ...goals,
      };
      if (mode === "add") {
        const payload: LearnerCreateInput = {
          username: form.username.trim(),
          password: form.password,
          ...payloadBase,
        };
        await createLearner(payload);
      } else if (editingId != null) {
        const updated = await updateLearner(editingId, payloadBase);
        setLearners((current) =>
          current.map((learner) => (learner.id === updated.id ? updated : learner)),
        );
      }
      if (mode === "add") {
        await load();
      }
      closeForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save learner");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(learner: LearnerProfile) {
    if (
      !window.confirm(
        `Deactivate ${learner.display_name}? They will not be able to log in until reactivated.`,
      )
    ) {
      return;
    }
    setError(null);
    try {
      await deactivateLearner(learner.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not deactivate learner");
    }
  }

  async function handleReactivate(learner: LearnerProfile) {
    setError(null);
    try {
      await updateLearner(learner.id, { is_active: true });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reactivate learner");
    }
  }

  async function handleDelete(learner: LearnerProfile) {
    if (
      !window.confirm(
        `Permanently delete ${learner.display_name}? All progress will be lost. This cannot be undone.`,
      )
    ) {
      return;
    }
    setError(null);
    setDeletingId(learner.id);
    try {
      await deleteLearner(learner.id);
      const updated = await listLearners();
      setLearners(updated);
      if (updated.some((row) => row.id === learner.id)) {
        setError(
          `${learner.display_name} was not removed. Restart the backend, then try again.`,
        );
        return;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete learner");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleResetPassword(learnerId: number) {
    if (!newPassword.trim()) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await resetLearnerPassword(learnerId, newPassword);
      setResetPasswordId(null);
      setNewPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset password");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageShell variant="parent">
      <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 p-6 sm:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-warm-muted">Family roster</p>
            <h1 className="text-3xl font-extrabold text-warm-brown">Your learners</h1>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Add accounts, set daily goals, and manage access.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {mode === "list" && (
              <button type="button" className="warm-btn warm-btn-primary text-sm" onClick={openAdd}>
                Add learner
              </button>
            )}
            <Link to="/parent/dashboard" className="warm-btn warm-btn-secondary text-sm">
              Dashboard
            </Link>
          </div>
        </header>

        {error && (
          <p className="rounded-xl bg-red-50 px-4 py-3 font-semibold text-red-600">{error}</p>
        )}

        {(mode === "add" || mode === "edit") && (
          <section className="warm-card p-6">
            <div className="flex items-center gap-4">
              <LearnerAvatar emoji={form.emoji} size="lg" />
              <div>
                <h2 className="text-lg font-extrabold text-warm-brown">
                  {mode === "add" ? "Add learner" : `Edit ${form.display_name.trim() || "learner"}`}
                </h2>
                <p className="text-sm text-warm-brown-soft">
                  {mode === "add" ? "Create a new account" : "Update profile and daily practice"}
                </p>
              </div>
            </div>
            <form onSubmit={(event) => void handleSubmit(event)} className="mt-4 grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                {mode === "add" && (
                  <>
                    <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                      Username
                      <input
                        className="warm-input"
                        required
                        value={form.username}
                        onChange={(e) => setForm({ ...form, username: e.target.value })}
                      />
                    </label>
                    <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                      Password
                      <input
                        className="warm-input"
                        type="password"
                        required
                        minLength={4}
                        value={form.password}
                        onChange={(e) => setForm({ ...form, password: e.target.value })}
                      />
                    </label>
                  </>
                )}
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  Display name
                  <input
                    className="warm-input"
                    required
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  Age
                  <input
                    className="warm-input"
                    type="number"
                    min={4}
                    max={18}
                    required
                    value={form.age}
                    onChange={(e) => setForm({ ...form, age: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  English level
                  <select
                    className="warm-input"
                    value={form.english_level}
                    onChange={(e) => setForm({ ...form, english_level: e.target.value })}
                  >
                    {LEVELS.map((level) => (
                      <option key={level} value={level}>
                        {level}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div>
                <p className="text-sm font-semibold text-warm-body">Profile icon</p>
                <p className="mt-1 text-sm text-warm-brown-soft">
                  Pick an emoji for {form.display_name.trim() || "this learner"}.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {LEARNER_EMOJI_OPTIONS.map((emoji) => (
                    <button
                      key={emoji}
                      type="button"
                      aria-label={`Use ${emoji} as profile icon`}
                      aria-pressed={form.emoji === emoji}
                      className={`flex h-11 w-11 items-center justify-center rounded-xl text-2xl transition ${
                        form.emoji === emoji
                          ? "bg-orange-100 ring-2 ring-orange-300"
                          : "bg-white/80 hover:bg-orange-50"
                      }`}
                      onClick={() => setForm({ ...form, emoji })}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-extrabold text-warm-brown">Daily practice</h3>
                <p className="mt-1 text-sm text-warm-brown-soft">
                  {Number(form.daily_new_word_goal)} new +{" "}
                  {Number(form.daily_learning_retention_mix)} learning/familiar +{" "}
                  {Number(form.daily_mastered_retention_mix)} mastered — about{" "}
                  {dailyPracticeTotal({
                    daily_new_word_goal: Number(form.daily_new_word_goal),
                    daily_learning_retention_mix: Number(form.daily_learning_retention_mix),
                    daily_mastered_retention_mix: Number(form.daily_mastered_retention_mix),
                  })}{" "}
                  cards per day.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  New words / day
                  <input
                    className="warm-input"
                    type="number"
                    min={1}
                    max={30}
                    required
                    value={form.daily_new_word_goal}
                    onChange={(e) => setForm({ ...form, daily_new_word_goal: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  Learning / familiar retention
                  <input
                    className="warm-input"
                    type="number"
                    min={0}
                    max={10}
                    required
                    value={form.daily_learning_retention_mix}
                    onChange={(e) =>
                      setForm({ ...form, daily_learning_retention_mix: e.target.value })
                    }
                  />
                </label>
                <label className="flex flex-col gap-1 text-sm font-semibold text-warm-body">
                  Mastered retention
                  <input
                    className="warm-input"
                    type="number"
                    min={0}
                    max={10}
                    required
                    value={form.daily_mastered_retention_mix}
                    onChange={(e) =>
                      setForm({ ...form, daily_mastered_retention_mix: e.target.value })
                    }
                  />
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button type="submit" className="warm-btn warm-btn-primary text-sm" disabled={saving}>
                  {saving ? "Saving…" : mode === "add" ? "Create learner" : "Save changes"}
                </button>
                <button
                  type="button"
                  className="warm-btn warm-btn-secondary text-sm"
                  onClick={closeForm}
                  disabled={saving}
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        )}

        {loading ? (
          <p className="text-warm-brown-soft">Loading learners…</p>
        ) : (
          <section className="space-y-3">
            {learners.map((learner) => (
              <article
                key={learner.id}
                className="warm-card flex flex-col gap-4 p-5 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="flex items-start gap-4">
                  <LearnerAvatar learner={learner} size="lg" />
                  <div>
                    <p className="text-lg font-extrabold text-warm-brown">{learner.display_name}</p>
                    <p className="text-sm font-semibold text-warm-brown-soft">
                      @{learner.username} · {learner.english_level} · age {learner.age}
                    </p>
                    <p className="mt-2 text-sm text-warm-body">
                      Daily practice: {learner.daily_new_word_goal} new +{" "}
                      {learner.daily_learning_retention_mix} learning/familiar +{" "}
                      {learner.daily_mastered_retention_mix} mastered (
                      {learner.daily_practice_goal} cards)
                    </p>
                    <span
                      className={`mt-2 inline-block rounded-full px-3 py-1 text-xs font-extrabold ${
                        learner.is_active
                          ? "bg-green-100 text-green-800"
                          : "bg-stone-100 text-stone-500"
                      }`}
                    >
                      {learner.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>
                </div>
                <div className="flex flex-col items-stretch gap-2 sm:items-end">
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="warm-btn warm-btn-secondary text-sm"
                      onClick={() => openEdit(learner)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="warm-btn warm-btn-secondary text-sm"
                      onClick={() => {
                        setResetPasswordId(learner.id);
                        setNewPassword("");
                      }}
                    >
                      Reset password
                    </button>
                  </div>
                  {learner.is_active ? (
                    <button
                      type="button"
                      className="text-sm font-semibold text-red-600"
                      onClick={() => void handleDeactivate(learner)}
                    >
                      Deactivate
                    </button>
                  ) : (
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        className="text-sm font-semibold text-green-700"
                        onClick={() => void handleReactivate(learner)}
                      >
                        Reactivate
                      </button>
                      <button
                        type="button"
                        className="text-sm font-semibold text-red-600 disabled:opacity-50"
                        disabled={deletingId === learner.id}
                        onClick={() => void handleDelete(learner)}
                      >
                        {deletingId === learner.id ? "Deleting…" : "Delete permanently"}
                      </button>
                    </div>
                  )}
                </div>
                {resetPasswordId === learner.id && (
                  <div className="flex w-full flex-wrap items-end gap-2 border-t border-orange-100 pt-4 sm:col-span-2">
                    <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-sm font-semibold text-warm-body">
                      New password
                      <input
                        className="warm-input"
                        type="password"
                        minLength={4}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                      />
                    </label>
                    <button
                      type="button"
                      className="warm-btn warm-btn-primary text-sm"
                      disabled={saving || newPassword.length < 4}
                      onClick={() => void handleResetPassword(learner.id)}
                    >
                      Save password
                    </button>
                    <button
                      type="button"
                      className="warm-btn warm-btn-secondary text-sm"
                      onClick={() => setResetPasswordId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </article>
            ))}
          </section>
        )}

        {!loading && learners.length === 0 && mode === "list" && !error && (
          <div className="warm-card p-8 text-center">
            <p className="font-bold text-warm-brown">No learners yet</p>
            <p className="mt-1 text-sm text-warm-brown-soft">
              Add your first learner to get started.
            </p>
            <button type="button" className="warm-btn warm-btn-primary mt-4 text-sm" onClick={openAdd}>
              Add learner
            </button>
          </div>
        )}
      </main>
    </PageShell>
  );
}
