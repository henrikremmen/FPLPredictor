import { render, screen } from "@testing-library/react-native";
import type { CopyCheck, TopManagers } from "@fplmodell/api-client";
import { CopyCheckView, TopManagersView } from "../app/top-managers";

const player = (id: number, name: string) => ({ id, name, team: "ARS", position: "MID" });
const data: TopManagers = {
  available: true, cohort: "top1pct",
  meta: { event: 10, season: "2026-27", collected_at: "2026-11-11T18:00:00Z", event_finished: true, stale: false,
    size: 2000, total_players: 11283441, population: 112835, sample_pages: 40, margin_pp: 2.2 },
  catch_up: { your_total: 650, your_rank: 400000, threshold: 697, cutoff_rank: 112835, gap: 47,
    per_gameweek: 1.7, remaining_gameweeks: 28, average_total: 720, trend: [] },
  match: { cohort: 61.4 },
  moves: { basis: "ownership change since GW9", bought: [{ ...player(1, "Saka"), share: 6.5 }],
    sold: [{ ...player(2, "Palmer"), share: -4.1 }], captains: [{ ...player(3, "Haaland"), share: 71 }],
    chips: { bboost: 3 }, average_hits: 0.4 },
  template: [{ ...player(3, "Haaland"), effective_ownership: 170, ownership: 98, captain_rate: 71, your_multiplier: 2 }],
  decisions: { threats: [], differentials: [], leverage: [] },
  managers: [],
};

describe("Top managers", () => {
  it("explains the top 1% sample and shows the gap, moves and template", () => {
    render(<TopManagersView data={data} />);
    expect(screen.getByText(/random 2,000 \(40 random pages/)).toBeTruthy();
    expect(screen.getByText("47 pts")).toBeTruthy();
    expect(screen.getByText("61%")).toBeTruthy();
    expect(screen.getByText("↑ Saka  +6.5%")).toBeTruthy();
    expect(screen.getByText("↓ Palmer  -4.1%")).toBeTruthy();
    expect(screen.getByText(/Bench Boost 3%/)).toBeTruthy();
    expect(screen.getByText("C")).toBeTruthy();
  });

  it("tells the user how to fill an empty tracker", () => {
    render(<TopManagersView data={{ available: false, cohort: "legacy" }} />);
    expect(screen.getByText(/No top-manager data yet/)).toBeTruthy();
  });

  it("shows each member's closest YouTuber with evidence", () => {
    const check: CopyCheck = {
      available: true, league: { id: 7, name: "Mini" }, event_through: 10, baseline_size: 75,
      members: [{ entry: 1, name: "Haakon", team_name: "A", closest: { entry: 70, name: "FPL Salah" },
        signal: { label: "Strong", percentile: 97, score: 98 }, overlap: 0.48, overlap_typical: 0.16,
        overlap_percentile: 97, same_buys: 17, buys_percentile: 96, follows: 0, same_chips: [],
        evidence: [{ event: 3, player: "Bentley", share: 0.18 }], series: [], closest_friend: null }],
      friends: { members: [], scores: [] },
    };
    render(<CopyCheckView data={check} />);
    expect(screen.getByText("Strong")).toBeTruthy();
    expect(screen.getByText(/Closest: FPL Salah · overlap 48% \(typical 16%\)/)).toBeTruthy();
    expect(screen.getByText("GW3: both bought Bentley (0.18% did)")).toBeTruthy();
  });
});
