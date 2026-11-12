import { loopBanner } from "@fplmodell/shared";

const base = {
  event: 11, window_open: false, locked: false, missed_locks: [] as number[],
  job: { state: "idle", error: null as string | null },
  fpl_data: { checkout: true, age_hours: 3, stale: false },
};

describe("lock banner", () => {
  it("stays hidden between windows when nothing is wrong", () => {
    expect(loopBanner(base)).toBeNull();
  });

  it("offers the lock only when the window is open and the round is not locked", () => {
    const open = loopBanner({ ...base, window_open: true });
    expect(open).toMatchObject({ headline: "Lock window open for GW11 – lock now", canLock: true, tone: "warning" });
    expect(open?.notes).toEqual(["Refresh forecast also locks the round."]);
    expect(loopBanner({ ...base, window_open: true, locked: true })).toBeNull();
    expect(loopBanner({ ...base, window_open: true, job: { state: "running", error: null } }))
      .toMatchObject({ headline: "Locking GW11…", canLock: false });
  });

  it("reports missed rounds, failures and stale fpl-data", () => {
    const banner = loopBanner({
      ...base, missed_locks: [9], job: { state: "failed", error: "No capture" },
      fpl_data: { checkout: true, age_hours: 340.2, stale: true },
    });
    expect(banner?.canLock).toBe(false);
    expect(banner?.notes).toEqual([
      "Last lock attempt failed: No capture",
      "Never locked: GW9. These rounds cannot count for the model comparison.",
      "fpl-data: last snapshot 340 h ago. Run src/fpl_collect.py --data-root fpl-data auto.",
    ]);
  });
});

import { decisionCard } from "@fplmodell/shared";

describe("decision card (U9)", () => {
  const strategy = {
    transfer: { decision: "ROLL", title: "Roll the free transfer", reason: "Best move gains 0.3 over 3 GW.", transfers_out: [], transfers_in: [] },
    captain: { captain: { name: "Haaland" }, alternatives: [{ name: "Salah" }], margin: 1.24 },
    squad_health: { flagged_players: [{ name: "Saka", news: "Knock - 75% chance of playing", availability: 0.75 }] },
  };
  it("answers the week in one card", () => {
    expect(decisionCard(strategy, { bench_boost: { available: true, expires_after_gw: 19 }, wildcard: { available: false } })).toEqual({
      recommendation: "Roll the free transfer", why: "Best move gains 0.3 over 3 GW.", captain: "Haaland",
      alternative: "Salah (1.2 behind)", news: "Saka: Knock - 75% chance of playing",
      chipHint: "Bench Boost available until GW19. Plan them in the multiweek plan.",
    });
  });
  it("names the move and stays quiet without news or chips", () => {
    const card = decisionCard({ ...strategy, transfer: { ...strategy.transfer, title: "Make one transfer", transfers_out: ["A"], transfers_in: ["B"] },
      squad_health: { flagged_players: [] } });
    expect(card.recommendation).toBe("Make one transfer: A → B");
    expect([card.news, card.chipHint]).toEqual([null, null]);
    const self = decisionCard({ ...strategy, captain: { ...strategy.captain, alternatives: [{ name: "Haaland" }, { name: "Salah" }] } });
    expect(self.alternative).toBe("Salah (1.2 behind)");
  });
});
