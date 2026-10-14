import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { api } from './api';
import type { Player, PlayerConstraints, PlayerDetail, PlayerComparison, SnapshotChanges, TeamResponse, RefreshStatus } from './types';

const empty: PlayerConstraints = { locked_ids: [], excluded_ids: [] };
const value = (n: number | null | undefined) => n == null ? 'Unavailable' : n.toFixed(2);
const date = (s: string | null | undefined) => s ? new Date(s).toLocaleString() : 'Unknown';
const cash = (n: number) => `£${(n / 10).toFixed(1)}m`;
const errorText = (e: unknown) => e instanceof Error ? e.message : 'Request failed. Try again.';

export function teamRevision(team: TeamResponse) {
  return team.forecast_context?.revision ?? JSON.stringify([team.forecast_path, team.horizon, team.risk_profile, team.bank, team.free_transfers, team.squad]);
}
function readStored<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? fallback; } catch { return fallback; }
}
interface SavedPlan {
  id: string; name: string; kind: string; created: string; revision: string; signature: string;
  event: number; horizon: number; risk: string; bank: number; freeTransfers: number;
  squad?: Player[]; forecastAt?: string | null;
  constraints: PlayerConstraints; summary: string; metrics: Record<string, string | number>;
  details: unknown;
}
interface WorkspaceState {
  constraints: PlayerConstraints;
  setConstraints: (c: PlayerConstraints) => void;
  signature: string;
  inspect: (id: number) => void;
  save: (plan: Omit<SavedPlan, 'id' | 'created' | 'revision' | 'signature' | 'event' | 'horizon' | 'risk' | 'bank' | 'freeTransfers' | 'constraints'>, signature: string) => void;
  plans: SavedPlan[];
  remove: (id: string) => void;
  rename: (id: string, name: string) => void;
  options: Player[];
  optionsError: string;
}
const WorkspaceContext = createContext<WorkspaceState | null>(null);
export function useWorkspace() {
  const state = useContext(WorkspaceContext);
  if (!state) throw new Error('Decision workspace is not available.');
  return state;
}
export function PlayerName({ id, children }: { id: number; children: ReactNode }) {
  const { inspect } = useWorkspace();
  return <button className="player-link" onClick={() => inspect(id)}>{children}</button>;
}

export function WorkspaceProvider({ team, children }: { team: TeamResponse; children: ReactNode }) {
  const key = `fpl-workspace-v1-${team.entry_id}`;
  const [constraints, setConstraintsState] = useState<PlayerConstraints>(() => {
    const stored = readStored<PlayerConstraints>(`${key}-constraints`, empty);
    return Array.isArray(stored.locked_ids) && Array.isArray(stored.excluded_ids) ? stored : empty;
  });
  const [plans, setPlans] = useState<SavedPlan[]>(() => {
    const stored = readStored<SavedPlan[]>(`${key}-plans`, []);
    return Array.isArray(stored) ? stored.filter(p => p && p.id && p.metrics && p.constraints) : [];
  });
  const [storageError, setStorageError] = useState('');
  const [notice, setNotice] = useState('');
  const [inspected, inspect] = useState<number | null>(null);
  const [options, setOptions] = useState<Player[]>([]);
  const [optionsError, setOptionsError] = useState('');
  const signature = JSON.stringify([teamRevision(team), constraints]);
  useEffect(() => {
    let active = true;
    setOptionsError('');
    api.squadOptions(team.session_id).then(r => { if (active) setOptions(r.players); })
      .catch(e => { if (active) setOptionsError(errorText(e)); });
    return () => { active = false; };
  }, [team.session_id, team.forecast_path]);
  const persist = (suffix: string, data: unknown) => {
    try { localStorage.setItem(`${key}-${suffix}`, JSON.stringify(data)); setStorageError(''); }
    catch { setStorageError('Browser storage is unavailable or full. These changes will last only until you close this page.'); }
  };
  const setConstraints = (c: PlayerConstraints) => { setConstraintsState(c); persist('constraints', c); };
  const updatePlans = (next: SavedPlan[]) => { setPlans(next); persist('plans', next); };
  const save: WorkspaceState['save'] = (plan, resultSignature) => {
    if (resultSignature !== signature) { setNotice('Recalculate this outdated result before saving it.'); return; }
    const record = { ...plan, id: crypto.randomUUID(), created: new Date().toISOString(), revision: teamRevision(team), signature,
      event: team.target_event, horizon: team.horizon, risk: team.risk_profile, bank: team.bank, freeTransfers: team.free_transfers,
      squad: team.squad.map(p => ({ ...p })), forecastAt: team.forecast_context?.forecast_at,
      constraints: { locked_ids: [...constraints.locked_ids], excluded_ids: [...constraints.excluded_ids] } };
    updatePlans([...plans, record]); setNotice(`Saved “${plan.name}”. Open Saved plans to compare alternatives.`);
  };
  return <WorkspaceContext.Provider value={{ constraints, setConstraints, signature, inspect, save, plans,
    remove: id => updatePlans(plans.filter(p => p.id !== id)),
    rename: (id, name) => updatePlans(plans.map(p => p.id === id ? { ...p, name: name.trim() || p.name } : p)),
    options, optionsError }}>
    {storageError && <p className="workspace-warning" role="alert">{storageError}</p>}
    {notice && <div className="workspace-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss saved plan notice">×</button></div>}
    {(constraints.locked_ids.length > 0 || constraints.excluded_ids.length > 0) && <p className="workspace-context">Player preferences active: {constraints.locked_ids.length} locked · {constraints.excluded_ids.length} excluded. Manage them in Player preferences.</p>}
    {children}
    {inspected != null && <PlayerInspector key={`${inspected}-${teamRevision(team)}`} team={team} id={inspected} close={() => inspect(null)} />}
  </WorkspaceContext.Provider>;
}

