import { fireEvent, render, screen } from "@testing-library/react-native";
import type { TeamResponse, ThisWeek } from "@fplmodell/api-client";
import { ThisWeekView } from "../src/panels/ThisWeek";

const player = (id: number, name: string, extra = {}) => ({ id, name, position: "MID", team: "ARS", price: 50, recommended_points: 4, opponent: "CHE (H)", ...extra });
const team = { entry_id: 1, target_event: 12, chip_status: {} } as unknown as TeamResponse;
const week = {
  strategy: {
    target_event: 12,
    transfer: { title: "Saka → Palmer", hit: 0, free_transfers_before: 1 },
    captain: { captain: { name: "Haaland" }, vice_captain: { name: "Palmer" }, reason: "Clear model margin." },
    squad_health: { flagged_starters: [player(7, "Isak", { news: "Knock - 75% chance of playing" })] },
    plan: { weeks: [{ event: 12, transfers_out: ["Saka"], transfers_in: ["Palmer"] }, { event: 13, transfers_out: [], transfers_in: [] }] },
  },
  lineup: { formation: "3-4-3", starters: [player(1, "Haaland", { role: "C" }), player(2, "Palmer", { role: "VC" })], bench: [player(3, "Wood", { bench_order: "1" })] },
  lineup_value: { expected_with_autosubs: 54.3 },
  chips: { recommendation: "Save chips for now", best_by_chip: [] },
  robustness: null,
  sell: [{ id: 9, name: "Saka", price: 98 }], buy: [{ id: 2, name: "Palmer", price: 105 }],
} as unknown as ThisWeek;

describe("This week (W1)", () => {
  it("shows the steps after the transfer and ticks one off", () => {
    const toggled: string[] = [];
    render(<ThisWeekView team={team} week={week} done={["captain"]} onToggle={step => toggled.push(step)} />);
    expect(screen.getByText("1. Saka → Palmer")).toBeTruthy();
    expect(screen.getByText("Sell Saka (£9.8m). Buy Palmer (£10.5m).")).toBeTruthy();
    expect(screen.getByText("✓. Captain Haaland")).toBeTruthy();
    expect(screen.getByText(/With autosubs and VC: 54.3 xP/)).toBeTruthy();
    expect(screen.getByText("Watch Isak: Knock - 75% chance of playing")).toBeTruthy();
    expect(screen.getByText("GW13: roll")).toBeTruthy();
    fireEvent.press(screen.getAllByText("Mark done")[0]);
    expect(toggled).toEqual(["transfers"]);
  });
});
