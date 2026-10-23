export const POSITIONS = ["GK", "DEF", "MID", "FWD"] as const;
export type Position = (typeof POSITIONS)[number];

export const POSITION_LABELS: Record<Position, string> = {
  GK: "Goalkeeper",
  DEF: "Defence",
  MID: "Midfield",
  FWD: "Forward",
};

export const RISK_PROFILES = ["balanced", "stable", "upside"] as const;
export type RiskProfile = (typeof RISK_PROFILES)[number];

export const RISK_PROFILE_LABELS: Record<RiskProfile, string> = {
  balanced: "Balanced",
  stable: "Stable",
  upside: "Upside",
};

/** What the lineup and optimisers rank by under each profile (src/fpl_app.py apply_risk_profile). */
export const RISK_PROFILE_SCORE: Record<RiskProfile, { label: string; formula: string }> = {
  balanced: { label: "Expected points", formula: "the model's expected points" },
  stable: { label: "Stable score", formula: "expected points − 0.1 × (Q90 − Q10)" },
  upside: { label: "Upside score", formula: "0.7 × expected points + 0.3 × Q90" },
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
