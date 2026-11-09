import { CHIP_LABELS, type Chip } from "./constants";
import { formatPoints } from "./format";

/** Fields of the strategy and team payloads the decision card reads (U9). */
export interface DecisionCardInput {
  transfer: { decision: string; title: string; reason: string; transfers_out: string[]; transfers_in: string[] };
  captain: { captain: { name: string }; alternatives?: Array<{ name: string }>; margin: number };
  squad_health?: { flagged_players?: Array<{ name: string; news: string; availability: number }> };
}

export interface DecisionCard {
  recommendation: string;
  why: string;
  captain: string;
  alternative: string | null;
  news: string | null;
  chipHint: string | null;
}

/** The answer to "what should I do this week?", same words on web and mobile. */
export function decisionCard(strategy: DecisionCardInput,
                             chipStatus: Record<string, { available?: boolean; expires_after_gw?: number | null }> = {}): DecisionCard {
  const move = strategy.transfer.transfers_out.length
    ? `${strategy.transfer.transfers_out.join(", ")} → ${strategy.transfer.transfers_in.join(", ")}` : "";
  const flagged = (strategy.squad_health?.flagged_players ?? []).find(player => player.news) ?? null;
  // The strategy's alternatives can start with the captain himself.
  const next = (strategy.captain.alternatives ?? []).find(player => player.name !== strategy.captain.captain.name);
  const available = Object.entries(chipStatus).filter(([, status]) => status?.available);
  const expiry = available.map(([, status]) => status.expires_after_gw).find(value => value != null);
  return {
    recommendation: move ? `${strategy.transfer.title}: ${move}` : strategy.transfer.title,
    why: strategy.transfer.reason,
    captain: strategy.captain.captain.name,
    alternative: next ? `${next.name} (${formatPoints(strategy.captain.margin)} behind)` : null,
    news: flagged ? `${flagged.name}: ${flagged.news}` : null,
    chipHint: available.length
      ? `${available.map(([chip]) => CHIP_LABELS[chip as Chip] ?? chip).join(", ")} available${expiry ? ` until GW${expiry}` : ""}. Plan them in the multiweek plan.`
      : null,
  };
}
