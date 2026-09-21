import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { RiskProfile } from "@fplmodell/shared";
import {
  clearOnboardingState,
  loadOnboardingState,
  saveOnboardingState,
  saveSessionId,
  type OnboardingState,
} from "../lib/storage";

interface SessionContextValue {
  isLoading: boolean;
  isOnboarded: boolean;
  fplId: string | null;
  horizon: number;
  riskProfile: RiskProfile;
  sessionId: string | null;
  completeOnboarding: (state: Omit<OnboardingState, "sessionId"> & { sessionId: string }) => Promise<void>;
  setSessionId: (sessionId: string) => Promise<void>;
  resetOnboarding: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const [state, setState] = useState<OnboardingState | null>(null);

  useEffect(() => {
    loadOnboardingState()
      .then(setState)
      .finally(() => setIsLoading(false));
  }, []);

  const completeOnboarding = useCallback(async (next: Omit<OnboardingState, "sessionId"> & { sessionId: string }) => {
    await saveOnboardingState(next);
    setState(next);
  }, []);

  const setSessionId = useCallback(async (sessionId: string) => {
    await saveSessionId(sessionId);
    setState((previous) => (previous ? { ...previous, sessionId } : previous));
  }, []);

  const resetOnboarding = useCallback(async () => {
    await clearOnboardingState();
    setState(null);
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      isLoading,
      isOnboarded: Boolean(state?.fplId && state?.sessionId),
      fplId: state?.fplId ?? null,
      horizon: state?.horizon ?? 3,
      riskProfile: state?.riskProfile ?? "balanced",
      sessionId: state?.sessionId ?? null,
      completeOnboarding,
      setSessionId,
      resetOnboarding,
    }),
    [isLoading, state, completeOnboarding, setSessionId, resetOnboarding],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used within SessionProvider");
  return context;
}
