import Constants from "expo-constants";

/**
 * `EXPO_PUBLIC_*` vars are inlined at build time from `.env` / the active
 * EAS profile's `env` block (see eas.json). The app.config.ts fallback only
 * covers local development when no `.env` has been created yet.
 */
export function apiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv) return fromEnv;
  const fallback = Constants.expoConfig?.extra?.apiUrlFallback;
  return typeof fallback === "string" ? fallback : "http://127.0.0.1:8000";
}
