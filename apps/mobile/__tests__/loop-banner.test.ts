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

import { fplChecklist } from "@fplmodell/shared";

describe("FPL checklist (W1)", () => {
  const week = {
    strategy: { target_event: 12, transfer: { hit: 0 } },
    sell: [{ name: "Saka", price: 98 }], buy: [{ name: "Palmer", price: 105 }],
    lineup: {
      formation: "3-4-3",
      starters: [{ name: "Raya" }, { name: "Haaland", role: "C" }, { name: "Palmer", role: "VC" }],
      bench: [{ name: "Kelleher", bench_order: "GK" }, { name: "Gvardiol", bench_order: "1" }, { name: "Wood", bench_order: "2" }],
    },
    chips: { best_by_chip: [{ chip: "bench_boost", event: 16, decision: "PLAY" }] },
  };
  it("lists the clicks in FPL order", () => {
    expect(fplChecklist(week)).toEqual([
      "Sell: Saka (£9.8m)", "Buy: Palmer (£10.5m)", "Starting XI (3-4-3): Raya, Haaland, Palmer",
      "Captain: Haaland · Vice-captain: Palmer", "Bench: 1. Gvardiol, 2. Wood · reserve GK Kelleher", "Chip: none",
    ]);
  });
  it("names a hit and a chip played this week", () => {
    const lines = fplChecklist({ ...week, strategy: { target_event: 16, transfer: { hit: 4 } }, sell: [], buy: [] });
    expect(lines.slice(0, 2)).toEqual(["Transfers: none", "Points hit: −4"]);
    expect(lines.at(-1)).toBe("Chip: Bench Boost");
  });
});
