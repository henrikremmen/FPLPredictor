export type RiskProfile = "balanced" | "stable" | "upside";
export type Position = "GK" | "DEF" | "MID" | "FWD";

export interface Player {
  id: number;
  name: string;
  position: Position;
  team: string;
  team_id: number;
  opponent: string;
  price: number;
  selling_price?: number;
  recommended_points: number;
  decision_points?: number;
  point_range_q10_q90?: string;
  expected_60plus_appearances?: number;
  status: string;
  role?: "" | "C" | "VC";
  bench_order?: string;
}

export interface Lineup {
  formation: string;
  projected_total: number;
  expected_total: number;
  captain_margin: number;
  starters: Player[];
  bench: Player[];
}

export interface ChipStatus {
  available: boolean;
  used_event: number | null;
  blocked_consecutive: boolean;
  half: number;
  expires_after_gw: number;
}

export interface TeamResponse {
  session_id: string;
  entry_id: number;
  event: number;
  target_event: number;
  manager_name: string;
  team_name: string;
  bank: number;
  free_transfers: number;
  deadline: string;
  horizon: number;
  risk_profile: RiskProfile;
  forecast_path: string;
  chip_status: Record<string, ChipStatus>;
  squad: Player[];
  lineup: Lineup;
}

export interface TransferPlan {
  out: string;
  in: string;
  cost: number;
  money_left: number;
  lineup_gain: number;
  expected_gain: number;
  hit: number;
  net_gain: number;
  expected_net_gain: number;
  projected_total: number;
  is_global_optimum: boolean;
}

export interface TransferResponse {
  number: number;
  global_optimum: boolean;
  plans: TransferPlan[];
}

export type ChipDecision = "PLAY" | "CONSIDER" | "HOLD" | "UNAVAILABLE";

export interface ChipCandidate {
  chip: string;
  label: string;
  event: number;
  gain: number;
  projected_points: number;
  threshold: number;
  decision: ChipDecision;
  available: boolean;
  reason: string;
  transfers_needed: number;
  squad: string[];
  double_players: number;
  blank_players: number;
}

export interface ChipStrategy {
  recommendation: string;
  summary: string;
  target_event: number;
  forecast_events: number[];
  horizon_limited: boolean;
  chip_status: Record<string, ChipStatus>;
  best_by_chip: ChipCandidate[];
  candidates: ChipCandidate[];
}