export function ResultStatus({ signature }: { signature: string }) {
  const workspace = useWorkspace();
  return signature && signature !== workspace.signature
    ? <p className="workspace-warning" role="status">Outdated result: forecast, squad, finances or player preferences have changed. Recalculate before using this advice.</p> : null;
}
export function SavePlan({ kind, summary, metrics, details, signature }: {
  kind: string; summary: string; metrics: Record<string, string | number>; details: unknown; signature: string;
}) {
  const workspace = useWorkspace();
  const [name, setName] = useState('');
  return <div className="save-plan"><input aria-label={`Name for ${kind} plan`} placeholder="Plan name (e.g. Plan A)" value={name} maxLength={100} onChange={e => setName(e.target.value)} />
    <button className="secondary" disabled={signature !== workspace.signature} onClick={() => workspace.save({ name: name.trim() || `${kind} ${workspace.plans.length + 1}`, kind, summary, metrics, details }, signature)}>Save plan</button></div>;
}

export function Preferences({ team }: { team: TeamResponse }) {
  const { constraints, setConstraints, options, optionsError } = useWorkspace();
  const [query, setQuery] = useState('');
  const owned = new Set(team.squad.map(p => p.id));
  const names = new Map([...options, ...team.squad].map(p => [p.id, p.name]));
  const toggle = (id: number, field: keyof PlayerConstraints) => {
    const other = field === 'locked_ids' ? 'excluded_ids' : 'locked_ids';
    setConstraints({ ...constraints, [field]: constraints[field].includes(id) ? constraints[field].filter(i => i !== id) : [...constraints[field], id],
      [other]: constraints[other].filter(i => i !== id) });
  };
  return <section className="panel workspace-preferences"><h2>Player preferences</h2>
    <p>Locks keep owned players in every proposed squad. Exclusions remove players from proposed squads, including owned players. Applied to transfers, market suggestions, multiweek plans and FH/WC optimisation. They do not change your actual squad or its current lineup.</p>
    {optionsError && <p role="alert">{optionsError}</p>}
    <div className="preference-tags">{(['locked_ids', 'excluded_ids'] as const).flatMap(field => constraints[field].map(id => <button className="secondary" key={`${field}-${id}`} onClick={() => toggle(id, field)}>{field === 'locked_ids' ? 'Locked' : 'Excluded'}: {names.get(id) ?? `Player ${id}`} ×</button>))}</div>
    {!!constraints.locked_ids.length && constraints.locked_ids.some(id => !owned.has(id)) && <p className="workspace-warning">A locked player is no longer owned. Remove that lock before calculating.</p>}
    <label>Find a player to lock or exclude<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search by player or club" /></label>
    <div className="preference-list">{(query ? options.filter(p => `${p.name} ${p.team}`.toLowerCase().includes(query.toLowerCase())).slice(0, 30) : team.squad).map(p => <div key={p.id}><PlayerName id={p.id}>{p.name}</PlayerName><small>{p.position} · {p.team}</small>
      {owned.has(p.id) && <button className="secondary" aria-pressed={constraints.locked_ids.includes(p.id)} onClick={() => toggle(p.id, 'locked_ids')}>{constraints.locked_ids.includes(p.id) ? 'Unlock' : 'Lock'}</button>}
      <button className="secondary" aria-pressed={constraints.excluded_ids.includes(p.id)} onClick={() => toggle(p.id, 'excluded_ids')}>{constraints.excluded_ids.includes(p.id) ? 'Include again' : 'Exclude'}</button></div>)}</div>
    <button className="secondary" onClick={() => setConstraints(empty)}>Clear preferences</button>
  </section>;
}

