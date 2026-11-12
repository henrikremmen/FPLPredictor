import { useEffect, useState, type ReactNode } from "react";
import type { Breakpoint, Player, TeamResponse, ThisWeek as Week } from "@fplmodell/api-client";
import { CHIP_LABELS, type Chip, formatDeadline, formatMoney, formatPoints, fplChecklist } from "@fplmodell/shared";
import { api } from "./api";
import { Icon } from "./icons";
import { PlayerName, useWorkspace } from "./Workspace";
import { RecordDecision } from "./Scenarios";

type Target = "squad" | "strategy" | "scenarios" | "plan";
const chipName = (chip: string) => CHIP_LABELS[chip as Chip] ?? chip;
const names = (players: Array<{ name: string; price: number }>) => players.map(p => `${p.name} (${formatMoney(p.price)})`).join(", ");

/** Steps ticked off this round, per team and Gameweek. Browser only; a private window keeps them for the visit. */
function useDone(key: string) {
  const [done, setDone] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(key) ?? "[]"); } catch { return []; } });
  const toggle = (step: string) => setDone(current => {
    const next = current.includes(step) ? current.filter(s => s !== step) : [...current, step];
    try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* not persisted */ }
    return next;
  });
  return [done, toggle] as const;
}

function Step({ n, title, done, onToggle, children }: { n: number; title: string; done?: boolean; onToggle?: () => void; children: ReactNode }) {
  return <section className={`panel week-step${done ? " done" : ""}`} aria-labelledby={`week-step-${n}`}>
    <header><span className="week-step-number" aria-hidden="true">{done ? <Icon.Check size={14} /> : n}</span><h2 id={`week-step-${n}`}>{title}</h2>
      {onToggle && <label className="week-done"><input type="checkbox" checked={!!done} onChange={onToggle} /> Done</label>}</header>
    {children}
  </section>;
}

function Roster({ players }: { players: Player[] }) {
  return <ul className="week-roster">{players.map(p => <li key={p.id}>
    <span className={`position position-${p.position.toLowerCase()}`}>{p.bench_order ?? p.position}</span>
    <PlayerName id={p.id}>{p.name}</PlayerName>{p.role && <b className="week-role">{p.role}</b>}
    <small>{p.opponent}</small><span>{formatPoints(p.recommended_points)}</span></li>)}</ul>;
}

