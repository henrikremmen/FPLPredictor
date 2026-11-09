import { useEffect, useMemo, useRef, useState } from "react";
import type { TeamTimeline, TimelinePick, TimelineWeek } from "@fplmodell/api-client";
import { formatMoney, formatRank, FPL_CHIP_NAMES, FPL_CHIP_SHORT, pitchRows, squadDiff } from "@fplmodell/shared";
import { api } from "./api";
import { Icon } from "./icons";

const SEASON_LENGTH = 38;
const pointsLabel = (points: number) => `${points} pt${points === 1 ? "" : "s"}`;

/** Season so far: every Gameweek's squad on the pitch, moves and rank, stepping back in time. */
export function Timeline({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<TeamTimeline | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const root = useRef<HTMLElement>(null);
  const load = () => {
    setError("");
    api.timeline(sessionId).then(result => {
      setData(result);
      setSelected(current => current ?? result.weeks.at(-1)?.event ?? null);
    }).catch(err => setError(err instanceof Error ? err.message : "Could not load the timeline."));
  };
  useEffect(load, [sessionId]);

  const weeks = data?.weeks ?? [];
  const index = weeks.findIndex(week => week.event === selected);
  const week = weeks[index];
  const step = (delta: number) => {
    const next = weeks[index + delta];
    if (next) setSelected(next.event);
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!root.current || root.current.offsetParent === null) return; // page not visible
      if ((event.target as HTMLElement).closest("input, select, textarea")) return;
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  const swipeStart = useRef<number | null>(null);

  if (error) return <div className="error-banner" role="alert"><Icon.Alert size={18} /><span>{error}</span><button onClick={load}>Try again</button></div>;
  if (!data || !week) return <div className="loading"><span className="spinner" />Loading the season…</div>;

  const previous = weeks[index - 1];
  const totals = weeks.at(-1)!;
  return (
    <section ref={root} className="timeline" aria-label="Season timeline">
      <header className="page-heading">
        <div className="page-heading-main">
          <span className="page-icon"><Icon.Calendar size={22} /></span>
          <div><span className="eyebrow">Season so far</span><h1>Timeline</h1>
            <p>GW{weeks[0].event}–GW{totals.event} · {totals.total_points} points · overall rank {formatRank(totals.overall_rank)}</p></div>
        </div>
      </header>

      <SeasonRibbon weeks={weeks} selected={week.event} onSelect={setSelected} />

      <div className="timeline-stepper">
        <button onClick={() => step(-1)} disabled={!previous} aria-label={previous ? `Show GW${previous.event}` : "No earlier Gameweek"}>
          <Icon.ArrowRight size={16} className="flip" />{previous ? `GW${previous.event}` : ""}
        </button>
        <div aria-live="polite">
          <strong>GW{week.event}</strong>
          <span>{week.points} pts{week.chip ? ` · ${FPL_CHIP_NAMES[week.chip] ?? week.chip}` : ""}{week.final ? "" : " · provisional"}</span>
        </div>
        <button onClick={() => step(1)} disabled={!weeks[index + 1]} aria-label={weeks[index + 1] ? `Show GW${weeks[index + 1].event}` : "No later Gameweek"}>
          {weeks[index + 1] ? `GW${weeks[index + 1].event}` : ""}<Icon.ArrowRight size={16} />
        </button>
      </div>

      <WeekStats week={week} />

      <div className="lineup-layout timeline-layout">
        <section className="pitch" aria-label={`Squad in GW${week.event}`}
          onTouchStart={event => { swipeStart.current = event.touches[0].clientX; }}
          onTouchEnd={event => {
            if (swipeStart.current === null) return;
            const distance = event.changedTouches[0].clientX - swipeStart.current;
            swipeStart.current = null;
            if (Math.abs(distance) > 50) step(distance > 0 ? -1 : 1);
          }}>
          <div className="pitch-lines" />
          {pitchRows(week.picks).rows.map((row, rowIndex) => <div className="pitch-row" key={rowIndex}>
            {row.map(pick => <TimelineCard key={pick.id} pick={pick} joined={!!previous && !previous.picks.some(p => p.id === pick.id)} />)}
          </div>)}
        </section>
        <aside className="bench panel">
          <ChangesThisRound week={week} previous={previous} />
          <span className="eyebrow">Bench</span>
          {pitchRows(week.picks).bench.map((pick, benchIndex) => (
            <div className="bench-row" key={pick.id}><span>{pick.position === "GK" ? "GK" : benchIndex}</span>
              <div><strong>{pick.name}</strong><small>{pick.team} · {pick.minutes}′</small></div><b>{pick.points}</b></div>
          ))}
          {week.automatic_subs.length > 0 && <div className="auto-subs">
            <span className="eyebrow">Automatic substitutions</span>
            {week.automatic_subs.map(sub => <p key={sub.out.id}><span className="move-in">↑ {sub.in.name}</span> <span className="move-out">↓ {sub.out.name}</span></p>)}
          </div>}
        </aside>
      </div>
      <p className="model-note">{data.caveat} Use ← and → to step through Gameweeks; swipe the pitch on a phone.</p>
    </section>
  );
}

function SeasonRibbon({ weeks, selected, onSelect }: { weeks: TimelineWeek[]; selected: number; onSelect: (event: number) => void }) {
  const best = Math.max(...weeks.map(week => week.points), 1);
  const byEvent = new Map(weeks.map(week => [week.event, week]));
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    strip.current?.querySelector<HTMLElement>("[aria-current=true]")?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [selected]);
  return (
    <div className="season-ribbon" ref={strip} role="group" aria-label="Gameweeks this season">
      {Array.from({ length: SEASON_LENGTH }, (_, i) => i + 1).map(event => {
        const week = byEvent.get(event);
        if (!week) return <span key={event} className="ribbon-cell future" aria-hidden="true"><i /><small>{event}</small></span>;
        const label = [`GW${event}: ${week.points} points`, week.chip && FPL_CHIP_NAMES[week.chip],
          week.transfer_cost ? `−${week.transfer_cost} hit` : "",
          week.rank_change ? `overall rank ${week.rank_change > 0 ? "up" : "down"} ${formatRank(Math.abs(week.rank_change))}` : ""]
          .filter(Boolean).join(", ");
        return (
          <button key={event} className="ribbon-cell" aria-current={event === selected} aria-label={label} title={label} onClick={() => onSelect(event)}>
            {week.chip ? <em>{FPL_CHIP_SHORT[week.chip] ?? "★"}</em> : <em className="empty" />}
            <i style={{ height: `${Math.max(6, (week.points / best) * 100)}%` }} />
            <small>{event}</small>
            <b className={week.rank_change == null ? "" : week.rank_change > 0 ? "up" : week.rank_change < 0 ? "down" : ""}>
              {week.rank_change == null || week.rank_change === 0 ? "·" : week.rank_change > 0 ? "▲" : "▼"}
            </b>
            {week.transfer_cost > 0 && <span className="hit">−{week.transfer_cost}</span>}
          </button>
        );
      })}
    </div>
  );
}

