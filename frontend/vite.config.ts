import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

const runtime = globalThis as typeof globalThis & {
  process?: { env?: Record<string, string | undefined> };
};
const apiUrl = runtime.process?.env?.FPL_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig(({ mode }) => {
  // FPL_API_TOKEN from the root .env (the dev server runs in frontend/); the proxy adds it, so it never reaches the browser.
  const token = loadEnv(mode, "..", "FPL_").FPL_API_TOKEN;
  return {
    plugins: [react()],
    server: {
      strictPort: true,
      proxy: {
        "/api": { target: apiUrl, headers: token ? { Authorization: `Bearer ${token}` } : {} },
      },
    },
  };
});
