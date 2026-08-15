import { apiFetch } from "./client";
import { API_BASE_URL } from "../lib/constants";

export type LoginPick = {
  label: string;
  emoji: string;
  role: "parent" | "learner";
};

export async function getLoginPicks(): Promise<LoginPick[]> {
  return apiFetch<LoginPick[]>("/auth/login-picks", {}, API_BASE_URL);
}
