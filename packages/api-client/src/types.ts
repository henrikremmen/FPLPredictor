/**
 * Response shapes for the FastAPI bridge (src/api.py).
 *
 * Endpoints return plain `-> dict`, not Pydantic `response_model`s, so these
 * are not generated from the OpenAPI schema (see openapi.d.ts) — they are
 * hand-ported from frontend/src/types.ts, which is verified against real
 * payloads from the running backend. Keep the two in sync when the backend
 * response shape changes.
 */

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
  market_clean_sheet_probability?: number;
  market_team_expected_goals?: number;
  market_player_goal_probability?: number;
  market_player_assist_probability?: number;
  selected_by_percent?: number;
  transfers_in_event?: number;
  transfers_out_event?: number;
  price_change_percent?: number;
  price_change_projected_percent?: number;
  price_change_likelihood?: number;
  defensive_contribution_per_90?: number;
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
  overall_points?: number | null;
  overall_rank?: number | null;
  team_value?: number | null;
  squad_source: "fpl_public" | "manual_override";
  manual_changes: Array<{ out_id: number; out: string; in_id: number; in: string }>;
  squad: Player[];
  lineup: Lineup;
}

export interface SquadChange {
  out_id: number;
  in_id: number;
}

export interface SquadUpdateResponse extends TeamResponse {
  squad_update?: {
    mode: "synchronize" | "apply_transfers";
    changes: Array<{ out_id: number; out: string; in_id: number; in: string }>;
    bank_before: number;
    bank_after: number;
    free_transfers_before: number;
    free_transfers_after: number;
    hit: number;
  };
}

export interface AnalyticsTimelineRow {
  event: number;
  points: number;
  total_points: number;
  global_average: number;
  vs_average: number;
  cumulative_vs_average: number;
  overall_rank: number | null;
  rank_change: number | null;
  transfers: number;
  transfer_cost: number;
  transfer_swing: number;
  bench_points: number;
  team_value: number;
  value_change: number | null;
  captain: string | null;
  captain_bonus: number;
  captain_opportunity_loss: number;
  chip: string | null;
  finished: boolean;
}

export interface AnalyticsSquadPlayer {
  id: number;
  name: string;
  team: string;
  position: Position | "?";
  pick_position: number;
  multiplier: number;
  is_captain: boolean;
  is_vice_captain: boolean;
  raw_points: number;
  effective_points: number;
  global_ownership: number;
  league_ownership: number;
  league_effective_ownership: number;
  league_swing: number;
  minutes: number;
}

export interface RelativeImpact {
  id: number;
  name: string;
  team: string;
  raw_points: number;
  your_multiplier: number;
  league_effective_ownership: number;
  league_swing: number;
  owned: boolean;
}

export interface AnalyticsDecisionPlayer {
  id: number;
  name: string;
  team: string;
  position: Position;
  price: number;
  projection: number;
  league_effective_ownership: number;
  league_ownership: number;
  top10k_effective_ownership: number;
  global_ownership: number;
  owned: boolean;
  projected_multiplier: number;
  rank_exposure: number;
  differential_value: number;
  threat_value: number;
  captain_rank_edge?: number;
  status: string;
  opponent: string;
}

export interface ManagerAnalytics {
  entry_id: number;
  manager_name: string;
  team_name: string;
  available_events: number[];
  completed_events: number[];
  selected_event: number;
  benchmark_event: number;
  leagues: Array<{ id: number; name: string; league_type: string }>;
  selected_league_id: number | null;
  summary: {
    total_points: number;
    overall_rank: number | null;
    percentile: number | null;
    average_points: number;
    points_vs_global_average: number;
    best_week: { event: number; points: number };
    worst_week: { event: number; points: number };
    bench_points: number;
    transfer_cost: number;
    transfer_swing: number;
    captain_bonus: number;
    captain_opportunity_loss: number;
    team_value: number;
  };
  global_benchmark: {
    sample_label: string;
    sample_size: number;
    sample_average_total: number | null;
    points_gap: number | null;
    ownership: Array<{
      id: number; name: string; effective_ownership: number; ownership: number;
      captain_rate: number; global_ownership: number;
    }>;
  };
  timeline: AnalyticsTimelineRow[];
  position_points: Record<Position, number>;
  gameweek: {
    event: number;
    points: number;
    squad: AnalyticsSquadPlayer[];
    captain: AnalyticsSquadPlayer | null;
    best_contributors: AnalyticsSquadPlayer[];
    missed_bench_points: number;
    relative_gain: number;
    top_gains: RelativeImpact[];
    top_losses: RelativeImpact[];
  };
  league: null | {
    id: number;
    name: string;
    member_count: number;
    analyzed_managers: number;
    sampled: boolean;
    your_rank: number | null;
    gap_to_leader: number | null;
    leader: null | { team_name: string; manager_name: string; total_points: number };
    standings: Array<{
      rank: number | null; last_rank: number | null; entry: number;
      team_name: string; manager_name: string; event_points: number;
      total_points: number; is_you: boolean;
    }>;
    development: Array<{
      event: number; rank: number; members: number; own_total: number;
      leader_total: number; gap_to_leader: number; league_average: number;
    }>;
    ownership: Array<{
      id: number; name: string; ownership: number; start_rate: number;
      captain_rate: number; effective_ownership: number; global_ownership: number;
    }>;
    mode: "protect" | "balanced" | "chase";
    advice: string;
  };
  decisions: {
    horizon: number;
    forecast_events: number[];
    differentials: AnalyticsDecisionPlayer[];
    threats: AnalyticsDecisionPlayer[];
    leverage: AnalyticsDecisionPlayer[];
    captain_matrix: AnalyticsDecisionPlayer[];
  };
  method: string;
  caveats: string[];
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
  outgoing_ids: number[];
  global_optimum: boolean;
  plans: TransferPlan[];
}