export function SinceLastTime({ team }: { team: TeamResponse }) {
  const [data, setData] = useState<SnapshotChanges | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    setData(null); setError('');
    api.changes(team.session_id).then(r => { if (active) setData(r); }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [team.session_id, teamRevision(team)]);
  const labels: Record<string, string> = { news: 'Team news', status: 'FPL status', availability: 'Playing chance', price: 'Price', opponent: 'Fixtures', recommended_points: `Expected points (${team.horizon} GW)` };
  const format = (field: string, v: string | number | null) => v == null || v === '' ? 'None reported' : field === 'price' ? cash(Number(v)) : field === 'availability' ? `${Math.round(Number(v) * 100)}%` : field === 'recommended_points' ? value(Number(v)) : String(v);
  return <section className="panel since-last"><h2>Since last time</h2>
    {error ? <p role="alert">{error}</p> : !data ? <p role="status">Comparing saved forecasts…</p> : <>
      <p>{data.message}</p>{data.previous_at && <small>{date(data.previous_at)} → {date(data.current_at)}</small>}
      {data.previous_at && !data.changes.length && <p>No material changes for your current squad.</p>}
      {data.changes.map(p => <article key={p.id}><h3><PlayerName id={p.id}>{p.name}</PlayerName></h3>{Object.entries(p.fields).map(([field, diff]) => <p key={field}><strong>{labels[field] ?? field}:</strong> {format(field, diff.before)} → {format(field, diff.after)}</p>)}</article>)}
      <a href="https://fantasy.premierleague.com/api/bootstrap-static/" target="_blank" rel="noreferrer">Official FPL source</a>
    </>}
  </section>;
}

