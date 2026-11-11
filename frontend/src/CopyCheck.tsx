import { Fragment, useEffect, useState } from "react";
import type { CopyCheck as Data, CopyCheckMember, TeamResponse } from "@fplmodell/api-client";
import { FPL_CHIP_NAMES } from "@fplmodell/shared";
import { api } from "./api";

const percent = (value: number | null | undefined) => value == null ? "–" : `${Math.round(value * 100)}%`;
const chips = (rows: CopyCheckMember["same_chips"]) => rows.map(row => `${FPL_CHIP_NAMES[row.chip] ?? row.chip} GW${row.event}`).join(", ");

function Evidence({ member }: { member: CopyCheckMember }) {
  return <div className="copy-evidence">
    <div><span className="eyebrow">Rarest shared buys with {member.closest.name}</span>{member.evidence.length ? <ul>{member.evidence.map(row => <li key={`${row.event}-${row.player}`}>GW{row.event}: both bought <strong>{row.player}</strong>, {row.share}% of managers did</li>)}</ul> : <p className="empty-copy">No shared buys.</p>}
      <p className="empty-copy">{member.follows} buys one round after {member.closest.name}. Same chips: {chips(member.same_chips) || "none"}.</p></div>
    <div><span className="eyebrow">Squad overlap per round · bar = {member.name.split(" ")[0]}, line = typical manager</span><div className="copy-series">{member.series.map(row => <span key={row.event} title={`GW${row.event}: ${percent(row.overlap)} vs typical ${percent(row.typical)}`}><b style={{ height: `${row.overlap * 100}%` }} />{row.typical != null && <i style={{ bottom: `${row.typical * 100}%` }} />}<small>{row.event}</small></span>)}</div></div>
  </div>;
}

/** Who in a mini-league looks most like a well-known YouTuber, or like each other, over the season. */
export function CopyCheck({ team, revision }: { team: TeamResponse; revision: number }) {
  const [league, setLeague] = useState<number | undefined>();
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  useEffect(() => {
    setError("");
    api.copyCheck(team.session_id, league).then(setData).catch(err => setError(err instanceof Error ? err.message : "Could not load the copy check."));
  }, [team.session_id, league, revision]);

  if (error) return <div className="error-banner" role="alert"><p>{error}</p></div>;
  if (!data) return <div className="loading"><span className="spinner" />Loading the copy check…</div>;
  if (!data.available || !data.members || !data.friends) return <section className="panel"><h2>No copy check yet</h2><p>Press Update: after the top managers it compares every finished round of your mini-leagues with the YouTubers and with each other. The first run takes about three minutes, later runs about one. Terminal: <code>.venv/bin/python src/copy_check.py collect --entry {team.entry_id}</code></p></section>;

  const friends = data.friends;
  return <>
    <section className="panel top-explainer">
      <div className="section-title"><div><span className="eyebrow">Copy check · GW1–GW{data.event_through}</span><h2>{data.league!.name}</h2></div>
        {(data.leagues?.length ?? 0) > 1 && <label>Mini-league<select value={data.league!.id} onChange={event => setLeague(Number(event.target.value))}>{data.leagues!.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}</div>
      <p>Similarity, not proof. Every finished round of public squads is compared with {data.creators?.length} YouTubers and with each other. Shared players and moves count more the rarer they were, and every number is measured against {data.baseline_size} random managers from the overall top 1,000,000. The signal takes the stronger of squad overlap and same-round buys. <strong>Strong</strong> = more alike than 95% of them, <strong>Some</strong> = 80%. A buy is a net squad change since the previous round. YouTubers resemble each other too, so the closest one is the best match, not necessarily the only source.</p>
    </section>
    <section className="panel analysis-section table-panel"><div className="section-title"><div><span className="eyebrow">Members</span><h2>Who looks most like whom</h2></div><span className="legend">Click a row for the evidence</span></div>
      <div className="analytics-table-wrap"><table className="analytics-table copy-table"><thead><tr><th>Member</th><th>Closest YouTuber</th><th>Signal</th><th>Squad overlap</th><th>Same-round buys</th><th>Same chips</th><th>Closest friend</th></tr></thead>
        <tbody>{data.members.map(row => <Fragment key={row.entry}>
          <tr className={row.is_you ? "you-row copy-row" : "copy-row"} onClick={() => setOpen(open === row.entry ? null : row.entry)} aria-expanded={open === row.entry}>
            <td><strong>{row.name}</strong>{row.is_you && <small> YOU</small>}<small>{row.team_name}</small></td>
            <td>{row.closest.name}</td>
            <td><span className={`copy-signal ${row.signal.label.toLowerCase()}`}>{row.signal.label}</span><small>beats {row.signal.percentile.toFixed(0)}%</small></td>
            <td>{percent(row.overlap)}<small>typical {percent(row.overlap_typical)}</small></td>
            <td>{row.same_buys}<small>beats {row.buys_percentile.toFixed(0)}%</small></td>
            <td>{row.same_chips.length}<small>{chips(row.same_chips)}</small></td>
            <td>{row.closest_friend ? <>{row.closest_friend.name}<small>beats {row.closest_friend.score.toFixed(0)}% · {row.closest_friend.same_buys} same buys</small></> : "–"}</td>
          </tr>
          {open === row.entry && <tr className="copy-detail"><td colSpan={7}><Evidence member={row} /></td></tr>}
        </Fragment>)}</tbody></table></div>
    </section>
    <section className="panel analysis-section table-panel"><div className="section-title"><div><span className="eyebrow">Friend vs friend</span><h2>How alike the squads in the league are</h2></div><span className="legend">Row compared with column · share of 75 random managers the row is more alike to the column than</span></div>
      <div className="analytics-table-wrap"><table className="analytics-table copy-matrix"><thead><tr><th />{friends.members.map((row, i) => <th key={row.entry} title={row.name}>{i + 1}</th>)}</tr></thead>
        <tbody>{friends.members.map((row, i) => <tr key={row.entry}><td><strong>{i + 1}. {row.name}</strong></td>{friends.scores[i].map((score, j) => <td key={j} style={score == null ? undefined : { background: `rgba(52, 211, 120, ${score >= 80 ? (score - 60) / 80 : 0})` }}>{score == null ? "" : score.toFixed(0)}</td>)}</tr>)}</tbody></table></div>
    </section>
    <p className="model-note">Squads become public after each deadline, so a copy shows up the round it happens. Transfer times are not used: YouTubers reveal moves in videos and often make them late.</p>
  </>;
}
