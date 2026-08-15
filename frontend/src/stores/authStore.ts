import { create } from "zustand";

import { apiFetch, configureApiAuth, setApiAccessToken } from "../api/client";
import { API_BASE_URL } from "../lib/constants";

export type LearnerProfile = {
  id: number;
  display_name: string;
  age: number;
  english_level: string;
  ui_mode: "kid" | "teen";
  emoji: string;
  avatar_url: string | null;
  daily_practice_goal: number;
};

export type AuthUser = {
  id: number;
  username: string;
  role: "parent" | "learner";
  learner: LearnerProfile | null;
};

type AuthState = {
  user: AuthUser | null;
  accessToken: string | null;
  initialized: boolean;
  setAccessToken: (token: string | null) => void;
  setUser: (user: AuthUser | null) => void;
  clearAuth: () => void;
  login: (username: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  restoreSession: () => Promise<AuthUser | null>;
  refreshProfile: () => Promise<AuthUser | null>;
};

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  initialized: false,
  setAccessToken: (token) => {
    setApiAccessToken(token);
    set({ accessToken: token });
  },
  setUser: (user) => {
    if (user?.learner?.ui_mode) {
      document.documentElement.dataset.uiMode = user.learner.ui_mode;
    } else {
      delete document.documentElement.dataset.uiMode;
    }
    set({ user });
  },
  clearAuth: () => {
    delete document.documentElement.dataset.uiMode;
    setApiAccessToken(null);
    set({ user: null, accessToken: null });
  },
  login: async (username, password) => {
    const tokenPayload = await apiFetch<{ access_token: string }>(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify({ username, password }),
      },
      API_BASE_URL,
    );
    get().setAccessToken(tokenPayload.access_token);
    const user = await apiFetch<AuthUser>("/auth/me", {}, API_BASE_URL);
    get().setUser(user);
    return user;
  },
  logout: async () => {
    try {
      await apiFetch<void>("/auth/logout", { method: "POST" }, API_BASE_URL);
    } finally {
      get().clearAuth();
    }
  },
  restoreSession: async () => {
    try {
      const tokenPayload = await apiFetch<{ access_token: string }>(
        "/auth/refresh",
        { method: "POST" },
        API_BASE_URL,
      );
      get().setAccessToken(tokenPayload.access_token);
      const user = await apiFetch<AuthUser>("/auth/me", {}, API_BASE_URL);
      get().setUser(user);
      return user;
    } catch {
      get().clearAuth();
      return null;
    } finally {
      set({ initialized: true });
    }
  },
  refreshProfile: async () => {
    if (!get().accessToken) {
      return null;
    }
    try {
      const user = await apiFetch<AuthUser>("/auth/me", {}, API_BASE_URL);
      get().setUser(user);
      return user;
    } catch {
      return null;
    }
  },
}));

configureApiAuth({
  getAccessToken: () => useAuthStore.getState().accessToken,
  setAccessToken: (token) => useAuthStore.getState().setAccessToken(token),
  clearAuth: () => useAuthStore.getState().clearAuth(),
});
