import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { Icon } from "./icons";
import type {
  ChipCandidate,
  ChipStrategy,
  MultiweekPlan,
  ManagerAnalytics,
  AnalyticsTimelineRow,
  AnalyticsDecisionPlayer,
  RelativeImpact,
  Player,
  Position,
  RecommendedSquads,
  RiskProfile,
  SquadSelection,
  StrategyAdvice,
  StrategyPlayer,
  TeamResponse,
  TransferResponse,
} from "./types";

type View = "overview" | "analysis" | "squad" | "strategy" | "lineup" | "transfers" | "plan" | "squads" | "chips" | "market";

const DEFAULT_TEAM = "https://fantasy.premierleague.com/en/entry/5139814/event/4";
const VIEWS: Array<{ id: View; label: string; icon: typeof Icon.Home }> = [
  { id: "overview", label: "Oversikt", icon: Icon.Home },
  { id: "analysis", label: "Analyse", icon: Icon.Chart },
  { id: "squad", label: "Korriger lag", icon: Icon.Edit },
  { id: "strategy", label: "Strategisenter", icon: Icon.Compass },
  { id: "lineup", label: "Laguttak", icon: Icon.Formation },
  { id: "transfers", label: "Bytter", icon: Icon.Swap },
  { id: "plan", label: "Flerukersplan", icon: Icon.Trend },
  { id: "squads", label: "FH / WC-lag", icon: Icon.Shield },
  { id: "chips", label: "Chips", icon: Icon.Zap },
  { id: "market", label: "Marked", icon: Icon.Search },
];

function PageHeading({ view, eyebrow, title, subtitle, action, right }: {
  view: View; eyebrow: string; title: string; subtitle?: string; action?: ReactNode; right?: ReactNode;
}) {
  const ViewIcon = VIEWS.find(item => item.id === view)?.icon ?? Icon.Home;
  return (
    <header className="page-heading">
      <div className="page-heading-main">
        <span className="page-icon"><ViewIcon size={22} /></span>
        <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
      </div>
      {right}
      {action}
    </header>
  );
}

const positionNames: Record<string, string> = {
  GK: "Keeper", DEF: "Forsvar", MID: "Midtbane", FWD: "Angrep",
};

function money(value: number | undefined) {
  return value == null ? "–" : `£${(value / 10).toFixed(1)}m`;
}

function moneyMillions(value: number | undefined) {
  return value == null ? "–" : `£${value.toFixed(1)}m`;
}

