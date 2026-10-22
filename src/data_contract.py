"""Data contract (D3) for public FPL payloads and Gameweek tables.

Every check collects all violations and raises one ``ContractError``; callers
write nothing when it fails. ``fpl_collect.py`` validates API payloads at the
boundary and Gameweek rows before files are written; ``build_dataset.py``
validates the own seasons it reads. Standalone (stdlib + pandas) so the file
can be copied unchanged into the fpl-data repository.
"""

from __future__ import annotations

import math

import pandas as pd


ELEMENT_KEYS = ("id", "code", "first_name", "second_name", "web_name", "team",
                "element_type", "now_cost", "status")
EVENT_KEYS = ("id", "deadline_time", "finished", "data_checked", "is_current", "is_next")
FIXTURE_KEYS = ("id", "event", "kickoff_time", "team_h", "team_a", "finished",
                "team_h_score", "team_a_score")
HISTORY_KEYS = ("element", "fixture", "opponent_team", "total_points", "was_home",
                "kickoff_time", "round", "minutes", "goals_scored", "own_goals", "value")
PLAYER_RANGE = (500, 1000)      # registered players in a season
GAMEWEEK_PLAYER_RANGE = (300, 1000)  # distinct players with a row in one Gameweek
PRICE_RANGE = (30, 200)          # tenths of a million
MINUTES_RANGE = (0, 120)


