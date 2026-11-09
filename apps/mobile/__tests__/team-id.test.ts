import { teamIdFromReference } from "@fplmodell/shared";

describe("teamIdFromReference", () => {
  it("keeps a plain ID and ignores the Gameweek in a pasted link", () => {
    expect(teamIdFromReference("5139814")).toBe("5139814");
    expect(teamIdFromReference("https://fantasy.premierleague.com/en/entry/5139814/event/4")).toBe("5139814");
    expect(teamIdFromReference("fantasy.premierleague.com/entry/5139814/history")).toBe("5139814");
  });

  it("drops non-digits while typing", () => {
    expect(teamIdFromReference(" 51 398a14 ")).toBe("5139814");
    expect(teamIdFromReference("abc")).toBe("");
  });
});
