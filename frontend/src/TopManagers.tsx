import { useEffect, useState } from "react";
import type { TeamResponse, TopCohort, TopManagers as TopData, TopManagersStatus, TopPlayer } from "@fplmodell/api-client";
import { waitForJob } from "@fplmodell/api-client";
import { formatRank, FPL_CHIP_NAMES } from "@fplmodell/shared";
import { api } from "./api";
import { CopyCheck } from "./CopyCheck";
import { Icon } from "./icons";

const COHORTS: Array<{ id: TopCohort; label: string; target: string }> = [
  { id: "top100", label: "Top 100", target: "the top 100" },
  { id: "legacy", label: "Legacy", target: "the legacy median" },
  { id: "top1pct", label: "Top 1%", target: "the top 1%" },
  { id: "youtubers", label: "YouTubers", target: "the YouTuber median" },
];
const number = (value: number | null | undefined) => value == null ? "–" : new Intl.NumberFormat("en-GB").format(value);
const role = (multiplier: number | null) => multiplier == null ? "–" : multiplier >= 3 ? "TC" : multiplier === 2 ? "C" : multiplier === 1 ? "XI" : "Bench";

function Explainer({ data }: { data: TopData }) {
  const meta = data.meta!;
  if (data.cohort === "top1pct") return <p>The top 1% is {number(meta.population)} managers (1% of {number(meta.total_players)}). Reading every one of them each round would take hours, so we read a random {number(meta.size)}: {meta.sample_pages} random pages of the overall table. Ownership figures land within ±{meta.margin_pp} percentage points of the true value 19 times out of 20. The points cutoff is read directly and is exact.</p>;
  if (data.cohort === "youtubers") return <p>{number(meta.size)} well-known FPL YouTubers and experts, from Let's Talk FPL, FPL Mate, FPL Focal and FPL Harry to FPL Salah and BigManBakar. Their FPL ids change every season; each one is checked against FPL. They reveal moves in videos before the deadline, but their squads only become public here after it.</p>;
  if (data.cohort === "legacy") return <p>The best managers of all time who still play. Candidates come from Fantasy Football Pundit's all-time table; we rank them on their past overall ranks from FPL (log scale, the latest season weighs most and each older season 80% of the next, at least five seasons). Typical rank is the rank that score corresponds to.</p>;
  return <p>Today's overall top 100, read in full. A good run this season, not a long record: use Legacy for proven managers.</p>;
}

function ShareList({ rows, empty, signed = false }: { rows: Array<TopPlayer & { share: number }>; empty: string; signed?: boolean }) {
  if (!rows.length) return <p className="empty-copy">{empty}</p>;
  const max = Math.max(1, ...rows.map(row => Math.abs(row.share)));
  return <div className="ownership-list">{rows.map(row => <div key={row.id}><strong>{row.name}</strong><i><b style={{ width: `${100 * Math.abs(row.share) / max}%` }} /></i><span>{signed && row.share > 0 ? "+" : ""}{row.share.toFixed(1)}%</span><small>{row.team}</small></div>)}</div>;
}

