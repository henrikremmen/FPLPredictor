"""M13: team strengths from odds for the whole horizon (challenger only).

Odds reach only the next one or two Gameweeks; later fixtures fall back to the
model without market data and look flatter (F22). Here each club gets an
attack and a defence rating plus a shared home advantage, fitted by weighted
Poisson likelihood with time decay to:

* odds-implied expected goals of past matches (football-data.co.uk pre-closing
  averages, de-vigged and fitted with ``external_context._implied_goal_model``),
* actual goals of those matches (half weight), and
* odds-implied expected goals of the upcoming fixtures in the lock rows
  (double weight, the freshest market view).

``fill_market`` then writes ``market_*`` features only where they are missing
and marks every row ``market_source = odds | implied``. Actual odds are never
overwritten. Production never uses this; ``ImpliedMarketModel`` is a
challenger that fills its own copy of the rows.

ponytail: one ridge-penalised Poisson fit (scipy), no Dixon-Coles low-score
correction or draw inflation; add those if implied draws look too low.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from external_context import _implied_goal_model, _poisson_outcomes, team_key

HALF_LIFE_DAYS = 90
RIDGE = 0.5
WEIGHTS = {"implied": 1.0, "goals": 0.5, "upcoming": 2.0}
MARKET_COLUMNS = ["market_team_win_probability", "market_opponent_win_probability", "market_draw_probability",
                  "market_over25_probability", "market_team_expected_goals", "market_opponent_expected_goals",
                  "market_clean_sheet_probability"]


def observations_from_results(frame: pd.DataFrame, before=None) -> pd.DataFrame:
    """football-data rows -> (home, away, home_rate, away_rate, kind, date), played before ``before``."""
    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame.Date, dayfirst=True, utc=True)
    if before is not None:
        frame = frame[frame.date < pd.Timestamp(before)]
    rows = []
    for match in frame.itertuples():
        home, away = team_key(match.HomeTeam), team_key(match.AwayTeam)
        prices = {"h": getattr(match, "AvgH", np.nan), "d": getattr(match, "AvgD", np.nan), "a": getattr(match, "AvgA", np.nan)}
        over, under = frame.at[match.Index, "Avg>2.5"] if "Avg>2.5" in frame else np.nan, \
            frame.at[match.Index, "Avg<2.5"] if "Avg<2.5" in frame else np.nan
        if all(np.isfinite(float(v)) and float(v) > 1 for v in prices.values()):
            raw = {k: 1 / float(v) for k, v in prices.items()}
            total = sum(raw.values())
            implied = {"market_home_win_probability": raw["h"] / total, "market_draw_probability": raw["d"] / total,
                       "market_away_win_probability": raw["a"] / total,
                       "market_over25_probability": (1 / over) / (1 / over + 1 / under)
                       if np.isfinite(over) and np.isfinite(under) else np.nan}
            goals = _implied_goal_model(implied)
            if np.isfinite(goals["market_home_expected_goals"]):
                rows.append({"home": home, "away": away, "home_rate": goals["market_home_expected_goals"],
                             "away_rate": goals["market_away_expected_goals"], "kind": "implied", "date": match.date})
        if np.isfinite(match.FTHG) and np.isfinite(match.FTAG):
            rows.append({"home": home, "away": away, "home_rate": float(match.FTHG), "away_rate": float(match.FTAG),
                         "kind": "goals", "date": match.date})
    return pd.DataFrame(rows, columns=["home", "away", "home_rate", "away_rate", "kind", "date"])


def observations_from_rows(rows: pd.DataFrame, at) -> pd.DataFrame:
    """Upcoming fixtures that already have odds in the lock rows, one observation per fixture."""
    known = rows[rows.market_team_expected_goals.notna()].drop_duplicates("fixture") if len(rows) else rows
    out = []
    for row in known.itertuples():
        team, opponent = team_key(row.team_name), team_key(row.opp_team_name)
        home, away = (team, opponent) if row.was_home == 1 else (opponent, team)
        team_rate, opp_rate = row.market_team_expected_goals, row.market_opponent_expected_goals
        out.append({"home": home, "away": away, "home_rate": team_rate if row.was_home == 1 else opp_rate,
                    "away_rate": opp_rate if row.was_home == 1 else team_rate, "kind": "upcoming", "date": pd.Timestamp(at)})
    return pd.DataFrame(out, columns=["home", "away", "home_rate", "away_rate", "kind", "date"])


def fit(observations: pd.DataFrame, at) -> dict:
    """Attack/defence per club, home advantage and base rate (log scale)."""
    teams = sorted(set(observations.home) | set(observations.away))
    index = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    age = (pd.Timestamp(at) - pd.to_datetime(observations.date, utc=True)).dt.total_seconds().clip(lower=0) / 86400
    weight = observations.kind.map(WEIGHTS).to_numpy(float) * 0.5 ** (age.to_numpy(float) / HALF_LIFE_DAYS)
    h, a = observations.home.map(index).to_numpy(), observations.away.map(index).to_numpy()
    y_home, y_away = observations.home_rate.to_numpy(float), observations.away_rate.to_numpy(float)

    def loss(x):
        mu, home_adv, attack, defence = x[0], x[1], x[2:2 + n], x[2 + n:]
        log_h = mu + home_adv + attack[h] - defence[a]
        log_a = mu + attack[a] - defence[h]
        lam_h, lam_a = np.exp(log_h), np.exp(log_a)
        value = np.sum(weight * (lam_h - y_home * log_h + lam_a - y_away * log_a)) + RIDGE * (attack @ attack + defence @ defence)
        r_h, r_a = weight * (lam_h - y_home), weight * (lam_a - y_away)
        grad = np.zeros_like(x)
        grad[0], grad[1] = r_h.sum() + r_a.sum(), r_h.sum()
        np.add.at(grad[2:2 + n], h, r_h)
        np.add.at(grad[2:2 + n], a, r_a)
        np.add.at(grad[2 + n:], a, -r_h)
        np.add.at(grad[2 + n:], h, -r_a)
        grad[2:] += 2 * RIDGE * x[2:]
        return value, grad

    start = np.zeros(2 + 2 * n)
    start[0] = np.log(max(np.average(np.r_[y_home, y_away], weights=np.r_[weight, weight]), 0.1))
    result = minimize(loss, start, jac=True, method="L-BFGS-B")
    x = result.x
    return {"mu": float(x[0]), "home": float(x[1]), "attack": dict(zip(teams, x[2:2 + n].tolist())),
            "defence": dict(zip(teams, x[2 + n:].tolist())), "observations": int(len(observations)), "fit_at": str(at)}


def rates(strengths: dict, home: str, away: str) -> tuple[float, float]:
    att, dfn = strengths["attack"], strengths["defence"]
    lam_h = np.exp(strengths["mu"] + strengths["home"] + att.get(home, 0.0) - dfn.get(away, 0.0))
    lam_a = np.exp(strengths["mu"] + att.get(away, 0.0) - dfn.get(home, 0.0))
    return float(lam_h), float(lam_a)


def fill_market(rows: pd.DataFrame, strengths: dict) -> pd.DataFrame:
    """Copy of ``rows`` with missing market features implied; real odds untouched."""
    result = rows.copy()
    missing = result.market_team_expected_goals.isna() & result.get("planned_fixture", True)
    result["market_source"] = np.where(result.market_team_expected_goals.notna(), "odds", None)
    for i in result.index[missing]:
        team, opponent = team_key(result.at[i, "team_name"]), team_key(result.at[i, "opp_team_name"])
        home = result.at[i, "was_home"] == 1
        lam_h, lam_a = rates(strengths, team, opponent) if home else rates(strengths, opponent, team)
        outcome = _poisson_outcomes(lam_h, lam_a)
        mine, theirs = (lam_h, lam_a) if home else (lam_a, lam_h)
        values = {"market_team_win_probability": outcome["home" if home else "away"],
                  "market_opponent_win_probability": outcome["away" if home else "home"],
                  "market_draw_probability": outcome["draw"], "market_over25_probability": outcome["over25"],
                  "market_team_expected_goals": mine, "market_opponent_expected_goals": theirs,
                  "market_clean_sheet_probability": float(np.exp(-theirs))}
        for column, value in values.items():
            result.at[i, column] = value
        result.at[i, "market_source"] = "implied"
    return result


class ImpliedMarketModel:
    """M13 challenger: the base model scored on rows whose missing odds are implied from team strengths.

    Strengths are refitted at every prediction from the stored past observations
    plus the odds already present in the rows, so a later lock uses fresher odds.
    """

    def __init__(self, base, past: pd.DataFrame):
        # ponytail: past results are frozen at registration; re-register to add newer rounds.
        self.base, self.past = base, past

    def _filled(self, rows):
        at = pd.Timestamp(getattr(self, "at", None) or pd.Timestamp.now(tz="UTC"))
        upcoming = observations_from_rows(rows, at)
        strengths = fit(pd.concat([self.past, upcoming], ignore_index=True), at)
        return fill_market(rows, strengths)

    def predict(self, rows):
        return self.base.predict(self._filled(rows))

    def probabilities(self, rows):
        method = getattr(self.base, "probabilities", None)
        return method(self._filled(rows)) if callable(method) else None

    def quantiles(self, rows):
        method = getattr(self.base, "quantiles", None)
        return method(self._filled(rows)) if callable(method) else None


def load_results(path: Path) -> pd.DataFrame:
    return observations_from_results(pd.read_csv(path))


def retrospective(root: Path, results_file: Path, captures: list[str], season: str = "2026-27") -> pd.DataFrame:
    """Weekly MAE with and without implied market features for Gameweeks a capture forecast without odds.

    Only matches played before the capture feed the strengths; the base is the
    capture's own production model; outcomes come from fpl-data.
    """
    import json
    import joblib
    from capture_fpl import score_rows
    root = Path(root)
    results = pd.read_csv(results_file)
    out = []
    for name in captures:
        folder = root / "data/raw/live_fpl" / name
        manifest = json.loads((folder / "manifest.json").read_text())
        at = pd.Timestamp(manifest["forecast_at"])
        model = joblib.load(manifest["model_path"])["model"]
        rows = pd.read_csv(folder / "horizon_fixture_forecast.csv", low_memory=False)
        rows = rows.drop(columns=[c for c in rows if c == "prediction" or c.startswith(("p_", "prediction_q"))])
        strengths = fit(pd.concat([observations_from_results(results, before=at), observations_from_rows(rows, at)],
                                  ignore_index=True), at)
        filled = fill_market(rows, strengths)
        for gw in sorted(filled.loc[filled.market_source.eq("implied"), "GW"].unique()):
            outcome = root / "fpl-data/data" / season / "gws" / f"gw{gw}.csv"
            if not outcome.exists():
                continue
            actual = pd.read_csv(outcome).groupby("element").total_points.sum()
            frame = {}
            for label, data in (("no_market", rows), ("implied", filled)):
                subset = data[data.GW.eq(gw)]
                frame[label] = score_rows(model, subset).groupby("player_id").prediction.sum()
            weekly = pd.DataFrame(frame)
            weekly["actual"] = weekly.index.map(actual).fillna(0.0)
            top = weekly.no_market.nlargest(100).index
            for cohort, part in (("all", weekly), ("top100", weekly.loc[top])):
                out.append({"capture": name, "GW": int(gw), "gw_ahead": int(gw) - int(manifest["target_event"]["id"]),
                            "cohort": cohort, "players": len(part),
                            "mae_no_market": float((part.no_market - part.actual).abs().mean()),
                            "mae_implied": float((part.implied - part.actual).abs().mean()),
                            "bias_no_market": float((part.no_market - part.actual).mean()),
                            "bias_implied": float((part.implied - part.actual).mean())})
    return pd.DataFrame(out)
