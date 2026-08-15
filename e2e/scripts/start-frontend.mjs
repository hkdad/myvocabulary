import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "../../frontend");
const port = process.env.E2E_PORT ?? "5174";
const isWin = process.platform === "win32";

const child = spawn("npx", ["pnpm", "dev", "--host", "127.0.0.1", "--port", port], {
  cwd: frontendDir,
  stdio: "inherit",
  shell: true,
  env: {
    ...process.env,
    VITE_API_BASE_URL: "/api/v1",
    VITE_DEV_API_PROXY:
      process.env.VITE_DEV_API_PROXY ?? `http://127.0.0.1:${process.env.E2E_BACKEND_PORT ?? "8799"}`,
  },
});

child.on("error", (error) => {
  console.error(error);
  process.exit(1);
});

child.on("close", (code) => process.exit(code ?? 0));