/** Follow the top 100, the all-time legacy 100, the top 1% and YouTubers; check who in your league copies whom. */
export function TopManagers({ team }: { team: TeamResponse }) {
  const [cohort, setCohort] = useState<TopCohort | "copy">("top100");
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<TopData | null>(null);
  const [error, setError] = useState("");
  const [updating, setUpdating] = useState(false);
  const [status, setStatus] = useState<TopManagersStatus | null>(null);
  const load = () => {
    let active = true; // a slow answer for the previous cohort must not overwrite this one
    setError("");
    if (cohort !== "copy") api.topManagers(team.session_id, cohort)
      .then(next => { if (active) setData(next); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : "Could not load top managers."); });
    return () => { active = false; };
  };
  useEffect(load, [team.session_id, cohort]);

  /** The update runs on the server for minutes; follow its status until it ends, then reload. */
  const follow = async (start?: () => Promise<unknown>) => {
    setUpdating(true); setError("");
    try { await start?.(); await waitForJob(api.topManagersStatus, setStatus, 1500); load(); setRevision(value => value + 1); }
    catch (err) { setError(err instanceof Error ? err.message : "The update failed."); }
    finally { setUpdating(false); setStatus(null); }
  };
  const update = () => follow(() => api.topManagersRefresh(team.session_id));
  useEffect(() => { // an update started before a page reload is still running on the server
    api.topManagersStatus().then(current => { if (current.state === "running") void follow(); }).catch(() => undefined);
  }, []);

  const label = COHORTS.find(item => item.id === cohort) ?? COHORTS[0];
  const meta = data?.meta;
  const gap = data?.catch_up?.gap;
  return <>
    <header className="page-heading compact">
      <div className="page-heading-main">
        <span className="page-icon"><Icon.Users size={22} /></span>
        <div><span className="eyebrow">Follow and compare</span><h1>Top managers</h1><p>What the best managers did last round, how far behind you are and how close your squad is to theirs.</p></div>
      </div>
      <div className="deadline"><small>{meta ? `GW${meta.event} squads` : "No data yet"}</small><strong>{meta ? new Date(meta.collected_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–"}</strong></div>
      <button className="primary" onClick={() => void update()} disabled={updating}>{updating ? (status?.total ? `${status.phase} ${status.done}/${status.total}` : status?.phase ?? "Starting…") : "Update"}</button>
    </header>
    {error && <div className="error-banner" role="alert"><Icon.Alert size={15} /><p>{error}</p><button onClick={() => setError("")} aria-label="Close"><Icon.Close size={15} /></button></div>}
    <section className="analysis-controls panel"><div className="analysis-tabs">{COHORTS.map(item => <button key={item.id} className={cohort === item.id ? "active" : ""} onClick={() => setCohort(item.id)}>{item.label}</button>)}<button className={cohort === "copy" ? "active" : ""} onClick={() => setCohort("copy")}>Copy check</button></div></section>
    {cohort === "copy" ? <CopyCheck team={team} revision={revision} /> : <>
    {!data && !error && <div className="loading"><span className="spinner" />Loading top managers…</div>}
    {data && !data.available && <section className="panel"><h2>No top-manager data yet</h2><p>Press Update after the deadline when you prepare the app for a new round. It reads about 2,600 public FPL pages for the top managers and then your mini-leagues for the copy check, about 5–7 minutes in all. Terminal: <code>.venv/bin/python src/top_managers.py collect</code></p></section>}
    {data?.available && meta && data.catch_up && data.moves && <>
      <section className="panel top-explainer"><span className="eyebrow">{label.label} · {number(meta.size)} managers</span><Explainer data={data} />{meta.stale && <p className="negative">These are GW{meta.event} squads. Press Update for the latest round.</p>}</section>
      <section className="analysis-metrics">
        <article><small>Gap to {label.target}</small><strong>{gap == null ? "–" : gap > 0 ? `${number(gap)} pts` : `+${number(-gap)} pts`}</strong><span>{gap == null ? "" : gap > 0 ? "behind" : "ahead"} · {data.cohort === "top1pct" ? `cutoff ${data.catch_up.threshold} pts at rank ${number(data.catch_up.cutoff_rank)}` : data.cohort === "top100" ? `rank 100 has ${data.catch_up.threshold} pts` : `median ${data.catch_up.threshold} pts`}</span></article>
        <article><small>Per remaining round</small><strong>{gap != null && gap > 0 ? `${data.catch_up.per_gameweek} pts` : "–"}</strong><span>over {data.catch_up.remaining_gameweeks} Gameweeks to close the gap</span></article>
        <article><small>Squad match</small><strong>{data.match?.cohort.toFixed(0)}%</strong><span>share of their effective ownership your planned XI and captain cover</span></article>
        <article><small>Their average total</small><strong>{data.catch_up.average_total ?? "–"}</strong><span>you {number(data.catch_up.your_total)} · avg hit −{data.moves.average_hits} this round</span></article>
      </section>
      <div className="analysis-two-col">
        <section className="panel analysis-section"><span className="eyebrow">What they did · GW{meta.event}</span><h2>Bought</h2><p className="section-copy">{data.moves.basis ?? "Ownership change appears after the second update this season."}</p><ShareList rows={data.moves.bought} empty="No transfers in." signed /><h2>Sold</h2><ShareList rows={data.moves.sold} empty="No transfers out." signed /></section>
        <section className="panel analysis-section"><span className="eyebrow">Captain and chips</span><h2>Captains</h2><ShareList rows={data.moves.captains} empty="No captain data." /><h2>Chips this round</h2>{Object.keys(data.moves.chips).length ? <div className="ownership-list">{Object.entries(data.moves.chips).map(([chip, share]) => <div key={chip}><strong>{FPL_CHIP_NAMES[chip] ?? chip}</strong><i><b style={{ width: `${share}%` }} /></i><span>{share}%</span><small /></div>)}</div> : <p className="empty-copy">Nobody played a chip.</p>}</section>
      </div>
      <section className="panel analysis-section table-panel"><div className="section-title"><div><span className="eyebrow">Template vs you</span><h2>Their most important players</h2></div><span className="legend">EO = average multiplier × 100</span></div><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>Player</th><th>EO</th><th>Owned</th><th>Captain</th><th>You</th></tr></thead><tbody>{data.template!.map(row => <tr key={row.id} className={row.your_multiplier ? "you-row" : ""}><td><strong>{row.name}</strong><small>{row.team} · {row.position}</small></td><td>{row.effective_ownership.toFixed(0)}%</td><td>{row.ownership.toFixed(0)}%</td><td>{row.captain_rate.toFixed(0)}%</td><td>{role(row.your_multiplier)}</td></tr>)}</tbody></table></div></section>
      <div className="risk-grid">
        <section className="panel analysis-section"><span className="eyebrow">Threats</span><h2>They have, you don't</h2><p className="section-copy">At least 20% EO among them, ranked by model points × EO.</p><div className="decision-rows">{data.decisions!.threats.map((row, index) => <div className="decision-row" key={row.id}><span className="decision-rank">{index + 1}</span><div><strong>{row.name}</strong><small>{row.team} · {row.opponent}</small></div><span><small>EO</small><b>{row.league_effective_ownership.toFixed(0)}%</b></span><span><small>Model</small><b>{row.projection.toFixed(1)}</b></span><span /></div>)}</div></section>
        <section className="panel analysis-section"><span className="eyebrow">Your edge</span><h2>You have, they don't</h2><p className="section-copy">Your starters ranked by model points × (your multiplier − their EO).</p><div className="decision-rows">{data.decisions!.leverage.map((row, index) => <div className="decision-row" key={row.id}><span className="decision-rank">{index + 1}</span><div><strong>{row.name}</strong><small>{row.team} · {row.opponent}</small></div><span><small>EO</small><b>{row.league_effective_ownership.toFixed(0)}%</b></span><span><small>Model</small><b>{row.projection.toFixed(1)}</b></span><span><small>Edge</small><b>{row.rank_exposure.toFixed(1)}</b></span></div>)}</div></section>
      </div>
      {!!data.managers?.length && <section className="panel analysis-section table-panel"><div className="section-title"><div><span className="eyebrow">{label.label}</span><h2>Managers</h2></div><span className="legend">Match = squad overlap weighted by multiplier · shared = players in both squads</span></div><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>{data.cohort === "legacy" ? "Typical rank" : data.cohort === "youtubers" ? "OR" : "#"}</th><th>Manager</th><th>Total</th><th>GW</th><th>Captain</th><th>Chip</th><th>Transfers</th><th>Match</th><th>Shared</th></tr></thead><tbody>{data.managers.map(row => <tr key={row.entry}><td>{data.cohort === "legacy" ? <>{formatRank(row.typical_rank)}<small>{row.seasons} seasons · {row.top10k_seasons}× top 10k</small></> : data.cohort === "youtubers" ? formatRank(row.overall_rank) : row.rank}</td><td><a href={row.fpl_url} target="_blank" rel="noreferrer"><strong>{row.name}</strong></a><small>{row.team_name}{data.cohort === "legacy" ? ` · OR ${formatRank(row.overall_rank)}` : ""}</small></td><td><strong>{row.total}</strong></td><td>{row.event_points}{row.hits ? <small>−{row.hits}</small> : null}</td><td>{row.captain_name ?? "–"}</td><td>{row.chip ? FPL_CHIP_NAMES[row.chip] ?? row.chip : "–"}</td><td>{row.transfers.length ? row.transfers.map(t => `${t.out} → ${t.in}`).join(", ") : "–"}</td><td>{row.match.toFixed(0)}%</td><td>{row.shared}/15</td></tr>)}</tbody></table></div></section>}
      <p className="model-note">Public squads become visible only after each deadline, so this always shows the last round, never the next one. EO here is measured among the {label.label} managers.</p>
    </>}
    </>}
  </>;
}
