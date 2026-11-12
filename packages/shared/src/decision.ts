import { CHIP_LABELS, type Chip } from "./constants";
import { formatMoney } from "./format";

/** Fields of the this-week payload the FPL checklist reads (W1). */
export interface ChecklistInput {
  strategy: { target_event: number; transfer: { hit: number } };
  sell: Array<{ name: string; price: number }>;
  buy: Array<{ name: string; price: number }>;
  lineup: { formation: string; starters: Array<{ name: string; role?: string }>; bench: Array<{ name: string; bench_order?: string }> };
  chips: { best_by_chip: Array<{ chip: string; event: number; decision: string }> };
}

const role = (week: ChecklistInput, tag: string) => week.lineup.starters.find(p => p.role === tag)?.name ?? "–";
const chipNow = (week: ChecklistInput) => {
  const chip = week.chips.best_by_chip.find(c => c.decision === "PLAY" && c.event === week.strategy.target_event);
  return chip ? CHIP_LABELS[chip.chip as Chip] ?? chip.chip : "none";
};

/** W1: what to click in FPL, in that order. Same text on web and mobile. */
export function fplChecklist(week: ChecklistInput): string[] {
  const list = (players: Array<{ name: string; price: number }>) => players.map(p => `${p.name} (${formatMoney(p.price)})`).join(", ");
  const keeper = week.lineup.bench.find(p => p.bench_order === "GK");
  const bench = week.lineup.bench.filter(p => p !== keeper).map((p, i) => `${i + 1}. ${p.name}`).join(", ");
  return [
    week.sell.length ? `Sell: ${list(week.sell)}` : "Transfers: none",
    ...(week.buy.length ? [`Buy: ${list(week.buy)}`] : []),
    ...(week.strategy.transfer.hit ? [`Points hit: −${week.strategy.transfer.hit}`] : []),
    `Starting XI (${week.lineup.formation}): ${week.lineup.starters.map(p => p.name).join(", ")}`,
    `Captain: ${role(week, "C")} · Vice-captain: ${role(week, "VC")}`,
    `Bench: ${bench}${keeper ? ` · reserve GK ${keeper.name}` : ""}`,
    `Chip: ${chipNow(week)}`,
  ];
}

/** L1: the parts of the advice whose change the user should hear about. */
export interface AdviceSummary { transfers: string; captain: string; vice: string; chip: string }
const SUMMARY_LABELS: Record<keyof AdviceSummary, string> = { transfers: "Transfers", captain: "Captain", vice: "Vice-captain", chip: "Chip" };

export function adviceSummary(week: ChecklistInput): AdviceSummary {
  return {
    transfers: week.sell.length ? `${week.sell.map(p => p.name).join(", ")} → ${week.buy.map(p => p.name).join(", ")}` : "roll",
    captain: role(week, "C"), vice: role(week, "VC"), chip: chipNow(week),
  };
}

/** L1 "Plan changed since you looked": one line per part that differs; nothing on a first look. */
export function adviceDiff(before: AdviceSummary | null, now: AdviceSummary): string[] {
  if (!before) return [];
  return (Object.keys(SUMMARY_LABELS) as Array<keyof AdviceSummary>)
    .filter(key => before[key] !== now[key]).map(key => `${SUMMARY_LABELS[key]}: ${before[key]} → ${now[key]}`);
}
