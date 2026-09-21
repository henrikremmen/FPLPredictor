export const POSITIONS = ["GK", "DEF", "MID", "FWD"] as const;
export type Position = (typeof POSITIONS)[number];

export const POSITION_LABELS: Record<Position, string> = {
  GK: "Keeper",
  DEF: "Forsvar",
  MID: "Midtbane",
  FWD: "Spiss",
};

export const RISK_PROFILES = ["balanced", "stable", "upside"] as const;
export type RiskProfile = (typeof RISK_PROFILES)[number];

export const RISK_PROFILE_LABELS: Record<RiskProfile, string> = {
  balanced: "Balansert",
  stable: "Stabil",
  upside: "Oppside",
};

export const CHIPS = ["wildcard", "free_hit", "triple_captain", "bench_boost"] as const;
export type Chip = (typeof CHIPS)[number];

export const CHIP_LABELS: Record<Chip, string> = {
  wildcard: "Wildcard",
  free_hit: "Free Hit",
  triple_captain: "Triple Captain",
  bench_boost: "Bench Boost",
};

export const MIN_HORIZON = 1;
export const MAX_HORIZON = 8;
export const MAX_TRANSFERS = 5;

export const STORAGE_KEYS = {
  fplId: "fplmodell.fplId",
  horizon: "fplmodell.horizon",
  riskProfile: "fplmodell.riskProfile",
  sessionId: "fplmodell.sessionId",
  preferences: "fplmodell.preferences",
} as const;