function PlayerInspector({ team, id, close }: { team: TeamResponse; id: number; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [detail, setDetail] = useState<PlayerDetail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const focused = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => { focused?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    api.player(team.session_id, id).then(r => { if (active) setDetail(r); }).catch(e => { if (active) setError(errorText(e)); });
    return () => { active = false; };
  }, [team.session_id, id]);
  const probability = (n: number | undefined) => n == null ? 'Unavailable' : `${(n * 100).toFixed(0)}%`;
  return <dialog className="player-dialog" ref={dialog} onCancel={close} aria-labelledby="player-title">
    <button className="secondary dialog-close" onClick={close} aria-label="Close player details">Close</button>
    <h2 id="player-title">{detail?.player.name ?? 'Player details'}</h2>
    {error ? <p role="alert">{error}</p> : !detail ? <p role="status">Loading player details…</p> : <>
      <p>{detail.player.team} · {detail.player.position} · {cash(detail.player.price)} · {team.horizon} GW</p>
      <div className="workspace-metrics"><span>Expected points<strong>{value(detail.player.recommended_points)}</strong></span><span>Decision score ({team.risk_profile})<strong>{value(detail.player.decision_points)}</strong></span><span>FPL playing chance<strong>{probability(detail.player.availability)}</strong></span></div>
      <h3>Team news</h3><p>{detail.player.news || 'No current FPL news reported.'}</p><small>News timestamp: {date(detail.news_added)}</small>
      <h3>Fixtures and expected points</h3><div className="table-scroll"><table><thead><tr><th>GW</th><th>Opponent</th><th>Expected points</th><th>Decision score</th></tr></thead><tbody>{detail.weeks.map(w => <tr key={w.forecast_event}><td>{w.forecast_event}</td><td>{w.opponent}</td><td>{value(w.recommended_points)}</td><td>{value(w.decision_points)}</td></tr>)}</tbody></table></div>
      <h3>Playing time and uncertainty per fixture</h3><p>{detail.minutes_note}</p>
      <div className="table-scroll"><table><thead><tr><th>GW</th><th>Kickoff</th><th>No minutes</th><th>1–59 min</th><th>60+ min</th><th>Q10–Q90 points</th></tr></thead><tbody>{detail.fixtures.map((f, i) => <tr key={i}><td>{f.GW}</td><td>{date(f.kickoff_time)}</td><td>{probability(f.p_zero_minutes)}</td><td>{probability(f.p_1_59_minutes)}</td><td>{probability(f.p_60plus_minutes)}</td><td>{value(f.prediction_q10)} – {value(f.prediction_q90)}</td></tr>)}</tbody></table></div>
      {!detail.fixtures.length && <p>Fixture-level probabilities are unavailable in this snapshot.</p>}
      <p>{detail.uncertainty_note}</p><p>Current recommendations retain the same FPL availability adjustment across future gameweeks.</p>
      {!!detail.injury_scenarios?.length && <section aria-label="Return-date scenario">
        <h3>Return-date scenario</h3>
        <p>FPL reports an expected return on {date(detail.injury_scenarios[0].reported_return)}. The scenario below removes the extra injury adjustment for later rounds from that date. It is an assumption, not a calibrated recovery probability or a guaranteed start. Current recommendations use the conservative column.</p>
        <div className="table-scroll"><table><thead><tr><th>GW</th><th>Kickoff</th><th>Conservative points</th><th>If back as reported</th></tr></thead>
          <tbody>{detail.injury_scenarios.map(s => <tr key={s.fixture}><td>{s.GW}</td><td>{date(s.kickoff_time)}</td><td>{value(s.conservative_points)}</td><td>{value(s.reported_return_points)}</td></tr>)}</tbody></table></div>
      </section>}
      <p>Forecast: {date(detail.context.forecast_at)}<br />Source snapshot: {date(detail.context.observed_at)}<br />Player news and prices checked: {date(detail.context.player_data_at)}</p>
      <a href={detail.context.source_url} target="_blank" rel="noreferrer">Official FPL source</a>
    </>}
  </dialog>;
}

