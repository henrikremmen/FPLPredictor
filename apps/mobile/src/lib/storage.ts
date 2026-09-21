import AsyncStorage from "@react-native-async-storage/async-storage";
import { STORAGE_KEYS, type RiskProfile } from "@fplmodell/shared";

export interface StoredPreferences {
  marketPosition: "ALL" | "GK" | "DEF" | "MID" | "FWD";
  marketMaxPrice: number;
}

export const DEFAULT_PREFERENCES: StoredPreferences = {
  marketPosition: "ALL",
  marketMaxPrice: 150,
};

export interface OnboardingState {
  fplId: string;
  horizon: number;
  riskProfile: RiskProfile;
  sessionId: string | null;
}

async function getItem(key: string): Promise<string | null> {
  return AsyncStorage.getItem(key);
}

async function setItem(key: string, value: string): Promise<void> {
  await AsyncStorage.setItem(key, value);
}

export async function loadOnboardingState(): Promise<OnboardingState | null> {
  const [fplId, horizon, riskProfile, sessionId] = await Promise.all([
    getItem(STORAGE_KEYS.fplId),
    getItem(STORAGE_KEYS.horizon),
    getItem(STORAGE_KEYS.riskProfile),
    getItem(STORAGE_KEYS.sessionId),
  ]);
  if (!fplId) return null;
  return {
    fplId,
    horizon: horizon ? Number(horizon) : 3,
    riskProfile: (riskProfile as RiskProfile) || "balanced",
    sessionId: sessionId || null,
  };
}

export async function saveOnboardingState(state: OnboardingState): Promise<void> {
  await Promise.all([
    setItem(STORAGE_KEYS.fplId, state.fplId),
    setItem(STORAGE_KEYS.horizon, String(state.horizon)),
    setItem(STORAGE_KEYS.riskProfile, state.riskProfile),
    state.sessionId
      ? setItem(STORAGE_KEYS.sessionId, state.sessionId)
      : AsyncStorage.removeItem(STORAGE_KEYS.sessionId),
  ]);
}

export async function saveSessionId(sessionId: string): Promise<void> {
  await setItem(STORAGE_KEYS.sessionId, sessionId);
}

export async function clearOnboardingState(): Promise<void> {
  await AsyncStorage.multiRemove([
    STORAGE_KEYS.fplId,
    STORAGE_KEYS.horizon,
    STORAGE_KEYS.riskProfile,
    STORAGE_KEYS.sessionId,
  ]);
}

export async function loadPreferences(): Promise<StoredPreferences> {
  const raw = await getItem(STORAGE_KEYS.preferences);
  if (!raw) return DEFAULT_PREFERENCES;
  try {
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export async function savePreferences(preferences: StoredPreferences): Promise<void> {
  await setItem(STORAGE_KEYS.preferences, JSON.stringify(preferences));
}
