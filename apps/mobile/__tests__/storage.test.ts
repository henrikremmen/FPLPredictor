import {
  clearOnboardingState,
  loadOnboardingState,
  saveOnboardingState,
  saveSessionId,
} from "../src/lib/storage";

describe("onboarding storage", () => {
  it("returns null before anything is saved", async () => {
    await expect(loadOnboardingState()).resolves.toBeNull();
  });

  it("round-trips a saved onboarding state", async () => {
    await saveOnboardingState({
      fplId: "5139814",
      horizon: 5,
      riskProfile: "stable",
      sessionId: "session-1",
    });

    await expect(loadOnboardingState()).resolves.toEqual({
      fplId: "5139814",
      horizon: 5,
      riskProfile: "stable",
      sessionId: "session-1",
    });
  });

  it("updates only the session id without touching the rest", async () => {
    await saveOnboardingState({
      fplId: "5139814",
      horizon: 2,
      riskProfile: "upside",
      sessionId: "old-session",
    });

    await saveSessionId("new-session");

    const state = await loadOnboardingState();
    expect(state?.sessionId).toBe("new-session");
    expect(state?.horizon).toBe(2);
    expect(state?.riskProfile).toBe("upside");
  });

  it("clears every stored key", async () => {
    await saveOnboardingState({
      fplId: "5139814",
      horizon: 3,
      riskProfile: "balanced",
      sessionId: "session-1",
    });

    await clearOnboardingState();

    await expect(loadOnboardingState()).resolves.toBeNull();
  });
});
