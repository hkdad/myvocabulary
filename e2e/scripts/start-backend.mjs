import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(__dirname, "../../backend");
const e2eDbPath = path.resolve(__dirname, "../.e2e-myvocabulary.db");
const isWin = process.platform === "win32";
const venvBin = path.join(backendDir, isWin ? ".venv/Scripts" : ".venv/bin");
const ext = isWin ? ".exe" : "";

function bin(name) {
  return path.join(venvBin, `${name}${ext}`);
}

function run(name, args, env = process.env) {
  return new Promise((resolve, reject) => {
    const child = spawn(bin(name), args, {
      cwd: backendDir,
      stdio: "inherit",
      shell: isWin,
      env,
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(`${name} exited with code ${code}`));
    });
  });
}

async function main() {
  if (fs.existsSync(e2eDbPath)) {
    fs.rmSync(e2eDbPath);
  }

  const env = {
    ...process.env,
    APP_ENV: "test",
    E2E_SKIP_CATALOG: "1",
    DATABASE_URL: `sqlite+aiosqlite:///${e2eDbPath.replace(/\\/g, "/")}`,
    PYTHONPATH: backendDir,
  };

  await run("alembic", ["upgrade", "head"], env);
  await run("python", ["scripts/seed.py"], env);
  await run("python", [path.resolve(__dirname, "seed-clear-zh-fixture.py")], env);

  const port = process.env.E2E_BACKEND_PORT ?? "8799";
  const uvicorn = spawn(
    bin("uvicorn"),
    ["app.main:app", "--host", "127.0.0.1", "--port", port, "--ws", "none"],
    {
      cwd: backendDir,
      stdio: "inherit",
      shell: isWin,
      env,
    },
  );

  uvicorn.on("error", (error) => {
    console.error(error);
    process.exit(1);
  });

  uvicorn.on("close", (code) => process.exit(code ?? 0));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
