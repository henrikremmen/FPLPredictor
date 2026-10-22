import { fireEvent, render, screen } from "@testing-library/react-native";
import type { TeamTimeline, TimelineWeek } from "@fplmodell/api-client";
import { Season } from "../app/timeline";

const POSITIONS = ["GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "GK", "DEF", "MID", "FWD"] as const;

function week(event: number, ids: number[], extra: Partial<TimelineWeek> = {}): TimelineWeek {
  return {
    event, points: 50 + event, total_points: 50 * event, rank: 1000, overall_rank: 5000, rank_change: null,
    bank: 5, value: 1000, transfers_made: 0, transfer_cost: 0, bench_points: 2, chip: null,
    automatic_subs: [], transfers: [], final: true,
    picks: ids.map((id, i) => ({
      id, name: id === 99 ? "Upgrade" : `Player ${id}`, team: "ARS", position: POSITIONS[i], slot: i + 1,
      multiplier: i === 0 ? 2 : i < 11 ? 1 : 0, is_captain: i === 0, is_vice_captain: i === 1, points: 3, minutes: 90,
    })),
    ...extra,
  };
}

const first = Array.from({ length: 15 }, (_, i) => i + 1);
const second = first.map((id) => (id === 7 ? 99 : id));
const data: TeamTimeline = {
  entry_id: 1, caveat: "Provisional until data-checked.",
  weeks: [
    week(1, first),
    week(2, second, { chip: "bboost", transfers_made: 1, transfer_cost: 4,
      transfers: [{ in: { id: 99, name: "Upgrade", team: "CHE", position: "MID", cost: 55 }, out: { id: 7, name: "Player 7", team: "ARS", position: "MID", cost: 50 } }] }),
  ],
};

describe("Season timeline", () => {
  it("opens on the latest Gameweek and steps back to the first", () => {
    render(<Season data={data} />);
    expect(screen.getByText("GW2")).toBeTruthy();
    expect(screen.getByText(/Bench Boost/)).toBeTruthy();
    expect(screen.getByText("↑ Upgrade  £5.5m")).toBeTruthy();
    expect(screen.getByText("↓ Player 7  £5.0m")).toBeTruthy();
    expect(screen.getByText("Hit: −4 points")).toBeTruthy();
    expect(screen.getByLabelText("Upgrade, 3 pts, new this round")).toBeTruthy();
    fireEvent.press(screen.getByLabelText("Show GW1"));
    expect(screen.getByText("GW1")).toBeTruthy();
    expect(screen.getByText("First Gameweek of the season.")).toBeTruthy();
    fireEvent.press(screen.getByLabelText(/^GW2: 52 points/));
    expect(screen.getByText("GW2")).toBeTruthy();
  });
});