export function PlayerComparisonView({ team }: { team: TeamResponse }) {
  const workspace = useWorkspace();
  const [outId, setOut] = useState(0);
  const [inId, setIn] = useState(0);
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<PlayerComparison | null>(null);
  const [resultSignature, setResultSignature] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const outgoing = team.squad.find(p => p.id === outId);
  const owned = new Set(team.squad.map(p => p.id));
  const incoming = workspace.options.filter(p => p.position === outgoing?.position && !owned.has(p.id));
  const calculate = async () => {
    const signature = workspace.signature;
    setLoading(true); setError('');
    try { setResult(await api.compare(team.session_id, outId, inId, workspace.constraints)); setResultSignature(signature); }
    catch (e) { setError(errorText(e)); } finally { setLoading(false); }
  };
  return <><header className="page-heading"><div><span className="eyebrow">Keep or buy</span><h1>Player comparison</h1><p>Compare a legal transfer against keeping your squad over {team.horizon} gameweeks.</p></div></header>
    <section className="panel"><div className="comparison-controls"><label>Player to keep / sell<select value={outId} onChange={e => { setOut(Number(e.target.value)); setIn(0); }}><option value={0}>Choose an owned player</option>{team.squad.map(p => <option key={p.id} value={p.id}>{p.name} · {p.position} · sell {cash(p.selling_price ?? p.price)}</option>)}</select></label>
      <label>Search incoming players<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label>
      <label>Player to buy<select value={inId} onChange={e => setIn(Number(e.target.value))}><option value={0}>Choose a replacement</option>{incoming.filter(p => p.id === inId || `${p.name} ${p.team}`.toLowerCase().includes(query.toLowerCase())).map(p => <option key={p.id} value={p.id}>{p.name} · {p.team} · {cash(p.price)}</option>)}</select></label></div>
      <p>{outId > 0 && <PlayerName id={outId}>Inspect outgoing player</PlayerName>} {inId > 0 && <PlayerName id={inId}>Inspect incoming player</PlayerName>}</p>
      <button className="primary" disabled={!outId || !inId || loading} onClick={calculate}>{loading ? 'Comparing legal lineups…' : 'Compare after hits'}</button>
      {(error || workspace.optionsError) && <p role="alert">{error || workspace.optionsError}</p>}
    </section>
    {result && <section className="panel comparison-result" aria-busy={loading}><h2>{result.out} → {result.in}</h2><ResultStatus signature={resultSignature} />
      {(result.out_id !== outId || result.in_id !== inId) && <p className="workspace-warning">Selection changed. The result below is for {result.out} → {result.in}; compare again to update.</p>}
      {result.players && <div className="table-scroll"><table><thead><tr><th>Player</th><th>{result.out}</th><th>{result.in}</th></tr></thead><tbody>
        <tr><th>Club / position</th><td>{result.players.outgoing.team} · {result.players.outgoing.position}</td><td>{result.players.incoming.team} · {result.players.incoming.position}</td></tr>
        <tr><th>Sale / purchase price</th><td>{cash(result.players.outgoing.selling_price ?? result.players.outgoing.price)}</td><td>{cash(result.players.incoming.price)}</td></tr>
        <tr><th>Player expected points</th><td>{value(result.players.outgoing.recommended_points)}</td><td>{value(result.players.incoming.recommended_points)}</td></tr>
        <tr><th>Expected 60+ appearances</th><td>{value(result.players.outgoing.expected_60plus_appearances)}</td><td>{value(result.players.incoming.expected_60plus_appearances)}</td></tr>
        <tr><th>Upcoming fixtures</th><td>{result.players.outgoing.opponent}</td><td>{result.players.incoming.opponent}</td></tr>
        <tr><th>Team news</th><td>{result.players.outgoing.news || 'None reported'}</td><td>{result.players.incoming.news || 'None reported'}</td></tr>
      </tbody></table></div>}
      <div className="workspace-metrics"><span>Keep XI + captain<strong>{value(result.hold_points)}</strong></span><span>Buy XI + captain, before hit<strong>{value(result.buy_points)}</strong></span><span>Hit<strong>−{result.hit}</strong></span><span>Net expected gain<strong>{value(result.net_gain)}</strong></span><span>Bank after transfer<strong>{cash(result.bank_after)}</strong></span></div>
      <div className="table-scroll"><table><thead><tr><th>GW</th><th>Keep</th><th>Buy</th><th>Gain before hit</th></tr></thead><tbody>{result.weeks.map(w => <tr key={w.event}><td>{w.event}</td><td>{value(w.hold)}</td><td>{value(w.buy)}</td><td>{value(w.gain)}</td></tr>)}</tbody></table></div>
      <p>{result.caveat}</p><SavePlan kind="Comparison" summary={`${result.out} → ${result.in}`} metrics={{ 'Keep expected points': result.hold_points, 'Buy expected points before hit': result.buy_points, 'Hit': result.hit, 'Net expected gain': result.net_gain, 'Bank after (£m)': result.bank_after / 10 }} details={result} signature={resultSignature} />
    </section>}
  </>;
}

