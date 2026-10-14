"""Local result-based Elo challenger; this is not the ClubElo rating.

Callers must supply a prediction cutoff, preferably a captured FPL deadline.
Historical availability below is a conservative next-day proxy, not evidence
of when a provider published a result. Retrospective experiments remain so
labelled until evaluated on prospectively frozen inputs.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from external_context import team_key

ELO_FEATURES = ["elo_team", "elo_opponent", "elo_difference", "elo_expected_score",
                "elo_team_games", "elo_opponent_games"]


def load_results(root: Path) -> pd.DataFrame:
    rows = []
    for path in sorted((Path(root) / "data-source/data").glob("*/fixtures.csv")):
        team_path = path.parent / "teams.csv"
        if not team_path.exists():
            continue
        teams = pd.read_csv(team_path).set_index("id")["name"].map(team_key)
        fixtures = pd.read_csv(path)
        for match in fixtures.to_dict("records"):
            if str(match.get("finished")).lower() != "true":
                continue
            kickoff = pd.to_datetime(match.get("kickoff_time"), utc=True, errors="coerce")
            if pd.isna(kickoff) or pd.isna(match.get("team_h_score")) or pd.isna(match.get("team_a_score")):
                continue
            rows.append({"match_id": f"{path.parent.name}:{match['id']}",
                "available_at": kickoff.normalize() + pd.Timedelta(days=1),
                "home": teams.loc[match["team_h"]], "away": teams.loc[match["team_a"]],
                "home_goals": float(match["team_h_score"]), "away_goals": float(match["team_a_score"])})
    return pd.DataFrame(rows)


def attach_elo(rows: pd.DataFrame, results: pd.DataFrame, *, k: float = 20.,
               home_advantage: float = 60.) -> pd.DataFrame:
    """Sweep results strictly before each cutoff; same-time games update together.

No season reset: strength carries across years. New teams start at 1500 with
zero observed games, exposing the cold start rather than claiming certainty.
"""
    required = {"prediction_cutoff", "team", "opp_team_name", "was_home"}
    if required - set(rows):
        raise ValueError(f"Missing Elo query columns: {sorted(required - set(rows))}")
    queries = rows.copy()
    cutoffs = pd.to_datetime(queries.prediction_cutoff, utc=True, errors="raise")
    if cutoffs.isna().any() or queries[["team", "opp_team_name"]].isna().any().any():
        raise ValueError("Elo needs known teams and cutoffs")
    home = queries.was_home.astype(str).str.lower().map(
        {"true": 1, "false": -1, "1": 1, "0": -1, "1.0": 1, "0.0": -1})
    if home.isna().any():
        raise ValueError("Unknown home/away flag")
    results = results.copy()
    if results.match_id.duplicated().any():
        raise ValueError("Duplicate result IDs")
    results["available_at"] = pd.to_datetime(results.available_at, utc=True, errors="raise")
    if results[["available_at", "home", "away", "home_goals", "away_goals"]].isna().any().any():
        raise ValueError("Incomplete results")
    batches = list(results.sort_values(["available_at", "match_id"]).groupby("available_at", sort=True))
    ratings, games, pointer = {}, {}, 0
    output = np.empty((len(rows), len(ELO_FEATURES)))
    for index in np.argsort(cutoffs.to_numpy(), kind="stable"):
        cutoff = cutoffs.iloc[index]
        while pointer < len(batches) and batches[pointer][0] < cutoff:
            changes = {}
            for match in batches[pointer][1].itertuples():
                h, a = team_key(match.home), team_key(match.away)
                expected = 1 / (1 + 10 ** ((ratings.get(a, 1500.) - ratings.get(h, 1500.) - home_advantage) / 400))
                score = float(match.home_goals > match.away_goals) + .5 * float(match.home_goals == match.away_goals)
                delta = k * (score - expected)
                changes[h] = changes.get(h, 0.) + delta
                changes[a] = changes.get(a, 0.) - delta
                games[h], games[a] = games.get(h, 0) + 1, games.get(a, 0) + 1
            for team, delta in changes.items():
                ratings[team] = ratings.get(team, 1500.) + delta
            pointer += 1
        query = queries.iloc[index]
        team, opponent = team_key(query.team), team_key(query.opp_team_name)
        own, other = ratings.get(team, 1500.), ratings.get(opponent, 1500.)
        difference = own - other
        output[index] = [own, other, difference,
            1 / (1 + 10 ** (-(difference + home.iloc[index] * home_advantage) / 400)),
            games.get(team, 0), games.get(opponent, 0)]
    queries[ELO_FEATURES] = output
    return queries