function points(value: number | undefined, signed = false) {
  if (value == null) return "–";
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}`;
}

function ErrorBanner({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="error-banner" role="alert">
      <span><Icon.Alert size={15} /></span><p>{message}</p><button onClick={onClose} aria-label="Lukk"><Icon.Close size={15} /></button>
    </div>
  );
}

function PlayerRow({ player, rank }: { player: Player; rank?: number }) {
  return (
    <div className="player-row">
      {rank != null && <span className="rank">{rank}</span>}
      <span className={`position position-${player.position.toLowerCase()}`}>{player.position}</span>
      <div className="player-name"><strong>{player.name}</strong><small>{player.team} · {player.opponent || "–"}</small></div>
      <span className="hide-mobile">{money(player.selling_price ?? player.price)}</span>
      <strong className="points">{points(player.decision_points ?? player.recommended_points)}</strong>
    </div>
  );
}

function Loading({ label }: { label: string }) {
  return <div className="loading"><span className="spinner" />{label}</div>;
}

function EmptyState() {
  return (
    <section className="empty-state">
      <div className="empty-mark"><Icon.Shield size={64} /></div>
      <h2>Last inn laget ditt</h2>
      <p>Lim inn en offentlig FPL-lenke i skjemaet for å komme i gang.</p>
    </section>
  );
}

function Overview({ team }: { team: TeamResponse }) {
  const best = [...team.squad].sort((a, b) => b.recommended_points - a.recommended_points)[0];
  return (
    <>
      <PageHeading view="overview" eyebrow={`GW ${team.target_event}`} title={team.team_name} subtitle={`${team.manager_name} · ${team.horizon} GW horisont`}
        right={<div className="deadline"><small>Deadline</small><strong>{team.deadline || "Ikke publisert"}</strong></div>} />
      <section className="metric-grid">
        <article><i className="metric-icon"><Icon.Star size={16} /></i><small>Forventet XI + kaptein</small><strong>{points(team.lineup.expected_total)}</strong><span>poeng i GW {team.target_event}</span></article>
        <article><i className="metric-icon"><Icon.Formation size={16} /></i><small>Formasjon</small><strong>{team.lineup.formation}</strong><span>modellens beste ellever</span></article>
        <article><i className="metric-icon"><Icon.Coins size={16} /></i><small>Bank</small><strong>{money(team.bank)}</strong><span>{team.free_transfers} gratisbytte{team.free_transfers === 1 ? "" : "r"}</span></article>
        <article><i className="metric-icon"><Icon.Target size={16} /></i><small>Høyest prognose</small><strong>{best?.name ?? "–"}</strong><span>{points(best?.recommended_points)} poeng</span></article>
      </section>
      <section className="panel">
        <div className="section-title"><div><span className="eyebrow">15 spillere</span><h2>Troppen din</h2></div><span className="legend">Modellpoeng <Icon.ArrowRight size={12} /></span></div>
        <div className="squad-groups">
          {(["GK", "DEF", "MID", "FWD"] as Position[]).map(position => (
            <div key={position} className="squad-group">
              <h3>{positionNames[position]}</h3>
              {team.squad.filter(p => p.position === position).sort((a, b) => b.recommended_points - a.recommended_points).map(player => <PlayerRow key={player.id} player={player} />)}
            </div>
          ))}
        </div>
      </section>
      <p className="model-note">Prognosene er modellestimater, ikke garantier. Kontroller særlig skader, bank og gratisbytter i FPL før deadline.</p>
    </>
  );
}

function PlayerCard({ player }: { player: Player }) {
  return (
    <div className={`pitch-player ${player.role ? "role-player" : ""}`}>
      {player.role && <span className="role-badge">{player.role}</span>}
      <span className="shirt">{player.position === "GK" ? "◆" : "⬟"}</span>
      <strong>{player.name}</strong>
      <small>{points(player.recommended_points)} · {player.opponent}</small>
    </div>
  );
}

function Lineup({ team }: { team: TeamResponse }) {
  const rows = (["GK", "DEF", "MID", "FWD"] as Position[]).map(position =>
    team.lineup.starters.filter(player => player.position === position),
  );
  return (
    <>
      <PageHeading view="lineup" eyebrow="Optimal XI" title="Laguttak" subtitle={`${team.lineup.formation} · ${points(team.lineup.expected_total)} forventet inkl. kaptein`} />
      <div className="lineup-layout">
        <section className="pitch" aria-label="Anbefalt startellever">
          <div className="pitch-lines" />
          {rows.map((row, index) => <div className="pitch-row" key={index}>{row.map(player => <PlayerCard key={player.id} player={player} />)}</div>)}
        </section>
        <aside className="bench panel">
          <span className="eyebrow">Benk</span><h2>Rekkefølge</h2>
          {team.lineup.bench.map((player, index) => (
            <div className="bench-row" key={player.id}><span>{player.position === "GK" ? "GK" : index}</span><div><strong>{player.name}</strong><small>{player.opponent}</small></div><b>{points(player.recommended_points)}</b></div>
          ))}
          <div className="captain-note"><span>C</span><p><strong>Kapteinsmargin {points(team.lineup.captain_margin)}</strong><br />Forskjellen til modellens nest beste kaptein.</p></div>
        </aside>
      </div>
    </>
  );
}

function Transfers({ team }: { team: TeamResponse }) {
  const [mode, setMode] = useState<"open" | "targeted">("open");
  const [number, setNumber] = useState(Math.min(2, Math.max(1, team.free_transfers)));
  const [selectedOut, setSelectedOut] = useState<number[]>([]);
  const [result, setResult] = useState<TransferResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selectedPlayers = team.squad.filter(player => selectedOut.includes(player.id));
  const transferCount = mode === "targeted" ? selectedOut.length : number;
  const chooseMode = (next: "open" | "targeted") => {
    setMode(next);
    setResult(null);
    setError("");
  };
  const togglePlayer = (playerId: number) => {
    setResult(null);
    setError("");
    setSelectedOut(current => {
      if (current.includes(playerId)) return current.filter(id => id !== playerId);
      if (current.length >= 5) {
        setError("Du kan velge maksimalt fem spillere som skal ut.");
        return current;
      }
      return [...current, playerId];
    });
  };
  const calculate = async () => {
    if (mode === "targeted" && selectedOut.length === 0) {
      setError("Velg minst én spiller du vil bytte ut.");
      return;
    }
    setLoading(true); setError("");
    try {
      setResult(await api.transfers(
        team.session_id,
        transferCount,
        mode === "targeted" ? selectedOut : [],
      ));
    }
    catch (err) { setError(err instanceof Error ? err.message : "Bytteberegningen feilet."); }
    finally { setLoading(false); }
  };
  const hit = Math.max(0, transferCount - team.free_transfers) * 4;
  return (
    <>
      <PageHeading view="transfers" eyebrow="Eksakt optimering" title="Bytteplan" subtitle={`Beste frie plan, eller velg opptil fem spillere å erstatte over ${team.horizon} GW.`} />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      <section className="transfer-mode panel">
        <div><h2>Hva vil du beregne?</h2></div>
        <div className="mode-toggle" aria-label="Type bytteberegning">
          <button className={mode === "open" ? "active" : ""} onClick={() => chooseMode("open")}>Beste frie plan</button>
          <button className={mode === "targeted" ? "active" : ""} onClick={() => chooseMode("targeted")}>Velg spillere ut</button>
        </div>
      </section>
      {mode === "targeted" && (
        <section className="transfer-player-picker panel">
          <div className="section-title"><div><span className="eyebrow">{selectedOut.length}/5 valgt</span><h2>Hvem vil du selge?</h2></div>{selectedOut.length > 0 && <button className="secondary compact" onClick={() => { setSelectedOut([]); setResult(null); }}>Nullstill</button>}</div>
          <div className="transfer-player-grid">
            {team.squad.map(player => {
              const selected = selectedOut.includes(player.id);
              return (
                <button key={player.id} className={selected ? "selected" : ""} onClick={() => togglePlayer(player.id)} aria-pressed={selected}>
                  <span className={`position position-${player.position.toLowerCase()}`}>{player.position}</span>
                  <span><strong>{player.name}</strong><small>{player.team} · {player.opponent}</small></span>
                  <b>{points(player.decision_points ?? player.recommended_points)}</b>
                  <i>{selected ? <Icon.Check size={13} /> : <Icon.Plus size={13} />}</i>
                </button>
              );
            })}
          </div>
        </section>
      )}
      <section className="transfer-control panel">
        <div><h2>{mode === "targeted" ? `${transferCount || "Ingen"} spiller${transferCount === 1 ? "" : "e"} valgt` : "Hvor mange bytter?"}</h2><p>{team.free_transfers} estimerte gratisbytter · analyse over {team.horizon} GW.</p></div>
        {mode === "open" ? <div className="number-picker" aria-label="Antall bytter">{[1, 2, 3, 4, 5].map(value => <button className={number === value ? "active" : ""} onClick={() => { setNumber(value); setResult(null); }} key={value}>{value}</button>)}</div> : <div className="selected-out-summary">{selectedPlayers.map(player => <span key={player.id}>{player.name}</span>)}</div>}
        <div className={`hit-pill ${hit ? "has-hit" : ""}`}>{hit ? `−${hit} poeng hit` : "Ingen hit"}</div>
        <button className="primary" onClick={calculate} disabled={loading || transferCount === 0}>{loading ? "Beregner…" : mode === "targeted" ? "Finn beste erstattere" : "Finn beste plan"}</button>
      </section>
      {loading && <Loading label="Søker gjennom lovlige tropper…" />}
      {result && !loading && (
        <section className="results">
          <div className="section-title"><div><span className="eyebrow">{result.global_optimum ? "Globalt optimum" : "Rangerte alternativer"}</span><h2>{result.outgoing_ids.length ? "Beste erstattere for de valgte spillerne" : "Anbefalt plan"}</h2></div></div>
          {result.plans.length === 0 ? <p className="panel">Fant ingen lovlig plan for dette valget og budsjettet.</p> : result.plans.map((plan, index) => (
            <article className={`transfer-plan ${index === 0 ? "best-plan" : ""}`} key={`${plan.out}-${plan.in}-${index}`}>
              <div className="plan-rank">{index + 1}</div>
              <div className="moves"><div><small>UT</small><strong>{plan.out}</strong></div><span>→</span><div><small>INN</small><strong>{plan.in}</strong></div></div>
              <div className="plan-stats"><div><small>Netto gevinst</small><strong className={plan.net_gain >= 0 ? "positive" : "negative"}>{points(plan.net_gain, true)}</strong></div><div><small>Hit</small><strong>{plan.hit ? `−${plan.hit}` : "0"}</strong></div><div><small>Igjen</small><strong>{moneyMillions(plan.money_left)}</strong></div></div>
            </article>
          ))}
          <p className="model-note">Netto gevinst er forskjellen mot å beholde dagens lag over {team.horizon} GW, etter eventuelle poengtrekk. En negativ verdi betyr at modellen helst ville beholdt spilleren, men viser fortsatt beste lovlige erstatning.</p>
        </section>
      )}
    </>
  );
}

function Multiweek({ team }: { team: TeamResponse }) {
  const [plan, setPlan] = useState<MultiweekPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const calculate = async () => {
    setLoading(true); setError("");
    try { setPlan(await api.plan(team.session_id, team.horizon)); }
    catch (err) { setError(err instanceof Error ? err.message : "Planleggingen feilet."); }
    finally { setLoading(false); }
  };
  return (
    <>
      <PageHeading view="plan" eyebrow="Global optimering" title="Flerukersplan" subtitle={`Bytter, startellever og kaptein samlet over ${team.horizon} GW.`}
        action={<button className="primary" onClick={calculate} disabled={loading}>{loading ? "Planlegger…" : plan ? <><Icon.Refresh size={15} />Beregn på nytt</> : "Lag plan"}</button>} />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      {!plan && !loading && <section className="panel plan-intro"><h2>Se lenger enn neste deadline</h2><p>Håndhever budsjett, posisjoner, maks tre per klubb og rullende gratisbytter.</p></section>}
      {loading && <Loading label="Søker etter beste sekvens av tropper og bytter…" />}
      {plan && !loading && <>
        <section className="metric-grid"><article><small>Planlagt total</small><strong>{points(plan.total_projected_points)}</strong><span>før usikkerhet</span></article><article><small>Horisont</small><strong>{plan.weeks.length} GW</strong><span>{plan.global_optimum ? "globalt optimum bevist" : "beste plan funnet innen tidsgrensen"}</span></article></section>
        <div className="plan-timeline">{plan.weeks.map(week => <article className="panel plan-week" key={week.event}>
          <div className="plan-week-head"><div><span className="eyebrow">GW {week.event}</span><h2>{week.formation}</h2></div><strong>{points(week.projected_points)}</strong></div>
          <div className="plan-moves"><div><small>UT</small><b>{week.transfers_out.join(", ") || "Ingen"}</b></div><span>→</span><div><small>INN</small><b>{week.transfers_in.join(", ") || "Ingen"}</b></div></div>
          <p><strong>Kaptein:</strong> {week.captain} · <strong>Bank:</strong> £{week.bank.toFixed(1)}m · <strong>FT:</strong> {week.free_transfers_before}{week.hit ? ` · Hit: −${week.hit}` : ""}</p>
          <details><summary>Vis startellever</summary><p>{week.starters.join(" · ")}</p></details>
        </article>)}</div>
        <p className="model-note">{plan.caveat} Dette er en beslutningsstøtteplan, ikke en garanti.</p>
      </>}
    </>
  );
}

function decisionText(decision: ChipCandidate["decision"]) {
  return { PLAY: "Spill", CONSIDER: "Vurder", HOLD: "Hold", UNAVAILABLE: "Utilgjengelig" }[decision];
}

function Chips({ team }: { team: TeamResponse }) {
  const [strategy, setStrategy] = useState<ChipStrategy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const calculate = async () => {
    setLoading(true); setError("");
    try { setStrategy(await api.chips(team.session_id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Chipanalysen feilet."); }
    finally { setLoading(false); }
  };
  return (
    <>
      <PageHeading view="chips" eyebrow="Regelbevisst scenariotest" title="Chipstrategi" subtitle="Verdsetter chipene mot vanlig spill over kjent horisont."
        action={<button className="primary" onClick={calculate} disabled={loading}>{loading ? "Analyserer…" : strategy ? <><Icon.Refresh size={15} />Kjør på nytt</> : "Analyser chips"}</button>} />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      {!strategy && !loading && <section className="chip-intro panel"><div className="chip-symbol"><Icon.Zap size={34} /></div><div><h2>Finn verdien av hver chip</h2><p>Sammenligner Triple Captain, Bench Boost, Free Hit og Wildcard. Tar 10–20 sekunder.</p></div></section>}
      {loading && <Loading label="Optimaliserer chipscenarier og lovlige tropper…" />}
      {strategy && !loading && (
        <>
          <section className="chip-hero"><span className="eyebrow">Modellens førstevalg</span><h2>{strategy.recommendation}</h2><p>{strategy.summary}</p><div className="horizon-warning">Kun {strategy.forecast_events.length} kjente GW-er: dette er en kortsiktig vurdering, ikke en garanti for beste tidspunkt i hele halvåret.</div></section>
          <div className="chip-grid">
            {strategy.best_by_chip.map(candidate => (
              <article className="chip-card" key={candidate.chip}>
                <div className="chip-card-head"><span className="chip-name">{candidate.label}</span><span className={`decision decision-${candidate.decision.toLowerCase()}`}>{decisionText(candidate.decision)}</span></div>
                <div className="chip-gain"><strong>{points(candidate.gain, true)}</strong><span>modellpoeng mot normal plan</span></div>
                <dl><div><dt>Beste GW</dt><dd>{candidate.event}</dd></div><div><dt>Terskel</dt><dd>{candidate.threshold.toFixed(1)}</dd></div><div><dt>Bytter</dt><dd>{candidate.transfers_needed}</dd></div></dl>
                <p>{candidate.reason}</p>
                {(candidate.double_players > 0 || candidate.blank_players > 0) && <small>{candidate.double_players} dobbelspillere · {candidate.blank_players} blanke</small>}
              </article>
            ))}
          </div>
          <details className="research-note panel"><summary><Icon.Info size={14} /> Hvordan vurderingen brukes</summary><p>Bench Boost favoriserer en sterk benk og doble kamper, Triple Captain en tydelig kapteinstopp, Free Hit store blank-/dobbelrunder og Wildcard varig gevinst over flere runder. Bare én chip kan brukes per Gameweek.</p><p><a href="https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627" target="_blank" rel="noreferrer">Offisielle chipregler 2026/27 ↗</a> · <a href="https://www.premierleague.com/en/news/4685105" target="_blank" rel="noreferrer">Premier Leagues ekspertstrategier ↗</a></p></details>
        </>
      )}
    </>
  );
}

function SquadPanel({ title, selection }: { title: string; selection: SquadSelection }) {
  return (
    <section className="panel squad-recommendation">
      <div className="section-title"><div><span className="eyebrow">GW {selection.event}</span><h2>{title}</h2></div><strong className="selection-points">{points(selection.projected_points)}</strong></div>
      <div className="selection-meta"><span>{selection.formation}</span><span>C {selection.captain}</span><span>VC {selection.vice_captain}</span><span>£{selection.money_left.toFixed(1)}m igjen</span></div>
      <div className="squad-groups compact-groups">
        {(["GK", "DEF", "MID", "FWD"] as Position[]).map(position => (
          <div key={position} className="squad-group"><h3>{positionNames[position]}</h3>
            {selection.squad.filter(player => player.position === position).map(player => <PlayerRow player={player} key={player.id} />)}
          </div>
        ))}
      </div>
      <details><summary>Vis XI og benk</summary><p><strong>Start:</strong> {selection.starters.map(player => player.name).join(" · ")}</p><p><strong>Benk:</strong> {selection.bench.map(player => player.name).join(" · ")}</p></details>
    </section>
  );
}

function RecommendedTeams({ team }: { team: TeamResponse }) {
  const [result, setResult] = useState<RecommendedSquads | null>(null);
  const [selectedEvent, setSelectedEvent] = useState(team.target_event);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const calculate = async () => {
    setLoading(true); setError("");
    try {
      const value = await api.recommendedSquads(team.session_id);
      setResult(value); setSelectedEvent(value.forecast_events[0]);
    } catch (err) { setError(err instanceof Error ? err.message : "Lagberegningen feilet."); }
    finally { setLoading(false); }
  };
  const freeHit = result?.free_hit_by_event.find(selection => selection.event === selectedEvent);
  return (
    <>
      <PageHeading view="squads" eyebrow="Uavhengige chip-lag" title="Free Hit & Wildcard" subtitle="Beste Free Hit-lag per runde og et langsiktig Wildcard-lag."
        action={<button className="primary" onClick={calculate} disabled={loading}>{loading ? "Optimaliserer…" : result ? <><Icon.Refresh size={15} />Beregn på nytt</> : "Lag anbefalinger"}</button>} />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      {!result && !loading && <section className="panel plan-intro"><h2>To forskjellige tidshorisonter</h2><p>Free Hit maksimerer valgt runde. Wildcard vekter nærmeste GW høyest med en rullerende bytteplan.</p></section>}
      {loading && <Loading label="Bygger lovlige 15-mannstropper, XI, kaptein og bytteplan…" />}
      {result && !loading && <>
        <div className="gw-tabs">{result.forecast_events.map(event => <button className={event === selectedEvent ? "active" : ""} onClick={() => setSelectedEvent(event)} key={event}>FH GW{event}</button>)}</div>
        {freeHit && <SquadPanel title="Beste Free Hit-lag" selection={freeHit} />}
        <SquadPanel title={`Beste Wildcard-lag for GW${result.wildcard.horizon_events[0]}–${result.wildcard.horizon_events[result.wildcard.horizon_events.length - 1]}`} selection={result.wildcard} />
        <section className="panel wildcard-roadmap"><span className="eyebrow">Etter Wildcard</span><h2>Planlagte bytter</h2>
          {result.wildcard.roadmap.weeks.length === 0 ? <p>Ingen senere runder i prognosen.</p> : result.wildcard.roadmap.weeks.map(week => <div className="roadmap-row" key={week.event}><strong>GW{week.event}</strong><span>{week.transfers_out.join(", ") || "Hold"}</span><b>→</b><span>{week.transfers_in.join(", ") || "Ingen bytter"}</span><small>C {week.captain}</small></div>)}
        </section>
        <p className="model-note">{result.method} {result.caveat}</p>
      </>}
    </>
  );
}

function strategyPrice(player: StrategyPlayer) {
  const value = player.price_change_projected_percent ?? player.price_change_percent;
  if (value == null) return "–";
  return `${value > 0 ? "+" : ""}${value.toFixed(0)}%`;
}

function StrategyPlayerRow({ player, price = false }: { player: StrategyPlayer; price?: boolean }) {
  return (
    <div className="strategy-player-row">
      <span className={`position position-${player.position.toLowerCase()}`}>{player.position}</span>
      <div><strong>{player.name}</strong><small>{player.team} · {player.opponent} · {player.ownership == null ? "ukjent" : `${player.ownership.toFixed(1)}% eid`}</small></div>
      <b className={price && (player.price_change_projected_percent ?? 0) < 0 ? "negative" : "positive"}>{price ? strategyPrice(player) : points(player.points)}</b>
    </div>
  );
}

function StrategyCenter({ team, onNavigate }: { team: TeamResponse; onNavigate: (view: View) => void }) {
  const [advice, setAdvice] = useState<StrategyAdvice | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const calculate = async () => {
    setLoading(true); setError("");
    try { setAdvice(await api.strategy(team.session_id)); }
    catch (err) { setError(err instanceof Error ? err.message : "Strategianalysen feilet."); }
    finally { setLoading(false); }
  };
  const deadlineLabel = advice?.deadline.hours_remaining == null
    ? "Ukjent"
    : advice.deadline.hours_remaining <= 0
      ? "Passert"
      : advice.deadline.hours_remaining < 24
        ? `${advice.deadline.hours_remaining.toFixed(1)} t`
        : `${Math.floor(advice.deadline.hours_remaining / 24)} d`;
  return (
    <>
      <PageHeading view="strategy" eyebrow="Din ukentlige arbeidsflyt" title="Strategisenter" subtitle="Én prioritert plan for bytter, kaptein, lagnytt og prisbevegelser."
        action={<button className="primary" onClick={calculate} disabled={loading}>{loading ? "Analyserer…" : advice ? <><Icon.Refresh size={15} />Oppdater råd</> : "Lag ukesplan"}</button>} />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      {!advice && !loading && <section className="panel strategy-intro"><div className="strategy-orbit"><Icon.Compass size={32} /></div><div><h2>Fra prognose til beslutning</h2><p>Kombinerer flerukersmotoren, FPLs prisindikator og siste tilgjengelighet i én plan.</p><small>Kan ta opptil ~45 sekunder for lange horisonter.</small></div></section>}
      {loading && <Loading label="Bygger og validerer ukens beste beslutningsrekkefølge…" />}
      {advice && !loading && <>
        <section className={`strategy-hero strategy-${advice.transfer.decision.toLowerCase()}`}>
          <div><span className="eyebrow">Første handling · GW {advice.target_event}</span><h2>{advice.headline}</h2><p>{advice.transfer.reason}</p>{advice.transfer.warnings.length > 0 && <div className="strategy-warnings"><strong>Motstridende signaler</strong>{advice.transfer.warnings.map(warning => <span key={warning}>{warning}</span>)}</div>}</div>
          <div className="strategy-stamp"><small>{advice.transfer.global_optimum ? "Globalt optimum" : "Beste validerte plan"}</small><strong>{advice.transfer.decision}</strong><span>{advice.transfer.horizon} GW · {advice.transfer.confidence === "high" ? "høy" : advice.transfer.confidence === "medium" ? "middels" : "lav"} tillit</span></div>
        </section>
        <section className="metric-grid strategy-metrics">
          <article><i className="metric-icon"><Icon.Shield size={16} /></i><small>Spillbare</small><strong>{advice.squad_health.playable_players}/15</strong><span>{advice.squad_health.rating === "healthy" ? "robust tropp" : "krever oppfølging"}</span></article>
          <article><i className="metric-icon"><Icon.Captain size={16} /></i><small>Kaptein</small><strong>{advice.captain.captain.name}</strong><span>{points(advice.captain.margin)} margin</span></article>
          <article><i className="metric-icon"><Icon.Swap size={16} /></i><small>Gratisbytter</small><strong>{advice.transfer.free_transfers_before}</strong><span>{advice.transfer.hit ? `planen koster −${advice.transfer.hit}` : "ingen hit i første steg"}</span></article>
          <article><i className="metric-icon"><Icon.Calendar size={16} /></i><small>Tid til frist</small><strong>{deadlineLabel}</strong><span>{advice.deadline.urgency}</span></article>
        </section>

        <div className="strategy-layout">
          <section className="panel action-list"><span className="eyebrow">Prioritert nå</span><h2>Ukens sjekkliste</h2>{advice.actions.map((action, index) => <button key={`${action.category}-${index}`} onClick={() => onNavigate(action.view as View)}><span className={`action-index severity-${action.severity}`}>{index + 1}</span><div><strong>{action.title}</strong><small>{action.detail}</small></div><b><Icon.ArrowRight size={16} /></b></button>)}</section>
          <section className="panel captain-panel"><span className="eyebrow">Kapteinsbeslutning</span><h2>{advice.captain.confidence === "strong" ? "Tydelig valg" : advice.captain.confidence === "close" ? "Åpent valg" : "Moderat fordel"}</h2><p>{advice.captain.reason}</p>{advice.captain.alternatives.map((player, index) => <div className="captain-option" key={player.id}><span>{index === 0 ? "C" : index === 1 ? "VC" : "3"}</span><div><strong>{player.name}</strong><small>{player.opponent} · {player.ownership == null ? "ukjent eierskap" : `${player.ownership.toFixed(1)}% eid`}</small></div><b>{points(player.decision_points)}</b></div>)}</section>
        </div>

        <section className="panel price-radar"><div className="section-title"><div><span className="eyebrow">Offisiell FPL-indikator</span><h2>Prisradar</h2></div><span className="legend">100% antyder terskel</span></div>
          {!advice.price_alerts.available ? <p>{advice.price_alerts.caveat}</p> : <><div className="price-columns"><div><h3>Eide nær prisfall</h3>{advice.price_alerts.owned_at_risk.length ? advice.price_alerts.owned_at_risk.map(player => <StrategyPlayerRow player={player} price key={player.id} />) : <p>Ingen tydelige varsler.</p>}</div><div><h3>Relevante mål nær oppgang</h3>{advice.price_alerts.targets_rising.length ? advice.price_alerts.targets_rising.map(player => <StrategyPlayerRow player={player} price key={player.id} />) : <p>Ingen relevante varsler.</p>}</div></div><p className="model-note">{advice.price_alerts.caveat}</p></>}
        </section>

        <div className="watchlist-grid">
          <section className="panel"><span className="eyebrow">Ren prognose</span><h2>Beste mål</h2>{advice.watchlists.top_targets.map(player => <StrategyPlayerRow player={player} key={player.id} />)}</section>
          <section className="panel"><span className="eyebrow">Under 10% eid</span><h2>Differensialer</h2>{advice.watchlists.differentials.map(player => <StrategyPlayerRow player={player} key={player.id} />)}<p className="model-note">{advice.watchlists.caveat}</p></section>
          <section className="panel"><span className="eyebrow">Poeng per £m</span><h2>Verdi</h2>{advice.watchlists.value.map(player => <StrategyPlayerRow player={player} key={player.id} />)}</section>
        </div>

        <section className="panel schedule-strip"><div><span className="eyebrow">Kjent terminliste</span><h2>Blanks og doubles i troppen</h2></div>{advice.schedule.map(week => <div key={week.event}><strong>GW{week.event}</strong><span>{week.blank_players} blank</span><span>{week.double_players} double</span></div>)}</section>
        <details className="panel principles"><summary><Icon.Info size={14} /> Reglene bak rådene</summary><ol>{advice.principles.map(item => <li key={item}>{item}</li>)}</ol><p>{advice.method}</p></details>
        <p className="model-note">{advice.caveat}</p>
      </>}
    </>
  );
}

function Market({ team }: { team: TeamResponse }) {
  const [position, setPosition] = useState<Position | "ALL">("ALL");
  const [maxPrice, setMaxPrice] = useState(100);
  const [players, setPlayers] = useState<Player[]>([]);
  const [sells, setSells] = useState<Player[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const search = async () => {
    setLoading(true); setError("");
    try { const [marketResult, sellResult] = await Promise.all([api.market(team.session_id, position, maxPrice), api.sells(team.session_id)]); setPlayers(marketResult.players); setSells(sellResult.players); }
    catch (err) { setError(err instanceof Error ? err.message : "Markedssøket feilet."); }
    finally { setLoading(false); }
  };
  return (
    <>
      <PageHeading view="market" eyebrow="Modellrangering" title="Spillermarked" subtitle="Finn kjøpskandidater og spillerne modellen helst vil selge." />
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      <section className="market-filter panel"><label>Posisjon<select value={position} onChange={event => setPosition(event.target.value as Position | "ALL")}><option value="ALL">Alle</option><option value="GK">Keeper</option><option value="DEF">Forsvar</option><option value="MID">Midtbane</option><option value="FWD">Angrep</option></select></label><label>Makspris<strong>{money(maxPrice)}</strong><input type="range" min="40" max="150" value={maxPrice} onChange={event => setMaxPrice(Number(event.target.value))} /></label><button className="primary" onClick={search} disabled={loading}>{loading ? "Søker…" : "Vis kandidater"}</button></section>
      {loading && <Loading label="Rangerer spillermarkedet…" />}
      {(players.length > 0 || sells.length > 0) && !loading && <div className="market-columns"><section className="panel"><span className="eyebrow">Kjøp</span><h2>Beste kandidater</h2>{players.map((player, index) => <PlayerRow player={player} rank={index + 1} key={player.id} />)}</section><section className="panel"><span className="eyebrow">Selg</span><h2>Svakeste i troppen</h2>{sells.map((player, index) => <PlayerRow player={player} rank={index + 1} key={player.id} />)}</section></div>}
    </>
  );
}

type AnalysisTab = "season" | "gameweek" | "league" | "risk";

function rankNumber(value: number | null | undefined) {
  return value == null ? "–" : new Intl.NumberFormat("nb-NO").format(value);
}

function SignedValue({ value, suffix = "" }: { value: number; suffix?: string }) {
  return <span className={value > 0 ? "positive" : value < 0 ? "negative" : ""}>{value > 0 ? "+" : ""}{value.toFixed(1)}{suffix}</span>;
}

function SignedRank({ value }: { value: number }) {
  return <span className={value > 0 ? "positive" : value < 0 ? "negative" : ""}>{value > 0 ? "+" : value < 0 ? "−" : ""}{rankNumber(Math.abs(value))}</span>;
}

function PerformanceChart({ rows }: { rows: AnalyticsTimelineRow[] }) {
  const complete = rows.filter(row => row.finished);
  if (!complete.length) return <p className="empty-copy">Ingen ferdigspilte runder ennå.</p>;
  const width = 760, height = 230, pad = 34;
  const maxScore = Math.max(1, ...complete.flatMap(row => [row.points, row.global_average]));
  const step = (width - pad * 2) / Math.max(1, complete.length);
  const y = (value: number) => height - pad - value / maxScore * (height - pad * 2);
  const averagePath = complete.map((row, index) => `${index ? "L" : "M"}${pad + step * (index + .5)},${y(row.global_average)}`).join(" ");
  return <div className="analysis-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Poeng mot globalt Gameweek-snitt">
    {[0, .5, 1].map(level => <line key={level} x1={pad} x2={width - pad} y1={y(maxScore * level)} y2={y(maxScore * level)} className="chart-grid" />)}
    {complete.map((row, index) => {
      const x = pad + step * index + step * .18;
      const barWidth = step * .64;
      return <g key={row.event}><rect x={x} y={y(row.points)} width={barWidth} height={height - pad - y(row.points)} className={row.vs_average >= 0 ? "chart-bar positive-bar" : "chart-bar negative-bar"} /><text x={x + barWidth / 2} y={height - 10} textAnchor="middle">GW{row.event}</text><text x={x + barWidth / 2} y={Math.max(15, y(row.points) - 7)} textAnchor="middle" className="chart-value">{row.points}</text></g>;
    })}
    <path d={averagePath} className="average-line" /><text x={width - pad} y={18} textAnchor="end" className="chart-legend">— globalt snitt</text>
  </svg></div>;
}

function RankChart({ rows }: { rows: NonNullable<ManagerAnalytics["league"]>["development"] }) {
  if (!rows.length) return <p className="empty-copy">Ingen ligahistorikk tilgjengelig.</p>;
  const width = 760, height = 190, pad = 34;
  const maxRank = Math.max(1, ...rows.map(row => row.members));
  const x = (index: number) => pad + index * (width - pad * 2) / Math.max(1, rows.length - 1);
  const y = (rank: number) => pad + (rank - 1) / Math.max(1, maxRank - 1) * (height - pad * 2);
  const path = rows.map((row, index) => `${index ? "L" : "M"}${x(index)},${y(row.rank)}`).join(" ");
  return <div className="analysis-chart rank-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Utvikling i miniligarank">
    <line x1={pad} x2={width - pad} y1={y(1)} y2={y(1)} className="chart-grid" /><line x1={pad} x2={width - pad} y1={y(maxRank)} y2={y(maxRank)} className="chart-grid" />
    <path d={path} className="rank-line" />
    {rows.map((row, index) => <g key={row.event}><circle cx={x(index)} cy={y(row.rank)} r="6" className="rank-dot" /><text x={x(index)} y={height - 8} textAnchor="middle">GW{row.event}</text><text x={x(index)} y={Math.max(14, y(row.rank) - 11)} textAnchor="middle" className="chart-value">#{row.rank}</text></g>)}
  </svg></div>;
}

function ImpactList({ title, rows, tone }: { title: string; rows: RelativeImpact[]; tone: "gain" | "loss" }) {
  return <section className={`panel impact-panel ${tone}`}><span className="eyebrow">{tone === "gain" ? "Gevinst" : "Tap"}</span><h2>{title}</h2>{rows.length ? rows.map(row => <div className="impact-row" key={row.id}><div><strong>{row.name}</strong><small>{row.owned ? `${row.your_multiplier}× for deg` : "Ikke i din XI"} · {row.league_effective_ownership.toFixed(0)}% liga-EO · {row.raw_points}p</small></div><b><SignedValue value={row.league_swing} /></b></div>) : <p className="empty-copy">Ingen utslag.</p>}</section>;
}

function DecisionRows({ rows, kind }: { rows: AnalyticsDecisionPlayer[]; kind: "differential" | "threat" | "leverage" }) {
  const metric = (row: AnalyticsDecisionPlayer) => kind === "differential" ? row.differential_value : kind === "threat" ? row.threat_value : row.rank_exposure;
  return <div className="decision-rows">{rows.length ? rows.map((row, index) => <div className="decision-row" key={row.id}><span className="decision-rank">{index + 1}</span><div><strong>{row.name}</strong><small>{row.team} · {row.opponent} · {money(row.price)} · topputvalg {row.top10k_effective_ownership.toFixed(0)}% EO</small></div><span><small>Modell</small><b>{row.projection.toFixed(2)}</b></span><span><small>Liga-EO</small><b>{row.league_effective_ownership.toFixed(0)}%</b></span><span><small>{kind === "differential" ? "Oppside" : kind === "threat" ? "Risiko" : "Edge"}</small><b className={metric(row) > 0 ? "positive" : "negative"}>{metric(row).toFixed(2)}</b></span></div>) : <p className="empty-copy">Ingen spillere oppfyller kriteriene akkurat nå.</p>}</div>;
}

function ManagerAnalysis({ team }: { team: TeamResponse }) {
  const [data, setData] = useState<ManagerAnalytics | null>(null);
  const [tab, setTab] = useState<AnalysisTab>("season");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async (event?: number, league?: number | null) => {
    setLoading(true); setError("");
    try { setData(await api.analytics(team.session_id, event, league)); }
    catch (err) { setError(err instanceof Error ? err.message : "Kunne ikke analysere laget."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [team.session_id]);

  return <>
    <PageHeading view="analysis" eyebrow="Manager intelligence" title="Analyse" subtitle="Forstå resultatene, rivalene og rank-risikoen bak poengsummen."
      right={data && <div className="deadline"><small>Datagrunnlag</small><strong>GW1–GW{data.benchmark_event}</strong></div>} />
    {error && <ErrorBanner message={error} onClose={() => setError("")} />}
    {loading && !data && <Loading label="Henter sesong, tropper og ligarivaler…" />}
    {data && <>
      <section className="analysis-controls panel">
        <div className="analysis-tabs">{(["season", "gameweek", "league", "risk"] as AnalysisTab[]).map(value => <button key={value} className={tab === value ? "active" : ""} onClick={() => setTab(value)}>{value === "season" ? "Sesong" : value === "gameweek" ? "Gameweek" : value === "league" ? "Miniliga" : "Risiko & differensialer"}</button>)}</div>
        <div className="analysis-selects"><label>Gameweek<select value={data.selected_event} onChange={event => void load(Number(event.target.value), data.selected_league_id)}>{data.available_events.map(value => <option key={value} value={value}>GW {value}{data.completed_events.includes(value) ? "" : " · live"}</option>)}</select></label><label>Miniliga<select value={data.selected_league_id ?? ""} disabled={!data.leagues.length} onChange={event => void load(data.selected_event, Number(event.target.value))}>{!data.leagues.length && <option value="">Ingen offentlig liga</option>}{data.leagues.map(league => <option key={league.id} value={league.id}>{league.name}</option>)}</select></label></div>
      </section>
      {loading && <div className="top-progress inline-progress" />}

      {tab === "season" && <>
        <section className="analysis-metrics">
          <article><small>Totalpoeng</small><strong>{data.summary.total_points}</strong><span><SignedValue value={data.summary.points_vs_global_average} /> mot globale GW-snitt</span></article>
          <article><small>Totalrank</small><strong>{rankNumber(data.summary.overall_rank)}</strong><span>{data.summary.percentile == null ? "Ukjent persentil" : `bedre enn ${data.summary.percentile.toFixed(0)}%`}</span></article>
          <article><small>Beste runde</small><strong>{data.summary.best_week.points}</strong><span>GW {data.summary.best_week.event}</span></article>
          <article><small>Lagverdi</small><strong>£{data.summary.team_value.toFixed(1)}m</strong><span>{data.summary.average_points.toFixed(1)} poeng per GW</span></article>
        </section>
        <section className="panel global-benchmark"><div><span className="eyebrow">Global benchmark</span><h2>Toppmanager-utvalg</h2><p>{data.global_benchmark.sample_label} · {data.global_benchmark.sample_size} offentlige lag. Dette gir et mer relevant template-signal enn samlet globalt eierskap.</p></div><div className="global-gap"><small>Mot utvalgets snitt</small><strong>{data.global_benchmark.points_gap == null ? "–" : <SignedValue value={data.global_benchmark.points_gap} suffix="p" />}</strong><span>snitt {data.global_benchmark.sample_average_total ?? "–"}</span></div><div className="top-eo-strip">{data.global_benchmark.ownership.slice(0, 5).map(row => <span key={row.id}><strong>{row.name}</strong><small>{row.effective_ownership.toFixed(0)}% EO · {row.captain_rate.toFixed(0)}% C</small></span>)}</div></section>
        <section className="panel analysis-section"><div className="section-title"><div><span className="eyebrow">Sesongkurve</span><h2>Poeng mot globalt snitt</h2></div><span className="legend">Søyle = deg · linje = snitt</span></div><PerformanceChart rows={data.timeline} /></section>
        <div className="analysis-two-col"><section className="panel analysis-section"><span className="eyebrow">Beslutningsregnskap</span><h2>Hvor poengene forsvant eller kom</h2><div className="audit-grid"><div><small>Kapteinsbonus</small><strong className="positive">+{data.summary.captain_bonus.toFixed(0)}</strong></div><div><small>Kapteinsmulighet tapt</small><strong className="negative">−{data.summary.captain_opportunity_loss.toFixed(0)}</strong></div><div><small>Poeng på benk</small><strong>{data.summary.bench_points}</strong></div><div><small>Transferkostnad</small><strong className={data.summary.transfer_cost ? "negative" : ""}>{data.summary.transfer_cost ? `−${data.summary.transfer_cost}` : "0"}</strong></div><div><small>Brutto transfersving</small><strong><SignedValue value={data.summary.transfer_swing} /></strong></div><div><small>Svakeste GW</small><strong>{data.summary.worst_week.points}</strong><span>GW{data.summary.worst_week.event}</span></div></div></section><section className="panel analysis-section"><span className="eyebrow">Poengbase</span><h2>Bidrag per posisjon</h2><div className="position-bars">{(["GK", "DEF", "MID", "FWD"] as Position[]).map(position => { const max = Math.max(...Object.values(data.position_points), 1); return <div key={position}><span>{position}</span><i><b style={{ width: `${data.position_points[position] / max * 100}%` }} /></i><strong>{data.position_points[position].toFixed(0)}</strong></div>; })}</div></section></div>
        <section className="panel analysis-section table-panel"><span className="eyebrow">Alle runder</span><h2>Gameweek-logg</h2><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>GW</th><th>Poeng</th><th>Snitt</th><th>Δ snitt</th><th>OR</th><th>Rankflytt</th><th>Benk</th><th>Bytter/hit</th><th>Kaptein</th></tr></thead><tbody>{data.timeline.map(row => <tr key={row.event} className={!row.finished ? "live-row" : ""}><td>GW{row.event}{!row.finished && <small> LIVE</small>}</td><td><strong>{row.points}</strong></td><td>{row.global_average.toFixed(0)}</td><td><SignedValue value={row.vs_average} /></td><td>{rankNumber(row.overall_rank)}</td><td>{row.rank_change == null ? "–" : <SignedRank value={row.rank_change} />}</td><td>{row.bench_points}</td><td>{row.transfers} / {row.transfer_cost ? `−${row.transfer_cost}` : "0"}</td><td>{row.captain ?? "–"} <small>+{row.captain_bonus}</small></td></tr>)}</tbody></table></div></section>
      </>}

      {tab === "gameweek" && <>
        <section className="analysis-metrics"><article><small>GW{data.gameweek.event}-poeng</small><strong>{data.gameweek.points}</strong><span>offisiell score</span></article><article><small>Mot ligaens XI-er</small><strong><SignedValue value={data.gameweek.relative_gain} /></strong><span>før eventuelle hits</span></article><article><small>Benkepoeng</small><strong>{data.gameweek.missed_bench_points}</strong><span>ikke tellende</span></article><article><small>Kaptein</small><strong>{data.gameweek.captain?.name ?? "–"}</strong><span>{data.gameweek.captain ? `${data.gameweek.captain.effective_points} tellende poeng` : ""}</span></article></section>
        <div className="analysis-two-col"><ImpactList title="Dette løftet deg" rows={data.gameweek.top_gains} tone="gain" /><ImpactList title="Dette kostet mot ligaen" rows={data.gameweek.top_losses} tone="loss" /></div>
        <section className="panel analysis-section table-panel"><div className="section-title"><div><span className="eyebrow">Låst tropp</span><h2>Din GW{data.gameweek.event}-squad</h2></div><span className="legend">Swing måles mot liga-EO</span></div><div className="analytics-table-wrap"><table className="analytics-table squad-analysis-table"><thead><tr><th>Spiller</th><th>Rolle</th><th>Min</th><th>Råpoeng</th><th>Tellende</th><th>Global</th><th>Liga-EO</th><th>Relativt bidrag</th></tr></thead><tbody>{data.gameweek.squad.map(row => <tr key={row.id} className={row.multiplier === 0 ? "bench-analysis-row" : ""}><td><strong>{row.name}</strong><small>{row.team} · {row.position}</small></td><td>{row.is_captain ? "C" : row.is_vice_captain ? "VC" : row.multiplier === 0 ? "Benk" : "XI"}</td><td>{row.minutes}</td><td>{row.raw_points}</td><td>{row.effective_points}</td><td>{row.global_ownership.toFixed(0)}%</td><td>{row.league_effective_ownership.toFixed(0)}%</td><td><SignedValue value={row.league_swing} /></td></tr>)}</tbody></table></div></section>
      </>}

      {tab === "league" && (data.league ? <>
        <section className={`league-brief panel mode-${data.league.mode}`}><div><span className="eyebrow">{data.league.mode === "protect" ? "Forsvar posisjon" : data.league.mode === "chase" ? "Jaktmodus" : "Balansert modus"}</span><h2>{data.league.name}</h2><p>{data.league.advice}</p></div><div className="league-rank-badge"><small>Din plass</small><strong>#{data.league.your_rank ?? "–"}</strong><span>{data.league.gap_to_leader == null ? "" : data.league.gap_to_leader === 0 ? "leder ligaen" : `${Math.abs(data.league.gap_to_leader)}p bak leder`}</span></div></section>
        <section className="panel analysis-section"><div className="section-title"><div><span className="eyebrow">Utvikling</span><h2>Ligaplass gjennom sesongen</h2></div><span className="legend">{data.league.analyzed_managers}/{data.league.member_count} analyserte managere</span></div><RankChart rows={data.league.development} /></section>
        <div className="analysis-two-col league-columns"><section className="panel analysis-section table-panel"><span className="eyebrow">Tabell</span><h2>Rivalene</h2><div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>#</th><th>Lag</th><th>Manager</th><th>Total</th></tr></thead><tbody>{data.league.standings.map(row => <tr key={row.entry} className={row.is_you ? "you-row" : ""}><td>{row.rank ?? "–"}</td><td><strong>{row.team_name}</strong>{row.is_you && <small> DEG</small>}</td><td>{row.manager_name}</td><td><strong>{row.total_points}</strong></td></tr>)}</tbody></table></div></section><section className="panel analysis-section"><span className="eyebrow">Liga-template</span><h2>Effective ownership</h2><div className="ownership-list">{data.league.ownership.slice(0, 15).map(row => <div key={row.id}><strong>{row.name}</strong><i><b style={{ width: `${Math.min(100, row.effective_ownership)}%` }} /></i><span>{row.effective_ownership.toFixed(0)}% EO</span><small>{row.captain_rate.toFixed(0)}% C</small></div>)}</div></section></div>
      </> : <section className="panel"><h2>Ingen miniliga funnet</h2><p>Laget er ikke synlig i en privat klassisk liga gjennom offentlig FPL-data.</p></section>)}

      {tab === "risk" && <>
        <section className="risk-intro panel"><div><span className="eyebrow">GW{data.decisions.forecast_events.join("–")}</span><h2>Rank-risk med modellstøtte</h2><p>Lavt eierskap alene er ikke en grunn til å kjøpe. Her kombineres modellpoeng med effective ownership i {data.league?.name ?? "den valgte ligaen"}.</p></div><div><small>Horisont</small><strong>{data.decisions.horizon} GW</strong></div></section>
        <section className="panel analysis-section"><span className="eyebrow">Kapteinsmatrise</span><h2>Forventning mot liga-EO</h2><p className="section-copy">Ranger først på forventede poeng. Kapteinsedge viser isolert rank-oppside mot feltet, ikke merverdi mot ditt nest beste kapteinsvalg.</p><div className="captain-matrix">{data.decisions.captain_matrix.map((row, index) => <div key={row.id}><span>{index === 0 ? "C" : index + 1}</span><div><strong>{row.name}</strong><small>{row.opponent}</small></div><p><small>Modell</small><b>{row.projection.toFixed(2)}</b></p><p><small>Liga / topp EO</small><b>{row.league_effective_ownership.toFixed(0)}% / {row.top10k_effective_ownership.toFixed(0)}%</b></p><p><small>Isolert rank-edge</small><b className="positive">{row.captain_rank_edge?.toFixed(2)}</b></p></div>)}</div></section>
        <div className="risk-grid"><section className="panel analysis-section"><span className="eyebrow">Angrip</span><h2>Modellsterke differensialer</h2><p className="section-copy">Ikke eid av deg, under 35% liga-EO og rangert på projisert differensialverdi.</p><DecisionRows rows={data.decisions.differentials} kind="differential" /></section><section className="panel analysis-section"><span className="eyebrow">Beskytt</span><h2>Største rank-trusler</h2><p className="section-copy">Ikke eid av deg; risiko = modellpoeng × liga-EO.</p><DecisionRows rows={data.decisions.threats} kind="threat" /></section></div>
        <section className="panel analysis-section"><span className="eyebrow">Din leverage</span><h2>Spillerne som kan flytte deg</h2><DecisionRows rows={data.decisions.leverage} kind="leverage" /></section>
      </>}
      <p className="model-note">{data.method} {data.caveats.join(" ")}</p>
    </>}
  </>;
}

type DraftSquadChange = { out_id: number; in_id: number };

function SquadEditor({ team, onUpdated }: {
  team: TeamResponse;
  onUpdated: (team: TeamResponse) => void;
}) {
  const [options, setOptions] = useState<Player[]>([]);
  const [changes, setChanges] = useState<DraftSquadChange[]>([{ out_id: 0, in_id: 0 }]);
  const [mode, setMode] = useState<"synchronize" | "apply_transfers">("synchronize");
  const [syncBank, setSyncBank] = useState(team.bank);
  const [syncTransfers, setSyncTransfers] = useState(team.free_transfers);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setSyncBank(team.bank);
    setSyncTransfers(team.free_transfers);
    api.squadOptions(team.session_id)
      .then(result => setOptions(result.players))
      .catch(err => setError(err instanceof Error ? err.message : "Kunne ikke hente spillere."));
  }, [team.session_id, team.bank, team.free_transfers]);

  const owned = useMemo(() => new Set(team.squad.map(player => player.id)), [team.squad]);
  const selectedIncoming = new Set(changes.map(change => change.in_id).filter(Boolean));
  const selectedOutgoing = new Set(changes.map(change => change.out_id).filter(Boolean));
  const playerById = useMemo(
    () => new Map([...options, ...team.squad].map(player => [player.id, player])),
    [options, team.squad],
  );
  const preview = useMemo(() => {
    let bank = team.bank;
    for (const change of changes) {
      const outgoing = team.squad.find(player => player.id === change.out_id);
      const incoming = playerById.get(change.in_id);
      if (outgoing && incoming) bank += (outgoing.selling_price ?? outgoing.price) - incoming.price;
    }
    const completed = changes.filter(change => change.out_id && change.in_id).length;
    return {
      bank,
      freeTransfers: Math.max(0, team.free_transfers - completed),
      hit: Math.max(0, completed - team.free_transfers) * 4,
    };
  }, [changes, playerById, team.bank, team.free_transfers, team.squad]);

  const updateChange = (index: number, field: keyof DraftSquadChange, value: number) => {
    setChanges(current => current.map((change, position) => {
      if (position !== index) return change;
      return field === "out_id" ? { out_id: value, in_id: 0 } : { ...change, in_id: value };
    }));
  };
  const candidates = (change: DraftSquadChange) => {
    const outgoing = team.squad.find(player => player.id === change.out_id);
    if (!outgoing) return [];
    return options.filter(player =>
      player.position === outgoing.position
      && !owned.has(player.id)
      && (!selectedIncoming.has(player.id) || player.id === change.in_id)
      && player.id !== change.out_id,
    ).sort((a, b) => a.name.localeCompare(b.name));
  };
  const valid = changes.length > 0 && changes.every(change => change.out_id > 0 && change.in_id > 0);

  const save = async () => {
    if (!valid) return;
    setLoading(true); setError(""); setNotice("");
    try {
      const updated = await api.updateSquad(
        team.session_id, mode, changes, syncBank, syncTransfers,
      );
      onUpdated(updated);
      const summary = updated.squad_update?.changes
        .map(change => `${change.out} → ${change.in}`).join(", ");
      setNotice(`${summary || "Laget"} er lagret. Alle analyser bruker nå den korrigerte troppen.`);
      setChanges([{ out_id: 0, in_id: 0 }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunne ikke korrigere laget.");
    } finally { setLoading(false); }
  };
  const reset = async () => {
    if (!window.confirm("Fjerne manuelle endringer og laste siste offentlige FPL-lag?")) return;
    setLoading(true); setError(""); setNotice("");
    try {
      const updated = await api.resetSquad(team.session_id);
      onUpdated(updated);
      setChanges([{ out_id: 0, in_id: 0 }]);
      setNotice("Manuell korrigering er fjernet.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunne ikke nullstille laget.");
    } finally { setLoading(false); }
  };

  return <>
    <PageHeading view="squad" eyebrow="Nåværende lagtilstand" title="Korriger lag" subtitle="Legg inn bytter FPL ennå ikke viser offentlig."
      right={<div className="deadline"><small>Kilde</small><strong>{team.squad_source === "manual_override" ? "Manuelt korrigert" : "Offentlig FPL-lag"}</strong></div>} />
    {error && <ErrorBanner message={error} onClose={() => setError("")} />}
    {notice && <div className="success-banner">{notice}</div>}
    <section className="panel squad-editor-intro">
      <div><span className="eyebrow">Velg betydning</span><h2>Er byttene allerede gjort i FPL?</h2><p>Synkronisering teller dem ikke på nytt. Nye sesjonsbytter bruker appens registrerte gratisbytter, men utføres aldri på FPL-nettsiden.</p></div>
      <div className="mode-toggle"><button className={mode === "synchronize" ? "active" : ""} onClick={() => setMode("synchronize")}>Allerede gjort</button><button className={mode === "apply_transfers" ? "active" : ""} onClick={() => setMode("apply_transfers")}>Nye bytter</button></div>
    </section>
    <section className="panel squad-editor">
      <div className="section-title"><div><span className="eyebrow">Spillerendringer</span><h2>Ut og inn</h2></div><button className="secondary" disabled={changes.length >= 5} onClick={() => setChanges(current => [...current, { out_id: 0, in_id: 0 }])}><Icon.Plus size={14} />Legg til bytte</button></div>
      <div className="manual-transfer-list">{changes.map((change, index) => <div className="manual-transfer-row" key={index}>
        <label>Spiller ut<select value={change.out_id} onChange={event => updateChange(index, "out_id", Number(event.target.value))}><option value={0}>Velg fra troppen</option>{team.squad.filter(player => !selectedOutgoing.has(player.id) || player.id === change.out_id).sort((a, b) => a.position.localeCompare(b.position) || a.name.localeCompare(b.name)).map(player => <option value={player.id} key={player.id}>{player.position} · {player.name} · {money(player.selling_price ?? player.price)}</option>)}</select></label>
        <span><Icon.ArrowRight size={16} /></span>
        <label>Spiller inn<select value={change.in_id} disabled={!change.out_id} onChange={event => updateChange(index, "in_id", Number(event.target.value))}><option value={0}>Velg spiller</option>{candidates(change).map(player => <option value={player.id} key={player.id}>{player.name} · {player.team} · {money(player.price)} · {points(player.recommended_points)}</option>)}</select></label>
        <button className="remove-change" disabled={changes.length === 1} onClick={() => setChanges(current => current.filter((_, position) => position !== index))} aria-label="Fjern bytte"><Icon.Trash size={15} /></button>
      </div>)}</div>
      {mode === "synchronize" ? <div className="sync-fields"><label>Faktisk bank etter byttene (£m)<input type="number" min="0" max="20" step="0.1" value={syncBank / 10} onChange={event => setSyncBank(Math.round(Number(event.target.value) * 10))} /></label><label>Gratisbytter igjen<input type="number" min="0" max="5" value={syncTransfers} onChange={event => setSyncTransfers(Number(event.target.value))} /></label></div> : <div className={`transfer-preview ${preview.hit ? "has-hit" : ""}`}><span>Estimert bank <strong>{money(preview.bank)}</strong></span><span>FT igjen <strong>{preview.freeTransfers}</strong></span><span>Kostnad <strong>{preview.hit ? `−${preview.hit}` : "0"}</strong></span></div>}
      <div className="editor-actions"><button className="primary" disabled={!valid || loading || (mode === "apply_transfers" && preview.bank < 0)} onClick={save}>{loading ? "Lagrer…" : mode === "synchronize" ? "Synkroniser faktisk lag" : "Bruk som nye sesjonsbytter"}</button>{team.squad_source === "manual_override" && <button className="secondary" disabled={loading} onClick={reset}>Tilbakestill til FPL</button>}</div>
    </section>
    <section className="panel current-squad-editor"><span className="eyebrow">Aktiv tropp</span><div className="squad-groups">{(["GK", "DEF", "MID", "FWD"] as Position[]).map(position => <div className="squad-group" key={position}><h3>{positionNames[position]}</h3>{team.squad.filter(player => player.position === position).map(player => <PlayerRow player={player} key={player.id} />)}</div>)}</div></section>
  </>;
}

export default function App() {
  const [reference, setReference] = useState(DEFAULT_TEAM);
  const [horizon, setHorizon] = useState(3);
  const [risk, setRisk] = useState<RiskProfile>("balanced");
  const [team, setTeam] = useState<TeamResponse | null>(null);
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [bank, setBank] = useState(0);
  const [freeTransfers, setFreeTransfers] = useState(1);
  const activeLabel = useMemo(() => VIEWS.find(item => item.id === view)?.label, [view]);

  const load = async () => {
    setLoading(true); setError("");
    try {
      const loaded = await api.importTeam(reference, horizon, risk);
      setTeam(loaded); setBank(loaded.bank); setFreeTransfers(loaded.free_transfers); setView("overview"); setMobileMenuOpen(false);
    } catch (err) {
      setTeam(null);
      setError(err instanceof Error ? err.message : "Kunne ikke laste laget.");
    }
    finally { setLoading(false); }
  };
  const saveSettings = async () => {
    if (!team) return;
    setLoading(true); setError("");
    try { const updated = await api.updateSettings(team.session_id, bank, freeTransfers); setTeam(updated); setEditing(false); }
    catch (err) { setError(err instanceof Error ? err.message : "Kunne ikke lagre innstillingene."); }
    finally { setLoading(false); }
  };
  const refresh = async () => {
    setRefreshing(true); setError("");
    try {
      const updated = team
        ? await api.refreshTeam(team.session_id)
        : await (async () => {
            await api.refreshForecast();
            return api.importTeam(reference, horizon, risk);
          })();
      setTeam(updated); setBank(updated.bank); setFreeTransfers(updated.free_transfers);
      setView("overview");
    }
    catch (err) { setError(err instanceof Error ? err.message : "Kunne ikke oppdatere prognosen."); }
    finally { setRefreshing(false); }
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${team ? "" : "no-team"} ${mobileMenuOpen ? "menu-open" : ""}`}>
        <div className="brand"><span><Icon.Shield size={20} /></span><div><strong>FPL Modell</strong><small>Decision lab</small></div></div>
        <div className="load-form">
          <label>Laglenke eller ID<textarea value={reference} onChange={event => setReference(event.target.value)} rows={3} /></label>
          <div className="form-row"><label>Horisont<select value={horizon} onChange={event => setHorizon(Number(event.target.value))}>{[1, 2, 3, 4, 5, 6, 7, 8].map(value => <option value={value} key={value}>{value} GW</option>)}</select></label><label>Profil<select value={risk} onChange={event => setRisk(event.target.value as RiskProfile)}><option value="balanced">Balansert</option><option value="stable">Stabil</option><option value="upside">Oppside</option></select></label></div>
          <button className="primary full" onClick={load} disabled={loading || !reference.trim()}>{loading && !team ? "Laster laget…" : team ? "Last inn på nytt" : "Last inn laget"}</button>
        </div>
        <nav>{VIEWS.map(item => <button key={item.id} className={view === item.id ? "active" : ""} disabled={!team} onClick={() => { setView(item.id); setMobileMenuOpen(false); }}><item.icon size={17} />{item.label}</button>)}</nav>
        {team && <div className="team-settings"><div><small>{team.squad_source === "manual_override" ? "Manuelt lag" : "Økonomi"}</small><button onClick={() => setEditing(!editing)}>{editing ? "Avbryt" : "Korriger"}</button></div>{editing ? <><label>Bank (£m)<input type="number" min="0" max="20" step="0.1" value={bank / 10} onChange={event => setBank(Math.round(Number(event.target.value) * 10))} /></label><label>Gratisbytter<input type="number" min="0" max="5" value={freeTransfers} onChange={event => setFreeTransfers(Number(event.target.value))} /></label><button className="secondary full" onClick={saveSettings}>Lagre</button></> : <p><strong>{money(team.bank)}</strong><span>{team.free_transfers} FT</span></p>}</div>}
        <button className="refresh" onClick={refresh} disabled={refreshing || !reference.trim()}><Icon.Refresh size={14} />{refreshing ? "Oppdaterer…" : "Oppdater prognose"}</button>
        <p className="privacy">Offentlige data · ingen innlogging · ingen automatiske bytter</p>
      </aside>
      <main>
        <div className="mobile-bar">
          <div className="brand"><span><Icon.Shield size={16} /></span><strong>FPL Modell</strong></div>
          {team && <small>{activeLabel}</small>}
          {team && <button className="mobile-menu-toggle" onClick={() => setMobileMenuOpen(open => !open)} aria-label="Lag og innstillinger">{mobileMenuOpen ? <Icon.Close size={18} /> : <Icon.Menu size={18} />}</button>}
        </div>
        {error && <ErrorBanner message={error} onClose={() => setError("")} />}
        {loading && team && <div className="top-progress" />}
        {!team ? <EmptyState /> : view === "overview" ? <Overview team={team} /> : view === "analysis" ? <ManagerAnalysis team={team} /> : view === "squad" ? <SquadEditor team={team} onUpdated={updated => { setTeam(updated); setBank(updated.bank); setFreeTransfers(updated.free_transfers); }} /> : view === "strategy" ? <StrategyCenter team={team} onNavigate={setView} /> : view === "lineup" ? <Lineup team={team} /> : view === "transfers" ? <Transfers team={team} /> : view === "plan" ? <Multiweek team={team} /> : view === "squads" ? <RecommendedTeams team={team} /> : view === "chips" ? <Chips team={team} /> : <Market team={team} />}
      </main>
      <nav className="mobile-nav">{VIEWS.map(item => <button key={item.id} className={view === item.id ? "active" : ""} disabled={!team} onClick={() => setView(item.id)}><item.icon size={19} /><small>{item.label}</small></button>)}</nav>
    </div>
  );
}
