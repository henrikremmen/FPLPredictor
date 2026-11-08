import { useEffect, useState } from "react";
import type { FixtureTicker } from "@fplmodell/api-client";
import { api } from "./api";
import { Icon } from "./icons";
import { PlayerName } from "./Workspace";

/** U16: 3–8 Gameweek columns with opponent, expected points and 60+ chance; blanks and doubles labelled. */
export function FixtureTickerView({ sessionId, revision }: { sessionId: string; revision: string }) {
  const [scope, setScope] = useState<"squad" | "market">("squad");
  const [data, setData] = useState<FixtureTicker | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    api.fixtures(sessionId, scope).then(r => { if (active) setData(r); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : "Could not load fixtures."); });
    return () => { active = false; };
  }, [sessionId, scope, revision]);
  return <section className="fixture-ticker" aria-label="Fixture ticker">
    <header className="page-heading compact"><div className="page-heading-main"><span className="page-icon"><Icon.Calendar size={22} /></span>
      <div><span className="eyebrow">Next Gameweeks</span><h1>Fixtures</h1><p>Opponent, expected points and the chance of 60+ minutes per Gameweek.</p></div></div></header>
    <div className="mode-toggle" role="group" aria-label="Players shown">
      <button aria-pressed={scope === "squad"} className={scope === "squad" ? "active" : ""} onClick={() => setScope("squad")}>Your squad</button>
      <button aria-pressed={scope === "market"} className={scope === "market" ? "active" : ""} onClick={() => setScope("market")}>Best not owned</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <div className="loading"><span className="spinner" />Loading fixtures…</div>}
    {data && <div className="table-scroll"><table className="ticker-table">
      <caption className="sr-only">{scope === "squad" ? "Your squad" : "Best players you do not own"}: fixtures by Gameweek</caption>
      <thead><tr><th scope="col">Player</th>{data.events.map(gw => <th scope="col" key={gw}>GW{gw}</th>)}<th scope="col">Total</th></tr></thead>
      <tbody>{data.players.map(player => <tr key={player.id}>
        <th scope="row"><PlayerName id={player.id}>{player.name}</PlayerName><small>{player.position} · {player.team}</small></th>
        {player.weeks.map(week => <td key={week.event} className={week.fixtures === 0 ? "blank" : week.fixtures > 1 ? "double" : ""}>
          <span>{week.fixtures === 0 ? "Blank" : week.opponent}</span>
          {week.fixtures > 1 && <em>Double</em>}
          {week.fixtures > 0 && <small>{week.xp.toFixed(1)} pts{week.p60 != null ? ` · 60+ ${(week.p60 * 100).toFixed(0)}%` : ""}</small>}
        </td>)}
        <td><strong>{player.total_xp.toFixed(1)}</strong></td>
      </tr>)}</tbody>
    </table></div>}
    {data && <p className="model-note">{data.note}</p>}
  </section>;
}