function WeekStats({ week }: { week: TimelineWeek }) {
  const change = week.rank_change;
  return (
    <dl className="week-stats">
      <div><dt>Points</dt><dd>{week.points}</dd></div>
      <div><dt>GW rank</dt><dd>{formatRank(week.rank)}</dd></div>
      <div><dt>Overall rank</dt><dd>{formatRank(week.overall_rank)}{change ? <span className={change > 0 ? "up" : "down"}> {change > 0 ? "▲" : "▼"} {formatRank(Math.abs(change))}</span> : null}</dd></div>
      <div><dt>Transfers</dt><dd>{week.transfers_made}{week.transfer_cost ? <span className="down"> −{week.transfer_cost}</span> : null}</dd></div>
      <div><dt>Bank · value</dt><dd>{formatMoney(week.bank)} · {formatMoney(week.value)}</dd></div>
      <div><dt>Bench points</dt><dd>{week.bench_points}</dd></div>
    </dl>
  );
}

function TimelineCard({ pick, joined }: { pick: TimelinePick; joined: boolean }) {
  const role = pick.is_captain ? (pick.multiplier === 3 ? "TC" : "C") : pick.is_vice_captain ? "V" : "";
  return (
    <div className={`pitch-player ${pick.multiplier === 0 ? "benched" : ""}`}>
      {role && <span className="role-badge">{role}</span>}
      {joined && <span className="joined-badge" title="New since the previous Gameweek">New</span>}
      <span className="shirt">{pick.position === "GK" ? "◆" : "⬟"}</span>
      <strong>{pick.name}</strong>
      <small>{pointsLabel(pick.points * Math.max(pick.multiplier, 1))} · {pick.team}</small>
    </div>
  );
}

function ChangesThisRound({ week, previous }: { week: TimelineWeek; previous?: TimelineWeek }) {
  const { joined, left } = useMemo(() => squadDiff(previous?.picks, week.picks), [previous, week]);
  const bought = new Map(week.transfers.map(move => [move.in.id, move.in.cost]));
  const sold = new Map(week.transfers.map(move => [move.out.id, move.out.cost]));
  return (
    <div className="round-changes">
      <span className="eyebrow">Changes this round</span>
      {!previous ? <p>First Gameweek of the season.</p> : joined.length === 0 ? <p>Same squad as GW{previous.event}.</p> : <ul>
        {joined.map(player => <li key={player.id} className="move-in">↑ {player.name}{bought.has(player.id) ? <small> {formatMoney(bought.get(player.id))}</small> : null}</li>)}
        {left.map(player => <li key={player.id} className="move-out">↓ {player.name}{sold.has(player.id) ? <small> {formatMoney(sold.get(player.id))}</small> : null}</li>)}
      </ul>}
      {week.transfer_cost > 0 && <p className="down">Hit: −{week.transfer_cost} points</p>}
    </div>
  );
}
