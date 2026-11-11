import { ApiError, type ApiClient, type TeamResponse } from "@fplmodell/api-client";
import type { RiskProfile } from "@fplmodell/shared";

export interface SavedTeam {
  fplId: string | null;
  horizon: number;
  riskProfile: RiskProfile;
}

/**
 * The session's team. When the server no longer knows the session (its session store was reset or
 * moved), the team is imported again from what onboarding saved; `replaced` says to store the new session.
 */
export async function loadTeam(
  client: Pick<ApiClient, "getTeam" | "importTeam">, sessionId: string, saved: SavedTeam,
): Promise<{ team: TeamResponse; replaced: boolean }> {
  try {
    return { team: await client.getTeam(sessionId), replaced: false };
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 404 && saved.fplId)) throw error;
    return { team: await client.importTeam(saved.fplId, saved.horizon, saved.riskProfile), replaced: true };
  }
}
