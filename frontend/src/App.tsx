import { useMemo, useState } from "react";
import { api } from "./api";
import type {
  ChipCandidate,
  ChipStrategy,
  Player,
  Position,
  RiskProfile,
  TeamResponse,
  TransferResponse,
} from "./types";

type View = "overview" | "lineup" | "transfers" | "chips" | "market";

const DEFAULT_TEAM = "https://fantasy.premierleague.com/en/entry/5139814/event/4";
const VIEWS: Array<{ id: View; label: string; icon: string }> = [
  { id: "overview", label: "Oversikt", icon: "⌂" },
  { id: "lineup", label: "Laguttak", icon: "◫" },
  { id: "transfers", label: "Bytter", icon: "⇄" },
  { id: "chips", label: "Chips", icon: "◇" },
  { id: "market", label: "Marked", icon: "⌕" },
];

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
      <span>!</span><p>{message}</p><button onClick={onClose} aria-label="Lukk">×</button>
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
      <div className="empty-mark">FPL</div>
      <h2>Last inn laget ditt</h2>
      <p>Lim inn en offentlig FPL-lenke i panelet til venstre. Appen leser laget, kobler på modellprognosen og lager lovlige anbefalinger.</p>
    </section>
  );
}

function Overview({ team }: { team: TeamResponse }) {
  const best = [...team.squad].sort((a, b) => b.recommended_points - a.recommended_points)[0];
  return (
    <>
      <header className="page-heading">
        <div><span className="eyebrow">GW {team.target_event}</span><h1>{team.team_name}</h1><p>{team.manager_name} · anbefalinger for de neste {team.horizon} GW</p></div>
        <div className="deadline"><small>Deadline</small><strong>{team.deadline || "Ikke publisert"}</strong></div>
      </header>
      <section className="metric-grid">
        <article><small>Forventet XI + kaptein</small><strong>{points(team.lineup.expected_total)}</strong><span>poeng i GW {team.target_event}</span></article>
        <article><small>Formasjon</small><strong>{team.lineup.formation}</strong><span>modellens beste ellever</span></article>
        <article><small>Bank</small><strong>{money(team.bank)}</strong><span>{team.free_transfers} gratisbytte{team.free_transfers === 1 ? "" : "r"}</span></article>
        <article><small>Høyest prognose</small><strong>{best?.name ?? "–"}</strong><span>{points(best?.recommended_points)} poeng</span></article>
      </section>
      <section className="panel">
        <div className="section-title"><div><span className="eyebrow">15 spillere</span><h2>Troppen din</h2></div><span className="legend">Modellpoeng →</span></div>
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
      <header className="page-heading"><div><span className="eyebrow">Optimal XI</span><h1>Laguttak</h1><p>{team.lineup.formation} · {points(team.lineup.expected_total)} forventede poeng inkludert kaptein</p></div></header>
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
  const [number, setNumber] = useState(Math.min(2, Math.max(1, team.free_transfers)));
  const [result, setResult] = useState<TransferResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const calculate = async () => {
    setLoading(true); setError("");
    try { setResult(await api.transfers(team.session_id, number)); }
    catch (err) { setError(err instanceof Error ? err.message : "Bytteberegningen feilet."); }
    finally { setLoading(false); }
  };
  const hit = Math.max(0, number - team.free_transfers) * 4;
  return (
    <>
      <header className="page-heading"><div><span className="eyebrow">Eksakt optimering</span><h1>Bytteplan</h1><p>Velg opptil fem spillere. Motoren håndhever budsjett, posisjoner og klubbgrense.</p></div></header>
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      <section className="transfer-control panel">
        <div><h2>Hvor mange bytter?</h2><p>Du har {team.free_transfers} estimerte gratisbytter.</p></div>
        <div className="number-picker" aria-label="Antall bytter">{[1, 2, 3, 4, 5].map(value => <button className={number === value ? "active" : ""} onClick={() => { setNumber(value); setResult(null); }} key={value}>{value}</button>)}</div>
        <div className={`hit-pill ${hit ? "has-hit" : ""}`}>{hit ? `−${hit} poeng hit` : "Ingen hit"}</div>
        <button className="primary" onClick={calculate} disabled={loading}>{loading ? "Beregner…" : "Finn beste plan"}</button>
      </section>
      {loading && <Loading label="Søker gjennom lovlige tropper…" />}
      {result && !loading && (
        <section className="results">
          <div className="section-title"><div><span className="eyebrow">{result.global_optimum ? "Globalt optimum" : "Rangerte alternativer"}</span><h2>Anbefalt plan</h2></div></div>
          {result.plans.length === 0 ? <p className="panel">Ingen lovlig plan med positiv modellgevinst ble funnet.</p> : result.plans.map((plan, index) => (
            <article className={`transfer-plan ${index === 0 ? "best-plan" : ""}`} key={`${plan.out}-${plan.in}-${index}`}>
              <div className="plan-rank">{index + 1}</div>
              <div className="moves"><div><small>UT</small><strong>{plan.out}</strong></div><span>→</span><div><small>INN</small><strong>{plan.in}</strong></div></div>
              <div className="plan-stats"><div><small>Netto gevinst</small><strong className={plan.net_gain >= 0 ? "positive" : "negative"}>{points(plan.net_gain, true)}</strong></div><div><small>Hit</small><strong>{plan.hit ? `−${plan.hit}` : "0"}</strong></div><div><small>Igjen</small><strong>{moneyMillions(plan.money_left)}</strong></div></div>
            </article>
          ))}
          <p className="model-note">Netto gevinst er modellens horisontscore etter eventuelle poengtrekk. Ikke utfør et bytte uten å kontrollere siste lagnytt.</p>
        </section>
      )}
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
      <header className="page-heading"><div><span className="eyebrow">Regelbevisst scenariotest</span><h1>Chipstrategi</h1><p>Verdsetter chipene mot vanlig spill over den kjente prognosehorisonten.</p></div><button className="primary" onClick={calculate} disabled={loading}>{loading ? "Analyserer…" : strategy ? "Kjør på nytt" : "Analyser chips"}</button></header>
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      {!strategy && !loading && <section className="chip-intro panel"><div className="chip-symbol">◇</div><div><h2>Finn verdien av hver chip</h2><p>Modellen sammenligner Triple Captain, Bench Boost, Free Hit, Wildcard og sekvensen Wildcard → Bench Boost. Beregningen kan ta 10–20 sekunder.</p></div></section>}
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
          <section className="research-note panel"><h3>Hvordan vurderingen brukes</h3><p>Bench Boost favoriserer en sterk benk og doble kamper, Triple Captain en tydelig kapteinstopp, Free Hit store blank-/dobbelrunder og Wildcard varig gevinst over flere runder. Bare én chip kan brukes per Gameweek.</p><p><a href="https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627" target="_blank" rel="noreferrer">Offisielle chipregler 2026/27 ↗</a> · <a href="https://www.premierleague.com/en/news/4685105" target="_blank" rel="noreferrer">Premier Leagues ekspertstrategier ↗</a></p></section>
        </>
      )}
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
      <header className="page-heading"><div><span className="eyebrow">Modellrangering</span><h1>Spillermarked</h1><p>Finn kjøpskandidater og spillerne modellen helst vil selge.</p></div></header>
      {error && <ErrorBanner message={error} onClose={() => setError("")} />}
      <section className="market-filter panel"><label>Posisjon<select value={position} onChange={event => setPosition(event.target.value as Position | "ALL")}><option value="ALL">Alle</option><option value="GK">Keeper</option><option value="DEF">Forsvar</option><option value="MID">Midtbane</option><option value="FWD">Angrep</option></select></label><label>Makspris<strong>{money(maxPrice)}</strong><input type="range" min="40" max="150" value={maxPrice} onChange={event => setMaxPrice(Number(event.target.value))} /></label><button className="primary" onClick={search} disabled={loading}>{loading ? "Søker…" : "Vis kandidater"}</button></section>
      {loading && <Loading label="Rangerer spillermarkedet…" />}
      {(players.length > 0 || sells.length > 0) && !loading && <div className="market-columns"><section className="panel"><span className="eyebrow">Kjøp</span><h2>Beste kandidater</h2>{players.map((player, index) => <PlayerRow player={player} rank={index + 1} key={player.id} />)}</section><section className="panel"><span className="eyebrow">Selg</span><h2>Svakeste i troppen</h2>{sells.map((player, index) => <PlayerRow player={player} rank={index + 1} key={player.id} />)}</section></div>}
    </>
  );
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
  const [bank, setBank] = useState(0);
  const [freeTransfers, setFreeTransfers] = useState(1);
  const activeLabel = useMemo(() => VIEWS.find(item => item.id === view)?.label, [view]);

  const load = async () => {
    setLoading(true); setError("");
    try {
      const loaded = await api.importTeam(reference, horizon, risk);
      setTeam(loaded); setBank(loaded.bank); setFreeTransfers(loaded.free_transfers); setView("overview");
    } catch (err) { setError(err instanceof Error ? err.message : "Kunne ikke laste laget."); }
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
    try { await api.refreshForecast(); await load(); }
    catch (err) { setError(err instanceof Error ? err.message : "Kunne ikke oppdatere prognosen."); }
    finally { setRefreshing(false); }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span>F</span><div><strong>FPL Modell</strong><small>Decision lab</small></div></div>
        <div className="load-form">
          <label>Laglenke eller ID<textarea value={reference} onChange={event => setReference(event.target.value)} rows={3} /></label>
          <div className="form-row"><label>Horisont<select value={horizon} onChange={event => setHorizon(Number(event.target.value))}><option value={1}>1 GW</option><option value={2}>2 GW</option><option value={3}>3 GW</option></select></label><label>Profil<select value={risk} onChange={event => setRisk(event.target.value as RiskProfile)}><option value="balanced">Balansert</option><option value="stable">Stabil</option><option value="upside">Oppside</option></select></label></div>
          <button className="primary full" onClick={load} disabled={loading || !reference.trim()}>{loading && !team ? "Laster laget…" : team ? "Last inn på nytt" : "Last inn laget"}</button>
        </div>
        <nav>{VIEWS.map(item => <button key={item.id} className={view === item.id ? "active" : ""} disabled={!team} onClick={() => setView(item.id)}><span>{item.icon}</span>{item.label}</button>)}</nav>
        {team && <div className="team-settings"><div><small>Økonomi</small><button onClick={() => setEditing(!editing)}>{editing ? "Avbryt" : "Korriger"}</button></div>{editing ? <><label>Bank (£m)<input type="number" min="0" max="20" step="0.1" value={bank / 10} onChange={event => setBank(Math.round(Number(event.target.value) * 10))} /></label><label>Gratisbytter<input type="number" min="0" max="5" value={freeTransfers} onChange={event => setFreeTransfers(Number(event.target.value))} /></label><button className="secondary full" onClick={saveSettings}>Lagre</button></> : <p><strong>{money(team.bank)}</strong><span>{team.free_transfers} FT</span></p>}</div>}
        <button className="refresh" onClick={refresh} disabled={!team || refreshing}>{refreshing ? "Oppdaterer…" : "↻ Oppdater prognose"}</button>
        <p className="privacy">Offentlige data · ingen innlogging · ingen automatiske bytter</p>
      </aside>
      <main>
        <div className="mobile-bar"><div className="brand"><span>F</span><strong>FPL Modell</strong></div><small>{activeLabel}</small></div>
        {error && <ErrorBanner message={error} onClose={() => setError("")} />}
        {loading && team && <div className="top-progress" />}
        {!team ? <EmptyState /> : view === "overview" ? <Overview team={team} /> : view === "lineup" ? <Lineup team={team} /> : view === "transfers" ? <Transfers team={team} /> : view === "chips" ? <Chips team={team} /> : <Market team={team} />}
      </main>
      <nav className="mobile-nav">{VIEWS.map(item => <button key={item.id} className={view === item.id ? "active" : ""} disabled={!team} onClick={() => setView(item.id)}><span>{item.icon}</span><small>{item.label}</small></button>)}</nav>
    </div>
  );
}
