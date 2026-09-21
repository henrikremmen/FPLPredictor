import { defineConfig, devices } from "@playwright/test";

const apiPort = process.env.FPL_API_PORT ?? "8000";
const uiPort = process.env.FPL_UI_PORT ?? "5173";

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${uiPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `../.venv/bin/python -m uvicorn api:app --app-dir ../src --host 127.0.0.1 --port ${apiPort}`,
      url: `http://127.0.0.1:${apiPort}/api/health`,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: `npm exec -- vite --host 127.0.0.1 --port ${uiPort}`,
      url: `http://127.0.0.1:${uiPort}`,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