export interface PlanWeek {
  event: number;
  transfers_out: string[];
  transfers_in: string[];
  free_transfers_before: number;
  paid_transfers: number;
  hit: number;
  bank: number;
  captain: string;
  formation: string;
  starters: string[];
  projected_points: number;
}

export interface MultiweekPlan {
  weeks: PlanWeek[];
  total_projected_points: number;
  discounted_objective_points: number;
  discount: number;
  global_optimum: boolean;
  solver_message: string;
  mip_gap: number | null;
  caveat: string;
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

export interface SquadSelection {
  event: number;
  formation: string;
  projected_points: number;
  captain: string;
  vice_captain: string;
  starters: Player[];
  bench: Player[];
  squad: Player[];
  effective_cost: number;
  money_left: number;
  transfers_needed: number;
}

export interface WildcardSelection extends SquadSelection {
  horizon_events: number[];
  horizon_points_before_future_transfers: number;
  discount: number;
  roadmap: MultiweekPlan;
}

export interface RecommendedSquads {
  forecast_events: number[];
  free_hit_by_event: SquadSelection[];
  wildcard: WildcardSelection;
  method: string;
  caveat: string;
}

export interface StrategyPlayer {
  id: number;
  name: string;
  position: Position;
  team: string;
  opponent: string;
  price: number;
  points: number;
  decision_points: number;
  ownership: number | null;
  availability: number;
  status: string;
  news: string;
  price_change_percent: number | null;
  price_change_projected_percent: number | null;
  price_change_likelihood: number;
  value_score: number;
}

export interface StrategyAction {
  priority: number;
  severity: "urgent" | "decision" | "monitor" | "check";
  category: string;
  title: string;
  detail: string;
  view: string;
}

export interface StrategyAdvice {
  target_event: number;
  generated_at: string;
  headline: string;
  deadline: { deadline: string; hours_remaining: number | null; urgency: string };
  manager_context: {
    overall_points: number | null;
    overall_rank: number | null;
    team_value: number | null;
    risk_profile: RiskProfile;
  };
  transfer: {
    decision: "ROLL" | "HOLD" | "TRANSFER" | "HIT";
    title: string;
    reason: string;
    transfers_out: string[];
    transfers_in: string[];
    hit: number;
    free_transfers_before: number;
    bank_after: number | null;
    global_optimum: boolean;
    horizon: number;
    hit_guard: {
      evaluated: boolean;
      avoided: boolean;
      model_gain_after_hit: number | null;
      required_uncertainty_buffer: number | null;
    };
    confidence: "high" | "medium" | "low";
    warnings: string[];
  };
  captain: {
    captain: StrategyPlayer;
    vice_captain: StrategyPlayer;
    alternatives: StrategyPlayer[];
    margin: number;
    confidence: "strong" | "medium" | "close";
    reason: string;
  };
  squad_health: {
    playable_players: number;
    flagged_players: StrategyPlayer[];
    flagged_starters: StrategyPlayer[];
    bench_expected_points: number;
    playable_outfield_bench: number;
    triple_ups: string[];
    rating: "healthy" | "watch" | "fragile";
  };
  price_alerts: {
    available: boolean;
    owned_at_risk: StrategyPlayer[];
    targets_rising: StrategyPlayer[];
    caveat: string;
  };
  watchlists: {
    top_targets: StrategyPlayer[];
    differentials: StrategyPlayer[];
    value: StrategyPlayer[];
    caveat: string;
  };
  schedule: Array<{ event: number; blank_players: number; double_players: number }>;
  actions: StrategyAction[];
  plan: MultiweekPlan;
  principles: string[];
  method: string;
  caveat: string;
}

export interface HealthResponse {
  status: string;
  uptime_seconds: number;
  active_sessions: number;
}
