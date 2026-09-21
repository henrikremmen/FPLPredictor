"""Public-data manager, Gameweek and mini-league analysis for the web app."""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock
import time

import numpy as np
import pandas as pd

from fpl_app import AppError, FPLClient, ImportedTeam


def _number(value, default=0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _rounded(value, digits=1):
    return round(float(value), digits)


class AnalyticsService:
    """Build manager analysis while caching immutable public FPL responses."""

    def __init__(self, client: FPLClient | None = None, ttl_seconds: int = 300) -> None:
        self.client = client or FPLClient()
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, object]] = {}
        self._lock = RLock()

    def get(self, endpoint: str):
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(endpoint)
            if cached and now - cached[0] < self.ttl_seconds:
                return deepcopy(cached[1])
        value = self.client.get(endpoint)
        with self._lock:
            self._cache[endpoint] = (now, deepcopy(value))
        return value

    def many(self, endpoints: list[str]) -> dict[str, object]:
        unique = list(dict.fromkeys(endpoints))
        if not unique:
            return {}
        with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
            values = list(pool.map(self.get, unique))
        return dict(zip(unique, values))

    def many_optional(self, endpoints: list[str]) -> dict[str, object]:
        """Fetch independent rival endpoints without losing all analysis to one 404."""
        unique = list(dict.fromkeys(endpoints))
        if not unique:
            return {}

        def optional(endpoint: str):
            try:
                return endpoint, self.get(endpoint)
            except AppError:
                return endpoint, None

        with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
            rows = list(pool.map(optional, unique))
        return {endpoint: value for endpoint, value in rows if value is not None}

    def _standings(self, league_id: int, entry_id: int, max_members: int = 100) -> tuple[dict, list[dict], bool]:
        rows: list[dict] = []
        league = {}
        page = 1
        has_next = True
        while has_next and len(rows) < max_members and page <= 10:
            payload = self.get(
                f"leagues-classic/{league_id}/standings/?page_standings={page}"
            )
            league = payload.get("league", league)
            standings = payload.get("standings", {})
            rows.extend(standings.get("results", []))
            has_next = bool(standings.get("has_next"))
            page += 1
        sampled = has_next
        rows = rows[:max_members]
        if entry_id not in {int(row.get("entry", -1)) for row in rows}:
            # The selected manager is still useful as an explicit comparison,
            # even when a very large league has been capped for API courtesy.
            entry = self.get(f"entry/{entry_id}/")
            rows.append({
                "entry": entry_id,
                "entry_name": entry.get("name", "Ditt lag"),
                "player_name": (
                    f"{entry.get('player_first_name', '')} {entry.get('player_last_name', '')}"
                ).strip(),
                "rank": None,
                "last_rank": None,
                "event_total": entry.get("summary_event_points", 0),
                "total": entry.get("summary_overall_points", 0),
            })
        return league, rows, sampled

    def build(self, team: ImportedTeam, *, event: int | None = None,
              league_id: int | None = None) -> dict:
        entry_id = int(team.entry_id)
        base = self.many([
            f"entry/{entry_id}/", f"entry/{entry_id}/history/",
            f"entry/{entry_id}/transfers/", "bootstrap-static/",
        ])
        entry = base[f"entry/{entry_id}/"]
        history = base[f"entry/{entry_id}/history/"]
        transfers = base[f"entry/{entry_id}/transfers/"]
        bootstrap = base["bootstrap-static/"]
        event_meta = {int(row["id"]): row for row in bootstrap.get("events", [])}
        player_meta = {int(row["id"]): row for row in bootstrap.get("elements", [])}
        team_names = {int(row["id"]): row.get("short_name", row.get("name", ""))
                      for row in bootstrap.get("teams", [])}
        history_rows = sorted(history.get("current", []), key=lambda row: int(row["event"]))
        if not history_rows:
            raise AppError("FPL-laget har ingen Gameweek-historikk å analysere ennå.")

        completed_events = [
            int(row["event"]) for row in history_rows
            if event_meta.get(int(row["event"]), {}).get("finished")
            or row.get("rank") is not None
        ]
        available_events = [int(row["event"]) for row in history_rows]
        default_event = max(completed_events or available_events)
        selected_event = int(event if event is not None else default_event)
        if selected_event not in available_events:
            raise AppError(f"GW{selected_event} finnes ikke i laghistorikken.")
        benchmark_event = max(available_events)

        classic = entry.get("leagues", {}).get("classic", [])
        mini_leagues = [{
            "id": int(row["id"]), "name": row.get("name", "Ukjent liga"),
            "league_type": row.get("league_type"),
        } for row in classic if row.get("league_type") == "x"]
        if league_id is None and mini_leagues:
            league_id = mini_leagues[0]["id"]
        if league_id is not None and int(league_id) not in {row["id"] for row in mini_leagues}:
            raise AppError("Valgt miniliga tilhører ikke dette offentlige FPL-laget.")

        overall_league = next(
            (row for row in classic if row.get("short_name") == "overall"), None
        )
        top_sample_rows: list[dict] = []
        if overall_league is not None:
            for page in [1, 50, 100, 150, 200]:
                try:
                    payload = self.get(
                        f"leagues-classic/{int(overall_league['id'])}/standings/"
                        f"?page_standings={page}"
                    )
                except AppError:
                    continue
                page_rows = payload.get("standings", {}).get("results", [])
                top_sample_rows.extend(page_rows[index] for index in range(
                    0, len(page_rows), max(1, len(page_rows) // 5)
                ) if len(top_sample_rows) < 25)
        top_sample_rows = list({int(row["entry"]): row for row in top_sample_rows}.values())[:25]

        league = None
        standings: list[dict] = []
        sampled = False
        if league_id is not None:
            league, standings, sampled = self._standings(int(league_id), entry_id)
        members = [int(row["entry"]) for row in standings]
        if not members:
            members = [entry_id]

        own_events = sorted(set(completed_events + [selected_event]))
        own_endpoints = []
        for gw in own_events:
            own_endpoints += [f"entry/{entry_id}/event/{gw}/picks/", f"event/{gw}/live/"]
        fetched = self.many(own_endpoints)
        rival_endpoints = []
        for member in members:
            rival_endpoints.append(f"entry/{member}/history/")
            rival_endpoints.append(f"entry/{member}/event/{selected_event}/picks/")
            if benchmark_event != selected_event:
                rival_endpoints.append(f"entry/{member}/event/{benchmark_event}/picks/")
        for row in top_sample_rows:
            rival_endpoints.append(
                f"entry/{int(row['entry'])}/event/{benchmark_event}/picks/"
            )
        fetched.update(self.many_optional(rival_endpoints))

        live_by_event = {
            gw: {
                int(row["id"]): row.get("stats", {})
                for row in fetched[f"event/{gw}/live/"].get("elements", [])
            }
            for gw in own_events
        }
        own_picks_by_event = {
            gw: fetched[f"entry/{entry_id}/event/{gw}/picks/"]
            for gw in own_events
        }

        chips = {int(row.get("event", 0)): row.get("name")
                 for row in history.get("chips", [])}
        transfer_swing: dict[int, float] = defaultdict(float)
        for transfer in transfers:
            gw = int(transfer.get("event", 0))
            if gw not in live_by_event:
                continue
            scores = live_by_event[gw]
            player_in = int(transfer.get("element_in", 0))
            player_out = int(transfer.get("element_out", 0))
            transfer_swing[gw] += (
                _number(scores.get(player_in, {}).get("total_points"))
                - _number(scores.get(player_out, {}).get("total_points"))
            )

        timeline = []
        cumulative_vs_average = 0.0
        previous_rank = None
        previous_value = None
        captain_bonus_total = 0.0
        captain_opportunity_total = 0.0
        position_points = Counter()
        for row in history_rows:
            gw = int(row["event"])
            average = _number(event_meta.get(gw, {}).get("average_entry_score"))
            points = _number(row.get("points"))
            net_vs_average = points - average
            cumulative_vs_average += net_vs_average
            overall_rank = row.get("overall_rank")
            rank_change = None
            if previous_rank is not None and overall_rank is not None:
                rank_change = int(previous_rank) - int(overall_rank)
            value = _number(row.get("value")) / 10
            value_change = None if previous_value is None else value - previous_value
            captain = None
            captain_bonus = 0.0
            captain_loss = 0.0
            if gw in own_picks_by_event and gw in live_by_event:
                picks = own_picks_by_event[gw].get("picks", [])
                scores = live_by_event[gw]
                starter_scores = []
                for pick in picks:
                    player_id = int(pick["element"])
                    raw = _number(scores.get(player_id, {}).get("total_points"))
                    multiplier = int(pick.get("multiplier", 0))
                    if multiplier > 0:
                        starter_scores.append(raw)
                        position_points[str(pick.get("element_type", "?"))] += raw
                    if pick.get("is_captain"):
                        captain = player_meta.get(player_id, {}).get("web_name", str(player_id))
                        captain_bonus = raw * max(0, multiplier - 1)
                best = max(starter_scores, default=0.0)
                captain_loss = max(0.0, best - captain_bonus)
                captain_bonus_total += captain_bonus
                captain_opportunity_total += captain_loss
            timeline.append({
                "event": gw, "points": int(points),
                "total_points": int(_number(row.get("total_points"))),
                "global_average": _rounded(average),
                "vs_average": _rounded(net_vs_average),
                "cumulative_vs_average": _rounded(cumulative_vs_average),
                "overall_rank": int(overall_rank) if overall_rank is not None else None,
                "rank_change": rank_change,
                "transfers": int(_number(row.get("event_transfers"))),
                "transfer_cost": int(_number(row.get("event_transfers_cost"))),
                "transfer_swing": _rounded(transfer_swing.get(gw, 0)),
                "bench_points": int(_number(row.get("points_on_bench"))),
                "team_value": _rounded(value),
                "value_change": _rounded(value_change) if value_change is not None else None,
                "captain": captain, "captain_bonus": _rounded(captain_bonus),
                "captain_opportunity_loss": _rounded(captain_loss),
                "chip": chips.get(gw),
                "finished": bool(event_meta.get(gw, {}).get("finished")),
            })
            if overall_rank is not None:
                previous_rank = overall_rank
            previous_value = value

        finished_timeline = [row for row in timeline if row["finished"]]
        scored_timeline = finished_timeline or timeline
        latest = timeline[-1]
        best_week = max(scored_timeline, key=lambda row: row["points"])
        worst_week = min(scored_timeline, key=lambda row: row["points"])

        selected_live = live_by_event[selected_event]
        selected_own = own_picks_by_event[selected_event]
        selected_league_picks = {
            member: fetched[f"entry/{member}/event/{selected_event}/picks/"]
            for member in members
            if f"entry/{member}/event/{selected_event}/picks/" in fetched
        }
        field = self._field_metrics(selected_league_picks, len(selected_league_picks))
        squad = self._squad_analysis(
            selected_own, selected_live, player_meta, team_names, field
        )
        relative_impacts = self._relative_impacts(
            selected_own, selected_live, player_meta, team_names, field
        )

        benchmark_picks = {
            member: fetched[f"entry/{member}/event/{benchmark_event}/picks/"]
            for member in members
            if f"entry/{member}/event/{benchmark_event}/picks/" in fetched
        }
        benchmark_field = self._field_metrics(benchmark_picks, len(benchmark_picks))
        top_picks = {
            int(row["entry"]): fetched[
                f"entry/{int(row['entry'])}/event/{benchmark_event}/picks/"
            ]
            for row in top_sample_rows
            if f"entry/{int(row['entry'])}/event/{benchmark_event}/picks/" in fetched
        }
        top_field = self._field_metrics(top_picks, len(top_picks))
        league_payload = self._league_analysis(
            standings, members, fetched, entry_id, selected_event,
            history_rows, sampled, league, benchmark_field, player_meta,
            len(benchmark_picks),
        ) if league is not None else None
        decisions = self._decision_support(team, benchmark_field, top_field, player_meta)

        total_points = int(latest["total_points"])
        overall_rank = latest["overall_rank"]
        total_players = int(_number(
            event_meta.get(benchmark_event, {}).get("ranked_count"), 0
        ))
        percentile = None
        if overall_rank and total_players:
            percentile = 100 * (1 - (overall_rank - 1) / total_players)
        if percentile is None:
            last_rank_percent = next((
                row.get("overall_rank_percentage") for row in reversed(history_rows)
                if row.get("overall_rank_percentage") is not None
            ), None)
            if last_rank_percent is not None:
                percentile = 100 - _number(last_rank_percent)
        summary = {
            "total_points": total_points,
            "overall_rank": overall_rank,
            "percentile": _rounded(percentile) if percentile is not None else None,
            "average_points": _rounded(np.mean([row["points"] for row in scored_timeline])),
            "points_vs_global_average": _rounded(sum(row["vs_average"] for row in scored_timeline)),
            "best_week": {"event": best_week["event"], "points": best_week["points"]},
            "worst_week": {"event": worst_week["event"], "points": worst_week["points"]},
            "bench_points": sum(row["bench_points"] for row in scored_timeline),
            "transfer_cost": sum(row["transfer_cost"] for row in scored_timeline),
            "transfer_swing": _rounded(sum(row["transfer_swing"] for row in scored_timeline)),
            "captain_bonus": _rounded(captain_bonus_total),
            "captain_opportunity_loss": _rounded(captain_opportunity_total),
            "team_value": latest["team_value"],
        }
        top_average = (_rounded(np.mean([
            _number(row.get("total")) for row in top_sample_rows
        ])) if top_sample_rows else None)
        top_ownership = [{
            "id": player_id,
            "name": player_meta.get(player_id, {}).get("web_name", str(player_id)),
            "effective_ownership": _rounded(metrics["effective_ownership"]),
            "ownership": _rounded(metrics["ownership"]),
            "captain_rate": _rounded(metrics["captain_rate"]),
            "global_ownership": _rounded(_number(
                player_meta.get(player_id, {}).get("selected_by_percent")
            )),
        } for player_id, metrics in top_field.items()]
        top_ownership.sort(key=lambda row: (-row["effective_ownership"], row["name"]))
        return {
            "entry_id": entry_id,
            "manager_name": team.manager_name,
            "team_name": team.team_name,
            "available_events": available_events,
            "completed_events": completed_events,
            "selected_event": selected_event,
            "benchmark_event": benchmark_event,
            "leagues": mini_leagues,
            "selected_league_id": int(league_id) if league_id is not None else None,
            "summary": summary,
            "global_benchmark": {
                "sample_label": "Stratifisert utvalg fra rank 1–10 000",
                "sample_size": len(top_picks),
                "sample_average_total": top_average,
                "points_gap": (_rounded(total_points - top_average)
                               if top_average is not None else None),
                "ownership": top_ownership[:30],
            },
            "timeline": timeline,
            "position_points": {
                "GK": _rounded(position_points.get("1", 0)),
                "DEF": _rounded(position_points.get("2", 0)),
                "MID": _rounded(position_points.get("3", 0)),
                "FWD": _rounded(position_points.get("4", 0)),
            },
            "gameweek": {
                "event": selected_event,
                "points": int(_number(selected_own.get("entry_history", {}).get("points"))),
                "squad": squad,
                "captain": next((row for row in squad if row["is_captain"]), None),
                "best_contributors": sorted(
                    [row for row in squad if row["multiplier"] > 0],
                    key=lambda row: (row["effective_points"], row["name"]), reverse=True,
                )[:5],
                "missed_bench_points": sum(
                    row["raw_points"] for row in squad if row["multiplier"] == 0
                ),
                "relative_gain": _rounded(sum(row["league_swing"] for row in relative_impacts)),
                "top_gains": [row for row in relative_impacts if row["league_swing"] > 0][:5],
                "top_losses": [row for row in reversed(relative_impacts)
                               if row["league_swing"] < 0][:5],
            },
            "league": league_payload,
            "decisions": decisions,
            "method": (
                "Liga-EO er gjennomsnittlig poengmultiplikator i det analyserte utvalget. "
                "Relativt bidrag = faktiske spillerpoeng × (din multiplikator − liga-EO/100)."
            ),
            "caveats": [
                "Offentlige FPL-tropper blir først synlige etter deadline.",
                "Global sammenligning bruker FPLs samlede eierskap og offisielle Gameweek-snitt.",
                "Liga-EO er eksakt for små ligaer; ligaer over 100 medlemmer analyseres som et merket utvalg.",
                "Topprank-EO bruker et stratifisert offentlig utvalg og er ikke en full opptelling av alle topp 10 000.",
            ],
        }

    @staticmethod
    def _field_metrics(picks_by_entry: dict[int, dict], member_count: int) -> dict[int, dict]:
        counts: dict[int, Counter] = defaultdict(Counter)
        denominator = max(1, member_count)
        for payload in picks_by_entry.values():
            for pick in payload.get("picks", []):
                player_id = int(pick["element"])
                multiplier = int(pick.get("multiplier", 0))
                counts[player_id]["owned"] += 1
                counts[player_id]["started"] += int(multiplier > 0)
                counts[player_id]["captained"] += int(bool(pick.get("is_captain")))
                counts[player_id]["multiplier"] += multiplier
        return {player_id: {
            "ownership": 100 * row["owned"] / denominator,
            "start_rate": 100 * row["started"] / denominator,
            "captain_rate": 100 * row["captained"] / denominator,
            "effective_ownership": 100 * row["multiplier"] / denominator,
            "owners": int(row["owned"]),
        } for player_id, row in counts.items()}

    @staticmethod
    def _squad_analysis(picks_payload: dict, live: dict[int, dict],
                        players: dict[int, dict], teams: dict[int, str],
                        field: dict[int, dict]) -> list[dict]:
        result = []
        for pick in picks_payload.get("picks", []):
            player_id = int(pick["element"])
            meta = players.get(player_id, {})
            raw = _number(live.get(player_id, {}).get("total_points"))
            multiplier = int(pick.get("multiplier", 0))
            eo = _number(field.get(player_id, {}).get("effective_ownership"))
            result.append({
                "id": player_id,
                "name": meta.get("web_name", str(player_id)),
                "team": teams.get(int(meta.get("team", 0)), ""),
                "position": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}.get(
                    int(meta.get("element_type", pick.get("element_type", 0))), "?"
                ),
                "pick_position": int(pick.get("position", 0)),
                "multiplier": multiplier,
                "is_captain": bool(pick.get("is_captain")),
                "is_vice_captain": bool(pick.get("is_vice_captain")),
                "raw_points": int(raw),
                "effective_points": int(raw * multiplier),
                "global_ownership": _rounded(_number(meta.get("selected_by_percent"))),
                "league_ownership": _rounded(field.get(player_id, {}).get("ownership", 0)),
                "league_effective_ownership": _rounded(eo),
                "league_swing": _rounded(raw * (multiplier - eo / 100)),
                "minutes": int(_number(live.get(player_id, {}).get("minutes"))),
            })
        return sorted(result, key=lambda row: row["pick_position"])

    @staticmethod
    def _relative_impacts(picks_payload: dict, live: dict[int, dict],
                          players: dict[int, dict], teams: dict[int, str],
                          field: dict[int, dict]) -> list[dict]:
        own = {int(row["element"]): int(row.get("multiplier", 0))
               for row in picks_payload.get("picks", [])}
        impacts = []
        for player_id in set(field) | set(own):
            meta = players.get(player_id, {})
            raw = _number(live.get(player_id, {}).get("total_points"))
            eo = _number(field.get(player_id, {}).get("effective_ownership"))
            multiplier = own.get(player_id, 0)
            impacts.append({
                "id": player_id,
                "name": meta.get("web_name", str(player_id)),
                "team": teams.get(int(meta.get("team", 0)), ""),
                "raw_points": int(raw),
                "your_multiplier": multiplier,
                "league_effective_ownership": _rounded(eo),
                "league_swing": _rounded(raw * (multiplier - eo / 100)),
                "owned": player_id in own,
            })
        return sorted(impacts, key=lambda row: (row["league_swing"], row["name"]), reverse=True)

    @staticmethod
    def _league_analysis(standings: list[dict], members: list[int], fetched: dict,
                         entry_id: int, selected_event: int, own_history: list[dict],
                         sampled: bool, league: dict, field: dict[int, dict],
                         players: dict[int, dict], analyzed_managers: int) -> dict:
        rival_histories = {
            member: fetched[f"entry/{member}/history/"].get("current", [])
            for member in members
            if f"entry/{member}/history/" in fetched
        }
        all_events = sorted({
            int(row["event"]) for rows in rival_histories.values() for row in rows
        })
        development = []
        for gw in all_events:
            totals = []
            own_total = None
            for member, rows in rival_histories.items():
                row = next((item for item in rows if int(item["event"]) == gw), None)
                if row is None:
                    continue
                total = int(_number(row.get("total_points")))
                totals.append((member, total))
                if member == entry_id:
                    own_total = total
            if own_total is None or not totals:
                continue
            ordered = sorted(totals, key=lambda item: (-item[1], item[0]))
            own_rank = next(index for index, item in enumerate(ordered, 1) if item[0] == entry_id)
            development.append({
                "event": gw, "rank": own_rank, "members": len(ordered),
                "own_total": own_total, "leader_total": ordered[0][1],
                "gap_to_leader": own_total - ordered[0][1],
                "league_average": _rounded(np.mean([total for _, total in ordered])),
            })

        standing_rows = [{
            "rank": row.get("rank"), "last_rank": row.get("last_rank"),
            "entry": int(row["entry"]), "team_name": row.get("entry_name", ""),
            "manager_name": row.get("player_name", ""),
            "event_points": int(_number(row.get("event_total"))),
            "total_points": int(_number(row.get("total"))),
            "is_you": int(row["entry"]) == entry_id,
        } for row in standings]
        standing_rows.sort(key=lambda row: (row["rank"] is None, row["rank"] or 999999))
        you = next((row for row in standing_rows if row["is_you"]), None)
        leader = standing_rows[0] if standing_rows else None
        gap_to_leader = None
        if you and leader:
            gap_to_leader = you["total_points"] - leader["total_points"]
        ownership = []
        for player_id, metrics in field.items():
            meta = players.get(player_id, {})
            ownership.append({
                "id": player_id, "name": meta.get("web_name", str(player_id)),
                "ownership": _rounded(metrics["ownership"]),
                "start_rate": _rounded(metrics["start_rate"]),
                "captain_rate": _rounded(metrics["captain_rate"]),
                "effective_ownership": _rounded(metrics["effective_ownership"]),
                "global_ownership": _rounded(_number(meta.get("selected_by_percent"))),
            })
        ownership.sort(key=lambda row: (-row["effective_ownership"], row["name"]))
        weeks_left = max(0, 38 - selected_event)
        if you and you["rank"] == 1:
            mode = "protect"
            advice = "Du leder ligaen. Prioriter høy forventning og de største EO-truslene; ta selektiv risiko."
        elif gap_to_leader is not None and weeks_left <= 8 and abs(gap_to_leader) >= 20:
            mode = "chase"
            advice = "Du jager sent i sesongen. Bruk modellsterke liga-differensialer og vurder avvikende kaptein."
        else:
            mode = "balanced"
            advice = "Spill balansert: maksimer forventede poeng og bruk differensialer bare når modellen støtter dem."
        return {
            "id": int(league.get("id")), "name": league.get("name", "Miniliga"),
            "member_count": len(members), "analyzed_managers": analyzed_managers,
            "sampled": sampled,
            "your_rank": you.get("rank") if you else None,
            "gap_to_leader": gap_to_leader,
            "leader": leader, "standings": standing_rows,
            "development": development, "ownership": ownership[:30],
            "mode": mode, "advice": advice,
        }

    @staticmethod
    def _decision_support(team: ImportedTeam, field: dict[int, dict],
                          top_field: dict[int, dict], players: dict[int, dict]) -> dict:
        market = team.market.drop_duplicates("id").copy()
        score = "decision_points" if "decision_points" in market else "recommended_points"
        owned = set(team.squad["id"].astype(int))
        lineup = team.lineup_squad if team.lineup_squad is not None else team.squad
        projected_multipliers = {int(row.id): 0 for row in team.squad.itertuples()}
        try:
            from fpl_app import optimal_lineup
            selection = optimal_lineup(lineup)
            projected_multipliers.update({int(row.id): 1 for row in selection["starters"].itertuples()})
            captain = next(
                (row for row in selection["starters"].itertuples()
                 if getattr(row, "role", "") == "C"), None
            )
            if captain is not None:
                projected_multipliers[int(captain.id)] = 2
        except (AppError, KeyError, ValueError):
            pass

        rows = []
        for row in market.itertuples():
            player_id = int(row.id)
            eo = _number(field.get(player_id, {}).get("effective_ownership"))
            top_eo = _number(top_field.get(player_id, {}).get("effective_ownership"))
            projection = _number(getattr(row, score, 0))
            global_ownership = _number(getattr(row, "selected_by_percent", 0))
            multiplier = projected_multipliers.get(player_id, 0)
            rows.append({
                "id": player_id, "name": str(row.name), "team": str(row.team),
                "position": str(row.position), "price": int(row.price),
                "projection": _rounded(projection, 2),
                "league_effective_ownership": _rounded(eo),
                "league_ownership": _rounded(field.get(player_id, {}).get("ownership", 0)),
                "top10k_effective_ownership": _rounded(top_eo),
                "global_ownership": _rounded(global_ownership),
                "owned": player_id in owned,
                "projected_multiplier": multiplier,
                "rank_exposure": _rounded(projection * (multiplier - eo / 100), 2),
                "differential_value": _rounded(projection * max(0, 1 - eo / 100), 2),
                "threat_value": _rounded(projection * eo / 100, 2),
                "status": str(getattr(row, "status", "a")),
                "opponent": str(getattr(row, "opponent", "")),
            })
        selectable = [row for row in rows if row["status"] not in {"u", "i"}]
        differentials = sorted(
            [row for row in selectable if not row["owned"]
             and row["league_effective_ownership"] < 35 and row["projection"] > 0],
            key=lambda row: (row["differential_value"], row["projection"]), reverse=True,
        )[:10]
        threats = sorted(
            [row for row in selectable if not row["owned"]
             and row["league_effective_ownership"] >= 20],
            key=lambda row: (row["threat_value"], row["projection"]), reverse=True,
        )[:10]
        leverage = sorted(
            [row for row in selectable if row["owned"] and row["projected_multiplier"] > 0],
            key=lambda row: row["rank_exposure"], reverse=True,
        )[:10]
        captain_pool = sorted(
            [row for row in selectable if row["owned"] and row["projected_multiplier"] > 0],
            key=lambda row: row["projection"], reverse=True,
        )[:5]
        for row in captain_pool:
            row["captain_rank_edge"] = _rounded(
                row["projection"] * (2 - row["league_effective_ownership"] / 100), 2
            )
        return {
            "horizon": team.horizon,
            "forecast_events": list(range(team.target_event, team.target_event + team.horizon)),
            "differentials": differentials,
            "threats": threats,
            "leverage": leverage,
            "captain_matrix": captain_pool,
        }
