import { pitchRows, squadDiff } from "@fplmodell/shared";

const pick = (id: number, slot: number, position: string) => ({ id, slot, position });

describe("timeline helpers", () => {
  it("reports players who joined and left since the previous round", () => {
    const before = [pick(1, 1, "GK"), pick(2, 2, "DEF")];
    const after = [pick(1, 1, "GK"), pick(3, 2, "DEF")];
    expect(squadDiff(before, after)).toEqual({ joined: [pick(3, 2, "DEF")], left: [pick(2, 2, "DEF")] });
    expect(squadDiff(undefined, after)).toEqual({ joined: [], left: [] });
  });

  it("groups the XI by position and keeps bench order", () => {
    const picks = [pick(5, 13, "DEF"), pick(1, 1, "GK"), pick(4, 12, "GK"), pick(2, 2, "DEF"), pick(3, 11, "FWD")];
    const { rows, bench } = pitchRows(picks);
    expect(rows.map((row) => row.map((p) => p.id))).toEqual([[1], [2], [], [3]]);
    expect(bench.map((p) => p.id)).toEqual([4, 5]);
  });
});