/** W1: what to do in FPL this week, in order, built from the same cached results as Strategy, Lineup, Chips and Scenarios. */
export function ThisWeek({ team, onNavigate }: { team: TeamResponse; onNavigate: (view: Target) => void }) {
  const workspace = useWorkspace();
  const [week, setWeek] = useState<Week | null>(null);
  const [error, setError] = useState("");
  const [tips, setTips] = useState<Breakpoint[]>([]);
  const [copied, setCopied] = useState("");
  const [done, toggle] = useDone(`fpl-this-week-v1-${team.entry_id}-${team.target_event}`);
  useEffect(() => {
    let active = true;
    setError(""); setTips([]);
    api.thisWeek(team.session_id, workspace.constraints).then(result => {
      if (!active) return;
      setWeek(result);
      // Tipping points for the player bought and the captain, loaded after the page shows (each is cached).
      const captain = result.lineup.starters.find(p => p.role === "C")?.id;
      const ids = [...new Set([result.buy[0]?.id, captain].filter((id): id is number => id != null))];
      void Promise.allSettled(ids.map(id => api.breakpoint(team.session_id, id, workspace.constraints)))
        .then(found => { if (active) setTips(found.flatMap(r => r.status === "fulfilled" ? [r.value] : [])); });
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Could not work out this week's plan."); });
    return () => { active = false; };
  }, [workspace.signature]);

  const copy = async () => {
    if (!week) return;
    try { await navigator.clipboard.writeText(fplChecklist(week).join("\n")); setCopied("Copied. Paste it wherever you keep notes, or follow it in FPL."); }
    catch { setCopied("Copying is blocked in this browser; the steps are listed above."); }
  };
  const s = week?.strategy;
  const rising = s ? s.price_alerts.targets_rising.filter(p => week!.buy.some(b => b.id === p.id)) : [];
  const shares = week?.robustness ? Object.entries(week.robustness.chosen_share).sort((a, b) => b[1] - a[1]) : [];
  const playNow = week?.chips.best_by_chip.filter(c => c.event === team.target_event && c.decision !== "HOLD" && c.decision !== "UNAVAILABLE") ?? [];
  const available = Object.entries(team.chip_status).filter(([, status]) => status.available);
  return <section className="this-week" aria-label="This week" aria-busy={!week && !error}>
    <header className="page-heading compact"><div className="page-heading-main"><span className="page-icon"><Icon.Check size={22} /></span>
      <div><span className="eyebrow">GW {team.target_event} · deadline {team.deadline ? formatDeadline(team.deadline) : "not published"}</span><h1>This week</h1>
        <p>Do these steps in FPL, in this order. The app never makes transfers for you.</p></div></div></header>
    <p className="import-note">{team.squad_source === "manual_override"
      ? "You corrected this squad by hand."
      : `Squad from your public FPL picks for GW${team.event}; transfers you made since that deadline are missing.`}
      {" "}<button className="link-button" onClick={() => onNavigate("squad")}>Correct squad, bank or free transfers</button></p>
    {error && <p className="workspace-warning" role="alert">{error}</p>}
    {!week && !error && <p className="section-copy">Working out this week's plan…</p>}
    {week && s && <>
      <Step n={1} title={s.transfer.title} done={done.includes("transfers")} onToggle={() => toggle("transfers")}>
        {week.sell.length ? <dl className="fact-list">
          <div><dt>Sell</dt><dd>{names(week.sell)}</dd></div>
          <div><dt>Buy</dt><dd>{names(week.buy)}</dd></div>
          <div><dt>Afterwards</dt><dd>{s.transfer.bank_after != null ? `£${s.transfer.bank_after.toFixed(1)}m in the bank` : "Bank unknown"} · {s.transfer.hit ? `−${s.transfer.hit} points hit` : "no hit"}</dd></div>
        </dl> : <p className="section-copy">No transfer this week. You keep {s.transfer.free_transfers_before} free transfer{s.transfer.free_transfers_before === 1 ? "" : "s"} for later.</p>}
        <dl className="fact-list">
          {s.transfer.roll_comparison?.gain_over_roll != null && <div><dt>Gain over rolling ({s.transfer.horizon} GW)</dt><dd>{formatPoints(s.transfer.roll_comparison.gain_over_roll)} planning points · {s.transfer.confidence} confidence</dd></div>}
          {shares.length > 0 && <div><dt>Across {week.robustness!.scenarios} sampled scenarios</dt><dd>{shares.map(([name, share]) => `${name} ${Math.round(share * 100)}%`).join(" · ")}</dd></div>}
        </dl>
        {rising.map(p => <p key={p.id} className="workspace-warning" role="status">{p.name} is close to a price rise ({Math.round(p.price_change_projected_percent ?? p.price_change_percent ?? 0)}%). If you are sure, buy before tonight's price update.</p>)}
        {s.transfer.warnings.map(w => <p key={w} className="model-note">{w}</p>)}
      </Step>
      <Step n={2} title={`Set the lineup (${week.lineup.formation})`} done={done.includes("lineup")} onToggle={() => toggle("lineup")}>
        <Roster players={week.lineup.starters} />
        <h3 className="week-subhead">Bench, in this order</h3>
        <Roster players={week.lineup.bench} />
        <p className="section-copy">XI and captain: {formatPoints(week.lineup.expected_total)} expected points. Including autosubs and the vice-captain: {formatPoints(week.lineup_value.expected_with_autosubs)}.</p>
      </Step>
      <Step n={3} title={`Captain ${s.captain.captain.name}`} done={done.includes("captain")} onToggle={() => toggle("captain")}>
        <p className="section-copy">Vice-captain {s.captain.vice_captain.name}. {s.captain.confidence === "close" ? "A close call" : `${formatPoints(s.captain.margin)} points clear`}: {s.captain.reason}</p>
      </Step>
      <Step n={4} title={playNow.length ? `Consider ${playNow.map(c => c.label).join(" or ")}` : "No chip this week"} done={done.includes("chip")} onToggle={() => toggle("chip")}>
        <p className="section-copy">{week.chips.recommendation}. {available.length
          ? `Available: ${available.map(([chip, status]) => `${chipName(chip)} (until GW${status.expires_after_gw})`).join(", ")}.`
          : "No chips left in this half."}</p>
      </Step>
      <Step n={5} title="What would change the plan">
        <ul className="week-list">
          {s.squad_health.flagged_starters.map(p => <li key={p.id}><PlayerName id={p.id}>{p.name}</PlayerName>: {p.news || "flagged by FPL"}</li>)}
          {tips.map(t => <li key={t.player_id}>{t.message}</li>)}
          <li>Check again after the press conferences, then press Refresh forecast.</li>
        </ul>
      </Step>
      {s.plan.weeks.length > 1 && <Step n={6} title="The weeks after">
        <ul className="week-list">{s.plan.weeks.slice(1).map(w => <li key={w.event}>GW{w.event}: {w.transfers_out.length ? `${w.transfers_out.join(", ")} → ${w.transfers_in.join(", ")}` : "roll"}{w.chip ? ` · ${chipName(w.chip)}` : ""}</li>)}</ul>
        <button className="link-button" onClick={() => onNavigate("plan")}>Open the multiweek plan</button>
      </Step>}
      <div className="decision-actions">
        <button className="primary" onClick={() => void copy()}><Icon.Check size={16} /> Copy to FPL</button>
        <a className="secondary button-link" href="https://fantasy.premierleague.com/transfers" target="_blank" rel="noreferrer">Open FPL transfers ↗</a>
        <a className="secondary button-link" href="https://fantasy.premierleague.com/my-team" target="_blank" rel="noreferrer">Open FPL pick team ↗</a>
        <button className="secondary" onClick={() => onNavigate("strategy")}>Compare the options</button>
      </div>
      {copied && <p role="status" className="section-copy">{copied}</p>}
      <RecordDecision team={team} />
    </>}
  </section>;
}
