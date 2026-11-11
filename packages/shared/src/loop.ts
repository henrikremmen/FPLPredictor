/** Lock-banner text shared by web and mobile (plan O2). Input mirrors LoopStatus. */
export interface LoopBannerInput {
  event: number | null;
  window_open: boolean;
  locked: boolean;
  missed_locks: number[];
  job: { state: string; error: string | null };
  fpl_data: { checkout: boolean; age_hours: number | null; stale: boolean };
}

export interface LoopBanner {
  headline: string | null;
  canLock: boolean;
  notes: string[];
  tone: "warning" | "info";
}

/** Nothing to show returns null; the banner stays out of the way between windows. */
export function loopBanner(status: LoopBannerInput): LoopBanner | null {
  const notes: string[] = [];
  let headline: string | null = null;
  const running = status.job.state === "running";
  const canLock = Boolean(status.event && status.window_open && !status.locked && !running);
  if (running) headline = `Locking GW${status.event}…`;
  else if (canLock) headline = `Lock window open for GW${status.event} – lock now`;
  if (status.job.state === "failed") notes.push(`Last lock attempt failed: ${status.job.error ?? "unknown error"}`);
  if (status.job.state === "complete" && status.locked) notes.push(`GW${status.event} is locked.`);
  if (status.missed_locks.length) {
    const rounds = status.missed_locks.map(gw => `GW${gw}`).join(", ");
    notes.push(`Never locked: ${rounds}. These rounds cannot count for the model comparison.`);
  }
  if (status.fpl_data.stale) {
    notes.push(status.fpl_data.checkout && status.fpl_data.age_hours != null
      ? `fpl-data: last snapshot ${Math.round(status.fpl_data.age_hours)} h ago. Run src/fpl_collect.py --data-root fpl-data auto.`
      : "fpl-data checkout not found; own data cannot be checked.");
  }
  if (!headline && !notes.length) return null;
  return { headline, canLock, notes, tone: canLock || running || status.job.state === "failed" ? "warning" : "info" };
}
