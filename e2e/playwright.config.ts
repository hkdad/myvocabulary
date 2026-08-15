import { defineConfig } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? 5174);
const backendPort = process.env.E2E_BACKEND_PORT ?? "8799";
const backendUrl = process.env.E2E_BACKEND_URL ?? `http://127.0.0.1:${backendPort}`;
const frontendUrl = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: frontendUrl,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "node scripts/start-backend.mjs",
      url: `${backendUrl}/health`,
      reuseExistingServer: false,
      timeout: 180_000,
      env: {
        E2E_BACKEND_PORT: backendPort,
      },
    },
    {
      command: "node scripts/start-frontend.mjs",
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        E2E_PORT: String(port),
        VITE_DEV_API_PROXY: backendUrl,
      },
    },
  ],
});