class ContractError(ValueError):
    """One or more data-contract violations; nothing should be written."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("Data contract failed:\n- " + "\n- ".join(self.problems))


def _missing(record: dict, keys, where: str) -> list[str]:
    absent = [key for key in keys if key not in record]
    return [f"{where}: missing {absent}"] if absent else []


def _raise(problems: list[str]) -> None:
    if problems:
        raise ContractError(problems)


def validate_bootstrap(data) -> dict:
    """bootstrap-static: registry shape, player count and unique stable codes."""
    if not isinstance(data, dict):
        raise ContractError(["bootstrap-static: not a JSON object"])
    problems = _missing(data, ("elements", "teams", "events"), "bootstrap-static")
    _raise(problems)
    for element in data["elements"]:
        problems += _missing(element, ELEMENT_KEYS, f"element {element.get('id')}")
    for event in data["events"]:
        problems += _missing(event, EVENT_KEYS, f"event {event.get('id')}")
    count = len(data["elements"])
    if not PLAYER_RANGE[0] <= count <= PLAYER_RANGE[1]:
        problems.append(f"bootstrap-static: {count} players outside {PLAYER_RANGE}")
    if len(data["teams"]) != 20:
        problems.append(f"bootstrap-static: {len(data['teams'])} teams, expected 20")
    codes = pd.Series([element.get("code") for element in data["elements"]])
    if codes.duplicated().any():
        problems.append(f"bootstrap-static: duplicate player codes {sorted(codes[codes.duplicated()].unique())[:5]}")
    for element in data["elements"]:
        cost = element.get("now_cost")
        if isinstance(cost, (int, float)) and not PRICE_RANGE[0] <= cost <= PRICE_RANGE[1]:
            problems.append(f"element {element['id']}: now_cost {cost} outside {PRICE_RANGE}")
    _raise(problems)
    return data


def validate_fixtures(data) -> list:
    if not isinstance(data, list) or not data:
        raise ContractError(["fixtures: expected a non-empty list"])
    problems = []
    for fixture in data:
        problems += _missing(fixture, FIXTURE_KEYS, f"fixture {fixture.get('id')}")
        if fixture.get("event") is not None and not fixture.get("kickoff_time"):
            problems.append(f"fixture {fixture.get('id')}: scheduled in event {fixture['event']} without kickoff")
    _raise(problems)
    return data


def validate_element_summary(data, element_id: int) -> dict:
    if not isinstance(data, dict):
        raise ContractError([f"element-summary {element_id}: not a JSON object"])
    problems = _missing(data, ("history", "history_past", "fixtures"), f"element-summary {element_id}")
    _raise(problems)
    for row in data["history"]:
        problems += _missing(row, HISTORY_KEYS, f"element-summary {element_id} fixture {row.get('fixture')}")
        if row.get("element") != element_id:
            problems.append(f"element-summary {element_id}: history row for element {row.get('element')}")
    _raise(problems)
    return data


def validate_live(data, event: int) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ContractError([f"event/{event}/live: missing elements list"])
    return data


def validate_price_moves(previous: dict, current: dict, days: float) -> None:
    """FPL prices move at most 0.1m per day between two registry snapshots."""
    allowed = max(1, math.ceil(days))
    before = {element["id"]: element["now_cost"] for element in previous["elements"]}
    problems = [
        f"element {element['id']}: price {before[element['id']]} -> {element['now_cost']} in {days:.2f} days"
        for element in current["elements"]
        if element["id"] in before and abs(element["now_cost"] - before[element["id"]]) > allowed
    ]
    _raise(problems)


def _team_rows(rows: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    sides = fixtures.set_index("id")[["team_h", "team_a"]]
    joined = rows.join(sides, on="fixture")
    home = joined["was_home"].astype(str).str.lower().eq("true")
    joined["team_id"] = joined["team_h"].where(home, joined["team_a"])
    joined["opponent_id"] = joined["team_a"].where(home, joined["team_h"])
    return joined


def validate_gameweeks(rows: pd.DataFrame, fixtures) -> None:
    """D3 checks on one season's player-fixture rows (vaastav ``merged_gw`` shape).

    New players simply have no rows for earlier Gameweeks; that is valid.
    """
    fixtures = pd.DataFrame(fixtures)
    _raise(_missing(rows.columns, ("element", "fixture", "GW", "kickoff_time", "minutes", "value",
                                   "was_home", "goals_scored", "own_goals"), "gameweek rows"))
    problems = []
    key = ["element", "fixture"]
    duplicated = rows.duplicated(key, keep=False)
    if duplicated.any():
        problems.append(f"{int(duplicated.sum())} duplicate (element, fixture) rows, e.g. "
                        f"{rows.loc[duplicated, key].head(3).values.tolist()}")
    kickoff = rows["kickoff_time"].astype("string").str.strip()
    if kickoff.isna().any() or kickoff.eq("").any():
        problems.append(f"{int(kickoff.isna().sum() + kickoff.eq('').sum())} rows without kickoff_time")
    per_gw = rows.groupby("GW")["element"].nunique()
    low, high = GAMEWEEK_PLAYER_RANGE
    for gw, count in per_gw[(per_gw < low) | (per_gw > high)].items():
        problems.append(f"GW{gw}: {count} players outside {GAMEWEEK_PLAYER_RANGE}")
    minutes = pd.to_numeric(rows["minutes"], errors="coerce")
    if (~minutes.between(*MINUTES_RANGE)).any():
        problems.append(f"{int((~minutes.between(*MINUTES_RANGE)).sum())} rows with minutes outside {MINUTES_RANGE}")
    value = pd.to_numeric(rows["value"], errors="coerce")
    if (~value.between(*PRICE_RANGE)).any():
        problems.append(f"{int((~value.between(*PRICE_RANGE)).sum())} rows with value outside {PRICE_RANGE}")

    ordered = rows.assign(_kickoff=pd.to_datetime(rows["kickoff_time"], utc=True, errors="coerce"),
                          _value=value).sort_values(["element", "_kickoff"])
    step = ordered.groupby("element")["_value"].diff().abs()
    days = ordered.groupby("element")["_kickoff"].diff().dt.total_seconds() / 86400
    jumps = ordered[step > days.apply(lambda d: max(1, math.ceil(d)) if pd.notna(d) else 1)]
    for _, row in jumps.head(5).iterrows():
        problems.append(f"element {row['element']}: price moved more than 0.1m per day before fixture {row['fixture']}")

    teams = _team_rows(rows, fixtures)
    if teams["team_id"].isna().any():
        problems.append(f"{int(teams['team_id'].isna().sum())} rows reference unknown fixtures")
    is_finished = fixtures["finished"].astype(str).str.lower().eq("true")
    finished = fixtures[is_finished & fixtures["event"].isin(per_gw.index)]
    present = set(map(tuple, teams[["fixture", "team_id"]].dropna().astype(int).values))
    for fixture in finished.itertuples():
        for team in (fixture.team_h, fixture.team_a):
            if (fixture.id, team) not in present:
                problems.append(f"fixture {fixture.id}: no rows for team {team}")
    numeric = {column: pd.to_numeric(teams[column], errors="coerce").fillna(0)
               for column in ("goals_scored", "own_goals", "starts") if column in teams}
    teams = teams.assign(**numeric)
    sums = teams.groupby(["fixture", "team_id"])[list(numeric)].sum()
    scores = finished.set_index("id")
    for (fixture_id, team_id), total in sums.iterrows():
        if fixture_id not in scores.index:
            continue
        match = scores.loc[fixture_id]
        if "starts" in total and total["starts"] != 11:
            problems.append(f"fixture {fixture_id} team {team_id}: {total['starts']:.0f} starters, expected 11")
        home = team_id == match["team_h"]
        opponent = match["team_a"] if home else match["team_h"]
        goals = match["team_h_score"] if home else match["team_a_score"]
        own_goals_for = sums["own_goals"].get((fixture_id, opponent), 0)
        if total["goals_scored"] + own_goals_for != goals:
            problems.append(f"fixture {fixture_id} team {team_id}: {total['goals_scored']:.0f} goals + "
                            f"{own_goals_for:.0f} opponent own goals != score {goals}")
    _raise(problems)


def diff_rows(old: pd.DataFrame, new: pd.DataFrame, key=("element", "fixture")) -> pd.DataFrame:
    """Cell-level changes between two versions of a finished round (FPL corrections).

    Compare frames read the same way (strings); a missing row shows as ``<absent>``.
    """
    key = list(key)
    columns = [column for column in new.columns if column in old.columns and column not in key]
    before = old.astype(str).set_index(key)[columns]
    after = new.astype(str).set_index(key)[columns]
    index = before.index.union(after.index)
    before = before.reindex(index).fillna("<absent>").rename_axis(columns="column")
    after = after.reindex(index).fillna("<absent>").rename_axis(columns="column")
    changed = before.ne(after).stack()
    changed = changed[changed].index
    return pd.DataFrame({"old": before.stack()[changed], "new": after.stack()[changed]}).reset_index()


def map_codes(previous: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    """Map season-specific ``id`` to the stable FPL ``code``; ambiguity fails."""
    problems = []
    for label, frame in (("previous", previous), ("current", current)):
        if frame["code"].isna().any():
            problems.append(f"{label} season: players without code")
        duplicated = frame["code"][frame["code"].duplicated()]
        if len(duplicated):
            problems.append(f"{label} season: ambiguous codes {sorted(duplicated.unique())[:5]}")
    _raise(problems)
    return previous[["code", "id"]].merge(
        current[["code", "id"]], on="code", how="outer",
        suffixes=("_previous", "_current"), validate="one_to_one",
    )
