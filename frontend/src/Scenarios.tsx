import { useEffect, useState } from "react";
import type { Breakpoint, JournalEntry, ScenarioComparison, TeamResponse } from "@fplmodell/api-client";
import { api } from "./api";
import { Icon } from "./icons";
import { useWorkspace } from "./Workspace";

const pts = (v: number | null | undefined, signed = false) => v == null ? "–" : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}`;
const errorText = (e: unknown) => e instanceof Error ? e.message : "Request failed. Try again.";

/** P5 "Your assumptions": the user's chance of playing for named players, with reset. Sent with every calculation. */
export function Assumptions({ team }: { team: TeamResponse }) {
  const { constraints, setConstraints, options } = useWorkspace();
  const overrides = constraints.overrides ?? [];
  const [player, setPlayer] = useState(0);
  const [chance, setChance] = useState(50);
  const names = new Map([...options, ...team.squad].map(p => [p.id, p.name]));
  const set = (next: typeof overrides) => { const { overrides: _, ...rest } = constraints; setConstraints(next.length ? { ...rest, overrides: next } : rest); };
  return <section className="panel assumptions" aria-label="Your assumptions">
    <h2>Your assumptions</h2>
    <p className="section-copy">“What if he is benched?” Your chance of playing replaces FPL's for that player in every calculation until you reset it. It is kept in this browser only and never used for training.</p>
    <div className="requirement-editor">
      <label>Player<select value={player} onChange={e => setPlayer(Number(e.target.value))}><option value={0}>Choose…</option>{[...team.squad].sort((a, b) => a.name.localeCompare(b.name)).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Chance of playing (%)<input type="number" min="0" max="100" step="5" value={chance} onChange={e => setChance(Math.min(100, Math.max(0, Number(e.target.value))))} /></label>
      <button className="secondary" disabled={!player} onClick={() => set([...overrides.filter(o => o.player_id !== player), { player_id: player, chance: chance / 100 }])}>Set assumption</button>
    </div>
    {!!overrides.length && <ul className="requirement-list">{overrides.map(o => <li key={o.player_id}>{names.get(o.player_id) ?? `Player ${o.player_id}`}: {Math.round(o.chance * 100)}% chance of playing
      <button className="secondary" onClick={() => set(overrides.filter(x => x.player_id !== o.player_id))} aria-label={`Remove assumption for ${names.get(o.player_id)}`}>Remove</button></li>)}</ul>}
    {!!overrides.length && <button className="secondary" onClick={() => set([])}>Reset all assumptions</button>}
  </section>;
}

/** P5: hold vs plan A vs plan B on the same inputs, robustness across seeded scenarios, and the tipping point. */
export function ScenariosView({ team }: { team: TeamResponse }) {
  const workspace = useWorkspace();
  const [data, setData] = useState<ScenarioComparison | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [player, setPlayer] = useState(0);
  const [tip, setTip] = useState<Breakpoint | null>(null);
  const [tipping, setTipping] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    api.scenarios(team.session_id, workspace.constraints).then(r => { if (active) setData(r); })
      .catch(e => { if (active) setError(errorText(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workspace.signature]);
  const findTip = async () => {
    setTipping(true); setTip(null);
    try { setTip(await api.breakpoint(team.session_id, player, workspace.constraints)); } catch (e) { setError(errorText(e)); }
    finally { setTipping(false); }
  };
  return <section className="scenarios" aria-label="Scenarios">
    <header className="page-heading compact"><div className="page-heading-main"><span className="page-icon"><Icon.Compass size={22} /></span>
      <div><span className="eyebrow">Same horizon, same inputs</span><h1>Scenarios</h1><p>Hold against the best plan and the best alternative, and what would change the answer.</p></div></div></header>
    {error && <p role="alert">{error}</p>}
    {loading && <div className="loading"><span className="spinner" />Comparing plans across scenarios…</div>}
    {data && <div className="panel"><div className="table-scroll"><table className="analytics-table">
      <thead><tr><th scope="col">Plan</th><th scope="col">This week</th><th scope="col">Net points</th><th scope="col">vs hold</th><th scope="col">Hits</th><th scope="col">Bank after</th><th scope="col">FT after</th><th scope="col">Chosen in</th></tr></thead>
      <tbody>{data.plans.map(plan => <tr key={plan.name}>
        <th scope="row">{plan.name}</th>
        <td>{plan.first_week_out.length ? `${plan.first_week_out.join(", ")} → ${plan.first_week_in.join(", ")}` : "No transfer"}</td>
        <td>{pts(plan.net_points)}</td><td>{pts(plan.gain_vs_hold, true)}</td><td>{plan.hits}</td><td>£{plan.final_bank.toFixed(1)}m</td><td>{plan.free_transfers_after}</td>
        <td>{Math.round((data.robustness.chosen_share[plan.name] ?? 0) * 100)}% of scenarios</td>
      </tr>)}</tbody></table></div>
      <p className="model-note">{data.robustness.note} {data.robustness.scenarios} scenarios, seed {data.robustness.seed}.</p></div>}
    <Assumptions team={team} />
    <section className="panel" aria-label="Tipping point"><h2>What would change the plan?</h2>
      <div className="requirement-editor">
        <label>Player<select value={player} onChange={e => setPlayer(Number(e.target.value))}><option value={0}>Choose…</option>{[...workspace.options].filter(p => team.squad.some(s => s.id === p.id) || p.recommended_points > 3).sort((a, b) => a.name.localeCompare(b.name)).map(p => <option key={p.id} value={p.id}>{p.name} ({p.team})</option>)}</select></label>
        <button className="secondary" disabled={!player || tipping} onClick={() => void findTip()}>{tipping ? "Searching…" : "Find the tipping point"}</button>
      </div>
      {tip && <p className="tipping-point">{tip.message}</p>}
    </section>
  </section>;
}

/** U19: your recorded decisions, frozen before each deadline, with the outcome once the round is checked. */
export function JournalView({ team }: { team: TeamResponse }) {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.journal(team.session_id).then(r => setEntries(r.entries)).catch(e => setError(errorText(e))); }, [team.session_id]);
  return <section className="journal" aria-label="Decision journal">
    <header className="page-heading compact"><div className="page-heading-main"><span className="page-icon"><Icon.Star size={22} /></span>
      <div><span className="eyebrow">Frozen before each deadline</span><h1>Decision journal</h1><p>The advice, the alternatives and your choice as they stood, and what happened afterwards.</p></div></div></header>
    {error && <p role="alert">{error}</p>}
    {entries && !entries.length && <section className="panel"><p>No decisions recorded yet. Use “Record my decision” on the Overview before a deadline.</p></section>}
    {entries?.map(entry => <article className="panel journal-entry" key={entry.file}>
      <span className="eyebrow">GW{entry.event} · recorded {new Date(entry.recorded_at).toLocaleString()}{entry.counts ? "" : " · replaced by a later entry"}</span>
      <h2>{entry.choice.label}</h2>
      {entry.choice.note && <p>“{entry.choice.note}”</p>}
      <dl className="fact-list">
        <div><dt>Advice</dt><dd>{entry.advice.title}{entry.advice.out.length ? `: ${entry.advice.out.join(", ")} → ${entry.advice.in.join(", ")}` : ""} · captain {entry.advice.captain}</dd></div>
        <div><dt>Alternatives</dt><dd>{entry.alternatives.map(a => `${a.name} ${pts(a.net_points)}`).join(" · ") || "–"}</dd></div>
        <div><dt>Forecast</dt><dd>{entry.forecast_at ? new Date(entry.forecast_at).toLocaleString() : "unknown"}</dd></div>
        <div><dt>Outcome</dt><dd>{entry.outcome ? `Advised XI ${pts(entry.outcome.advised_xi_points)} · hold XI ${pts(entry.outcome.hold_xi_points)} points` : "After FPL checks the round"}</dd></div>
      </dl>
    </article>)}
  </section>;
}

/** U19: record your decision from the decision card. */
export function RecordDecision({ team }: { team: TeamResponse }) {
  const workspace = useWorkspace();
  const [choice, setChoice] = useState<JournalEntry["choice"]["kind"]>("follow");
  const [note, setNote] = useState("");
  const [state, setState] = useState("");
  const [open, setOpen] = useState(false);
  const save = async () => {
    setState("Saving…");
    try { await api.recordDecision(team.session_id, choice, note, workspace.constraints); setState("Recorded in your decision journal."); setNote(""); }
    catch (e) { setState(errorText(e)); }
  };
  return <details className="record-decision" onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}><summary>Record my decision</summary>
    {open && <><div className="requirement-editor">
      <label>My decision<select value={choice} onChange={e => setChoice(e.target.value as typeof choice)}><option value="follow">Follow the advice</option><option value="roll">Roll / no transfer</option><option value="other">Something else</option></select></label>
      <label>Note<input value={note} maxLength={500} onChange={e => setNote(e.target.value)} placeholder="Optional" /></label>
      <button className="secondary" onClick={() => void save()}>Save to journal</button>
    </div>
    {state && <p role="status">{state}</p>}</>}
  </details>;
}
