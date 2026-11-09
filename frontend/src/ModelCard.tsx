import { useEffect, useState } from "react";
import type { ModelCard } from "@fplmodell/api-client";
import { api } from "./api";
import { Icon } from "./icons";

const signed = (value: number | null | undefined, digits = 2) => value == null ? "–" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
const percent = (value: number | null | undefined) => value == null ? "–" : `${(value * 100).toFixed(0)}%`;

/** Plan E4 + O3: the production model, locked-round results, calibration, limits and data coverage. */
export function ModelCardView() {
  const [card, setCard] = useState<ModelCard | null>(null);
  const [error, setError] = useState("");
  const load = () => { setError(""); api.modelCard().then(setCard).catch(err => setError(err instanceof Error ? err.message : "Could not load the model card.")); };
  useEffect(load, []);
  if (error) return <div className="error-banner" role="alert"><Icon.Alert size={18} /><span>{error}</span><button onClick={load}>Try again</button></div>;
  if (!card) return <div className="loading"><span className="spinner" />Loading the model card…</div>;
  const quality = card.data_quality;
  const odds = Object.entries(quality.capture.odds_coverage ?? {});
  return <section className="model-card" aria-label="Model card">
    <header className="page-heading"><div className="page-heading-main"><span className="page-icon"><Icon.Chart size={22} /></span>
      <div><span className="eyebrow">How far to trust the numbers</span><h1>Model and data</h1><p>{card.claim}</p></div></div></header>

    <div className="panel">
      <div className="section-title"><h2>Data quality</h2></div>
      {quality.consequences.length ? <ul className="quality-notes">{quality.consequences.map(note => <li key={note}>{note}</li>)}</ul> : <p className="section-copy">No known data issues affect this round.</p>}
      <dl className="fact-list">
        <div><dt>Forecast snapshot</dt><dd>{quality.capture.age_hours != null ? `${quality.capture.age_hours.toFixed(0)} h old` : "–"}</dd></div>
        <div><dt>Own data (fpl-data)</dt><dd>{quality.fpl_data.age_hours != null ? `${quality.fpl_data.age_hours.toFixed(0)} h old · GW${quality.fpl_data.exported_rounds.at(-1) ?? "–"} exported` : "not found"}</dd></div>
        <div><dt>Odds coverage</dt><dd>{odds.length ? odds.map(([gw, share]) => `GW${gw} ${percent(share)}`).join(" · ") : "–"}</dd></div>
        <div><dt>Forecasts without odds</dt><dd>{percent(quality.capture.market_fallback_share)}</dd></div>
        <div><dt>Players with earlier PL history</dt><dd>{percent(quality.code_coverage.share)} ({quality.code_coverage.with_history} of {quality.code_coverage.players})</dd></div>
        <div><dt>Last evaluated round</dt><dd>{quality.last_evaluated_round ? `GW${quality.last_evaluated_round}` : "none yet"}{quality.missed_locks.length ? ` · never locked: ${quality.missed_locks.map(gw => `GW${gw}`).join(", ")}` : ""}</dd></div>
      </dl>
    </div>

    <div className="panel">
      <div className="section-title"><h2>Locked rounds</h2><span className="legend">{card.rounds.counted_v1} of {card.rounds.needed} counted (v1) · {card.rounds.counted_v2} of {card.rounds.needed} (v2)</span></div>
      <p className="section-copy">Every model is locked before the deadline and scored after FPL checks the round. One or two rounds say little; differences are shown with their round count.</p>
      <div className="analytics-table-wrap"><table className="analytics-table">
        <thead><tr><th scope="col">Model</th><th scope="col">Rounds (counted)</th><th scope="col">Δ team pts/round</th><th scope="col">Weekly MAE</th><th scope="col">Q10–Q90 hit</th><th scope="col">Criterion</th></tr></thead>
        <tbody>{card.leaderboard.map(row => <tr key={row.model}>
          <th scope="row">{row.model === "incumbent" ? "Production (incumbent)" : row.model}</th>
          <td>{row.rounds_shown} ({row.rounds_counted})</td><td>{signed(row.team_points_diff_mean)}</td>
          <td>{row.weekly_MAE_mean?.toFixed(2) ?? "–"}</td><td>{percent(row.interval_coverage_mean)}</td>
          <td>{row.criterion_met ? "Met" : "Not met"}</td></tr>)}</tbody>
      </table></div>
    </div>

    <div className="panel">
      <div className="section-title"><h2>Calibration and limits</h2></div>
      <dl className="fact-list">
        <div><dt>Production model</dt><dd>{card.production.model_family ?? "–"}</dd></div>
        <div><dt>Q10–Q90 hit rate</dt><dd>{percent(card.calibration.interval_coverage)} (aim {percent(card.calibration.interval_nominal)})</dd></div>
        <div><dt>Brier score, 60+ minutes</dt><dd>{card.calibration.brier_60plus?.toFixed(3) ?? "–"} (lower is better)</dd></div>
        <div><dt>Playing-time recalibration</dt><dd>{card.calibration.minutes_recalibration ? `${card.calibration.minutes_recalibration.rounds} of ${card.calibration.minutes_recalibration.needed} rounds` : "–"}</dd></div>
      </dl>
      <ul className="quality-notes">{card.limitations.map(item => <li key={item}>{item}</li>)}</ul>
    </div>
  </section>;
}