export function SavedPlans({ team }: { team: TeamResponse }) {
  const workspace = useWorkspace();
  const [selected, setSelected] = useState<string[]>([]);
  const plans = workspace.plans.filter(p => selected.includes(p.id));
  const comparable = plans.length === 2 && plans[0].signature === plans[1].signature && plans[0].kind === plans[1].kind
    && plans[0].metrics['Gain baseline'] === plans[1].metrics['Gain baseline']
    && plans[0].metrics['Evaluation window'] === plans[1].metrics['Evaluation window'];
  const fields = [...new Set(plans.flatMap(p => Object.keys(p.metrics)))];
  return <><header className="page-heading"><div><span className="eyebrow">Saved locally for {team.team_name}</span><h1>Saved plans</h1><p>Choose two plans to compare. Saved results retain their original inputs and never change your FPL squad.</p></div></header>
    {!workspace.plans.length && <section className="panel"><p>Save alternatives from transfers, player comparison, multiweek plans or chip analysis.</p></section>}
    <div className="saved-plan-list">{workspace.plans.map(p => <article className="panel" key={p.id}>
      <label>Plan name<input value={p.name} maxLength={100} onChange={e => workspace.rename(p.id, e.target.value)} /></label><p>{p.kind} · {p.summary}</p><small>{date(p.created)} · GW{p.event} · {p.horizon} GW · {p.risk}</small>
      <ResultStatus signature={p.signature} />
      <div className="saved-actions"><button className="secondary" aria-pressed={selected.includes(p.id)} disabled={selected.length === 2 && !selected.includes(p.id)} onClick={() => setSelected(ids => ids.includes(p.id) ? ids.filter(id => id !== p.id) : [...ids, p.id])}>{selected.includes(p.id) ? 'Selected for comparison' : 'Compare A/B'}</button><button className="secondary" onClick={() => { workspace.remove(p.id); setSelected(ids => ids.filter(id => id !== p.id)); }}>Delete</button></div>
      <details><summary>Saved plan and assumptions</summary><p>Bank: {cash(p.bank)} · {p.freeTransfers} FT · Locked: {p.constraints.locked_ids.join(', ') || 'None'} · Excluded: {p.constraints.excluded_ids.join(', ') || 'None'}</p><p>Forecast: {date(p.forecastAt)}<br />Original squad: {p.squad?.map(player => player.name).join(", ") ?? "Not recorded"}</p><PlanDetails data={p.details} /></details>
    </article>)}</div>
    {plans.length > 0 && <section className="panel"><h2>Plan A / B</h2>{plans.length === 2 && !comparable && <p className="workspace-warning">These plans use different inputs or analysis types. Values are shown for reference; their scores are not directly comparable.</p>}
      <div className="table-scroll"><table><thead><tr><th>Measure</th>{plans.map(p => <th key={p.id}>{p.name}</th>)}{comparable && <th>B − A</th>}</tr></thead><tbody>
        <tr><th>Decision</th>{plans.map(p => <td key={p.id}>{p.summary}</td>)}{comparable && <td>—</td>}</tr>
        {fields.map(field => <tr key={field}><th>{field}</th>{plans.map(p => <td key={p.id}>{typeof p.metrics[field] === 'number' ? value(p.metrics[field] as number) : p.metrics[field] ?? '—'}</td>)}{comparable && <td>{typeof plans[0].metrics[field] === 'number' && typeof plans[1].metrics[field] === 'number' ? value(Number(plans[1].metrics[field]) - Number(plans[0].metrics[field])) : '—'}</td>}</tr>)}
      </tbody></table></div></section>}
  </>;
}
function PlanDetails({ data }: { data: unknown }) {
  if (data == null) return <span>—</span>;
  if (Array.isArray(data)) return <ul>{data.map((item, i) => <li key={i}><PlanDetails data={item} /></li>)}</ul>;
  if (typeof data === 'object') return <dl className="plan-details">{Object.entries(data).filter(([key]) => key !== 'context').map(([key, v]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd><PlanDetails data={v} /></dd></div>)}</dl>;
  return <span>{typeof data === 'number' ? (Number.isInteger(data) ? data : data.toFixed(2)) : String(data)}</span>;
}

export function ForecastStatus({ team, refreshing }: { team: TeamResponse | null; refreshing: boolean }) {
  const [status, setStatus] = useState<RefreshStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [pollError, setPollError] = useState(false);
  useEffect(() => {
    if (!refreshing) return;
    let active = true;
    const started = Date.now();
    const poll = async () => {
      try { const next = await api.refreshStatus(); if (active) { setStatus(next); setPollError(false); } }
      catch { if (active) setPollError(true); }
      if (active) setElapsed(Math.floor((Date.now() - started) / 1000));
    };
    setStatus(null); setElapsed(0); void poll();
    const timer = window.setInterval(poll, 2000);
    return () => { active = false; clearInterval(timer); };
  }, [refreshing]);
  const stamp = team?.forecast_context?.forecast_at;
  const old = stamp ? Date.now() - new Date(stamp).getTime() > 24 * 3600 * 1000 : true;
  return <section className="forecast-status" aria-live="polite" aria-busy={refreshing}>
    {refreshing ? <><strong>{status?.stage ?? 'Starting forecast update'} · {elapsed}s</strong>
      <progress value={status?.total && status.captured < status.total ? status.captured : undefined} max={status?.total ?? 1} />
      <span>{status?.captured ? `${status.captured}${status.total ? ` / ${status.total}` : ''} player histories received. ` : ''}Previous results remain visible until the update succeeds.</span>
      {pollError && <span>Progress temporarily unavailable; the update request is still running.</span>}</> : team ? <><strong>Forecast updated {date(stamp)}</strong><span>Player news and prices checked {date(team.forecast_context?.player_data_at)}</span><span>{old ? 'Forecast age is unknown or over 24 hours. Refresh before acting.' : 'Check for late team news before the deadline.'}</span></> : null}
  </section>;
}
