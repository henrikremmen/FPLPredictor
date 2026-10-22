/** FPL chip ids (picks `active_chip`) as short and full labels. */
export const FPL_CHIP_SHORT: Record<string, string> = {
  bboost: "BB", "3xc": "TC", freehit: "FH", wildcard: "WC", manager: "AM",
};
export const FPL_CHIP_NAMES: Record<string, string> = {
  bboost: "Bench Boost", "3xc": "Triple Captain", freehit: "Free Hit", wildcard: "Wildcard", manager: "Assistant Manager",
};

/** Players who joined or left the squad since the previous round (Free Hit rounds included). */
export function squadDiff<T extends { id: number }>(previous: readonly T[] | undefined, current: readonly T[]) {
  if (!previous) return { joined: [] as T[], left: [] as T[] };
  const before = new Set(previous.map((player) => player.id));
  const now = new Set(current.map((player) => player.id));
  return {
    joined: current.filter((player) => !before.has(player.id)),
    left: previous.filter((player) => !now.has(player.id)),
  };
}

/** Starting XI (slots 1–11) grouped GK → FWD, and the bench in FPL order. */
export function pitchRows<T extends { slot: number; position: string }>(picks: readonly T[]) {
  const starters = picks.filter((pick) => pick.slot <= 11);
  return {
    rows: ["GK", "DEF", "MID", "FWD"].map((position) => starters.filter((pick) => pick.position === position)),
    bench: picks.filter((pick) => pick.slot > 11).sort((a, b) => a.slot - b.slot),
  };
}
