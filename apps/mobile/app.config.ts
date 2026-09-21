import type { ExpoConfig, ConfigContext } from "expo/config";

/**
 * Bundle identifier: nb.fplmodell.app (documented in README.md and
 * docs/mobile/app-store-checklist.md). This is a placeholder reverse-DNS id
 * for an app that has no Apple Developer account yet — change it here (and
 * nowhere else) before the first EAS build if you register a different one.
 */
const BUNDLE_ID = "nb.fplmodell.app";

const APP_ENV = process.env.APP_ENV ?? "development";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: APP_ENV === "production" ? "FPL Modell" : `FPL Modell (${APP_ENV})`,
  slug: "fpl-modell",
  scheme: "fplmodell",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/icon.png",
  userInterfaceStyle: "dark",
  ios: {
    bundleIdentifier: BUNDLE_ID,
    supportsTablet: true,
    infoPlist: {
      // The app is read-only against the public FPL API and never logs in;
      // no App Tracking Transparency prompt is needed because nothing is
      // tracked across apps/websites. See docs/mobile/app-privacy-answers.md.
      ITSAppUsesNonExemptEncryption: false,
    },
  },
  android: {
    package: BUNDLE_ID,
    adaptiveIcon: {
      backgroundColor: "#0B0F14",
      foregroundImage: "./assets/android-icon-foreground.png",
      backgroundImage: "./assets/android-icon-background.png",
      monochromeImage: "./assets/android-icon-monochrome.png",
    },
    predictiveBackGestureEnabled: false,
  },
  web: {
    favicon: "./assets/favicon.png",
    bundler: "metro",
  },
  plugins: [
    "expo-router",
    [
      "expo-splash-screen",
      {
        image: "./assets/splash-icon.png",
        resizeMode: "contain",
        backgroundColor: "#0B0F14",
      },
    ],
    [
      "expo-system-ui",
      {
        userInterfaceStyle: "dark",
      },
    ],
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    // Read by src/lib/env.ts. EXPO_PUBLIC_API_URL (set in .env or an EAS
    // profile's "env") always wins; this is only the local-dev fallback.
    apiUrlFallback: "http://127.0.0.1:8000",
    eas: {
      // Placeholder until `eas init` links this app to a real EAS project.
      // See docs/mobile/app-store-checklist.md.
      projectId: "00000000-0000-0000-0000-000000000000",
    },
  },
});
