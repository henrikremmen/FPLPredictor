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

/** W1: what to click in FPL, in that order. Same text on web and mobile. */
export function fplChecklist(week: ChecklistInput): string[] {
  const list = (players: Array<{ name: string; price: number }>) => players.map(p => `${p.name} (${formatMoney(p.price)})`).join(", ");
  const role = (tag: string) => week.lineup.starters.find(p => p.role === tag)?.name ?? "–";
  const keeper = week.lineup.bench.find(p => p.bench_order === "GK");
  const bench = week.lineup.bench.filter(p => p !== keeper).map((p, i) => `${i + 1}. ${p.name}`).join(", ");
  const chip = week.chips.best_by_chip.find(c => c.decision === "PLAY" && c.event === week.strategy.target_event);
  return [
    week.sell.length ? `Sell: ${list(week.sell)}` : "Transfers: none",
    ...(week.buy.length ? [`Buy: ${list(week.buy)}`] : []),
    ...(week.strategy.transfer.hit ? [`Points hit: −${week.strategy.transfer.hit}`] : []),
    `Starting XI (${week.lineup.formation}): ${week.lineup.starters.map(p => p.name).join(", ")}`,
    `Captain: ${role("C")} · Vice-captain: ${role("VC")}`,
    `Bench: ${bench}${keeper ? ` · reserve GK ${keeper.name}` : ""}`,
    `Chip: ${chip ? CHIP_LABELS[chip.chip as Chip] ?? chip.chip : "none"}`,
  ];
}
