"""Challenger models for the prospective loop (plan M1, M2 and the FPL benchmark of M5).

Challengers live in ``artifacts/challengers/<name>/`` with ``production_eligible``
false. ``capture_fpl.select_model_path`` only considers
``artifacts/models/production_*``, so training a challenger can never change the
app's model; promotion is a manual decision under the pre-registered criterion
(docs/prospective_criterion_2026-10-22.md).

    python src/challengers.py refit --features data/processed/features_20261022
    python src/challengers.py season-transfer --features data/processed/features_20261022 --base refit_20261022
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests
from lightgbm import LGBMRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from cup_minutes import FEATURES as CUP_FEATURES, SOURCE, attach_cup_minutes, latest_download, load_appearances
from data_contract import map_codes
from historical_market import SOURCE_URL
from improved_models import enrich
from market_models import ALL_MARKET_FEATURES, _production_model, load_market_data, market_enrich
from model_experiments import FEATURE_SETS
from model_experiments import TARGET
from improved_models import EXTRA
from nextgen_models import SEASON_ORDER

ROOT = Path(__file__).resolve().parents[1]
CHALLENGERS = "artifacts/challengers"
CURRENT_SEASON, CURRENT_CODE = "2026-27", "2627"


def registered(root: Path) -> dict[str, Path]:
    """Challenger name -> model file, for every registered challenger."""
    found = {}
    for spec in sorted((Path(root) / CHALLENGERS).glob("*/challenger.json")):
        info = json.loads(spec.read_text())
        if info.get("production_eligible") is not False:
            raise ValueError(f"{spec}: challengers must declare production_eligible false")
        if info.get("active", True):
            found[info["name"]] = spec.parent / info["model_file"]
    return found


def register(root: Path, name: str, model_file: str, **info) -> Path:
    folder = Path(root) / CHALLENGERS / name
    spec = {"name": name, "model_file": model_file, "production_eligible": False, "active": True,
            "registered_at": datetime.now(timezone.utc).isoformat(), **info}
    (folder / "challenger.json").write_text(json.dumps(spec, indent=2))
    return folder


def current_season_odds(root: Path, day: str | None = None) -> Path:
    """This season's football-data.co.uk file, one dated copy per day (the file keeps growing)."""
    day = day or datetime.now(timezone.utc).strftime("%Y%m%d")
    path = Path(root) / "data/raw/historical_odds/football_data_uk/current" / f"E0_{CURRENT_CODE}_{day}.csv"
    if not path.exists():
        response = requests.get(SOURCE_URL.format(code=CURRENT_CODE), timeout=(10, 120),
                                headers={"User-Agent": "fplmodell-research/1.0"})
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    return path


def train_refit(root: Path, features_dir: Path, name: str | None = None) -> Path:
    """M1: the production recipe (market_hgb + fallback + minutes + quantiles), refitted
    with the data-checked rounds of the current season included."""
    root = Path(root)
    name = name or f"refit_{datetime.now(timezone.utc):%Y%m%d}"
    folder = root / CHALLENGERS / name
    folder.mkdir(parents=True, exist_ok=False)
    data = load_market_data(root, features_dir, seasons=[*SEASON_ORDER, CURRENT_SEASON],
                            extra_odds={CURRENT_SEASON: current_season_odds(root)})
    model = _production_model(data, "market_hgb", include_current=True)
    joblib.dump({"model": model, "model_family": "market_hgb+market_fallback+minutes_mixture_15+quantile_hgb",
                 "production_eligible": False}, folder / "model.joblib")
    current = data[data.season.eq(CURRENT_SEASON)]
    return register(root, name, "model.joblib", plan_item="M1",
        description="Production recipe refitted with the current season's data-checked rounds.",
        features_dir=str(Path(features_dir)), training_rows=int(len(data)),
        current_season_rows=int(len(current)), current_season_gameweeks=sorted(int(g) for g in current.GW.unique()),
        current_season_market_rows=int(current.market_team_expected_goals.notna().sum())
        if "market_team_expected_goals" in current else None)


PRIOR_COLUMNS = ["prior_pts90", "prior_min_share", "prior_xgi90", "prior_start_share", "prior_ppg"]
TRANSFER_ROUNDS = 10  # prior-season weight falls linearly from GW1 to zero after this round
POSITION_CODES = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}


def prior_season_table(season_dirs: dict[str, Path]) -> pd.DataFrame:
    """(season, player_id) -> previous-season rates, matched on FPL's stable ``code``.

    ``element`` ids change every season; an ambiguous code fails instead of guessing.
    """
    raw = {}
    for season, folder in season_dirs.items():
        frame = pd.read_csv(Path(folder) / "players_raw.csv", low_memory=False)
        for column in ["minutes", "total_points", "starts", "expected_goal_involvements", "points_per_game"]:
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        raw[season] = frame
    tables = []
    ordered = sorted(raw)
    for previous, season in zip(ordered, ordered[1:]):
        before, current = raw[previous], raw[season][["id", "code"]]
        map_codes(before[["id", "code"]], current)
        minutes = before.minutes
        prior = pd.DataFrame({
            "code": before.code,
            "prior_pts90": np.where(minutes >= 270, before.total_points / minutes * 90, np.nan),
            "prior_min_share": minutes / (38 * 90),
            "prior_xgi90": np.where(minutes >= 270, before.expected_goal_involvements / minutes * 90, np.nan),
            "prior_start_share": before.starts / 38,
            "prior_ppg": before.points_per_game,
        })
        tables.append(current.merge(prior, on="code", how="left", validate="one_to_one")
                      .rename(columns={"id": "player_id"}).assign(season=season))
    return pd.concat(tables, ignore_index=True)[["season", "player_id", *PRIOR_COLUMNS]]


def transfer_features(rows: pd.DataFrame, prior: pd.DataFrame, base: np.ndarray) -> pd.DataFrame:
    joined = rows[["season", "player_id"]].reset_index(drop=True).merge(
        prior, on=["season", "player_id"], how="left", validate="many_to_one")
    weight = np.clip(1 - (rows.GW.to_numpy(float) - 1) / TRANSFER_ROUNDS, 0, 1)
    features = pd.DataFrame({f"{column}_w": joined[column].to_numpy(float) * weight for column in PRIOR_COLUMNS})
    features["new_player_w"] = joined.prior_min_share.isna().to_numpy(float) * weight
    features["weight"] = weight
    features["base"] = base
    features["position"] = rows.position.map(POSITION_CODES).to_numpy(float)
    return features


class _Corrected:
    """Base model plus a learned correction; playing-time probabilities stay the base's."""

    def _features(self, rows, base):
        raise NotImplementedError

    def _parts(self, rows):
        base = np.asarray(self.base.predict(rows), float)
        return base, self.residual.predict(self._features(rows.reset_index(drop=True), base))

    def predict(self, rows):
        base, adjustment = self._parts(rows)
        return base + adjustment

    def probabilities(self, rows):
        return self.base.probabilities(rows)

    def quantiles(self, rows):
        quantiles = self.base.quantiles(rows)
        return None if quantiles is None else quantiles + self._parts(rows)[1][:, None]


class SeasonTransferModel(_Corrected):
    """M2: base model plus a small correction from last season, fading out by GW10."""

    def __init__(self, base, residual, prior: pd.DataFrame):
        self.base, self.residual, self.prior = base, residual, prior

    def _parts(self, rows):
        base, adjustment = super()._parts(rows)
        weight = np.clip(1 - (rows.GW.to_numpy(float) - 1) / TRANSFER_ROUNDS, 0, 1)
        return base, np.where(weight > 0, adjustment, 0.0)

    def _features(self, rows, base):
        return transfer_features(rows, self.prior, base)


def _residual_model():
    return HistGradientBoostingRegressor(max_depth=3, max_iter=200, learning_rate=0.05,
                                         l2_regularization=1.0, min_samples_leaf=100, random_state=0)


def _residual_fit(data: pd.DataFrame, featurize, select=lambda rows: rows):
    """Shared by M2, M5 and M8. Bases trained to 2024-25 and 2025-26 predict 2025-26 and
    this season out of sample; the correction learns actual minus base. The check fits
    on 2025-26 only and is applied to this season."""
    frames = {}
    for target, last_training in [("2025-26", "2024-25"), (CURRENT_SEASON, "2025-26")]:
        rows = select(data[data.season.eq(target)].sort_values(["kickoff_time", "player_id"]).reset_index(drop=True))
        base = np.asarray(_production_model(data[data.season.le(last_training)], "market_hgb").predict(rows), float)
        actual = rows[TARGET].to_numpy(float)
        frames[target] = (featurize(rows, base), actual - base, actual, base)
    x_train, y_train, _, _ = frames["2025-26"]
    x_test, _, actual, base_prediction = frames[CURRENT_SEASON]
    adjusted = base_prediction + _residual_model().fit(x_train, y_train).predict(x_test)
    check = {"rows": int(len(actual)), "base_MAE": float(np.abs(actual - base_prediction).mean()),
             "adjusted_MAE": float(np.abs(actual - adjusted).mean()),
             "base_RMSE": float(np.sqrt(((actual - base_prediction) ** 2).mean())),
             "adjusted_RMSE": float(np.sqrt(((actual - adjusted) ** 2).mean()))}
    residual = _residual_model().fit(pd.concat([frames[t][0] for t in frames], ignore_index=True),
                                     np.concatenate([frames[t][1] for t in frames]))
    return residual, {"retrospective_check": check, "residual_training_rows": int(sum(len(f[1]) for f in frames.values()))}


def _save(root: Path, name: str, model, family: str, **info) -> Path:
    folder = Path(root) / CHALLENGERS / name
    folder.mkdir(parents=True, exist_ok=False)
    joblib.dump({"model": model, "model_family": family, "production_eligible": False}, folder / "model.joblib")
    return register(root, name, "model.joblib", **info)


def _training_data(root: Path, features_dir: Path) -> pd.DataFrame:
    return load_market_data(root, features_dir, seasons=[*SEASON_ORDER, CURRENT_SEASON],
                            extra_odds={CURRENT_SEASON: current_season_odds(root)})


def _base(root: Path, base_challenger: str):
    return joblib.load(registered(root)[base_challenger])["model"]


def train_season_transfer(root: Path, features_dir: Path, base_challenger: str, name: str | None = None) -> Path:
    """M2: previous-season correction for early rounds (GW <= TRANSFER_ROUNDS)."""
    import challengers  # pickle classes by module path, also when run as a script
    root = Path(root)
    vaastav, own = root / "data-source/data", root / "fpl-data/data"
    season_dirs = {season: vaastav / season for season in ["2019-20", *SEASON_ORDER]}
    season_dirs[CURRENT_SEASON] = own / CURRENT_SEASON
    prior = prior_season_table(season_dirs)
    residual, info = _residual_fit(_training_data(root, features_dir), lambda rows, base: transfer_features(rows, prior, base),
                                   select=lambda rows: rows[rows.GW.le(TRANSFER_ROUNDS)])
    current = prior[prior.season.eq(CURRENT_SEASON)].reset_index(drop=True)
    return _save(root, name or f"season_transfer_{datetime.now(timezone.utc):%Y%m%d}",
        challengers.SeasonTransferModel(_base(root, base_challenger), residual, current),
        f"{base_challenger}+season_transfer_residual", plan_item="M2", base_challenger=base_challenger,
        description=f"{base_challenger} plus a previous-season correction (matched on code) that fades out after GW{TRANSFER_ROUNDS}.",
        prior_coverage_current=float(current.prior_min_share.notna().mean()), **info)


def crowd_features(rows: pd.DataFrame, base: np.ndarray) -> pd.DataFrame:
    """M5: FPL managers' collective signal, ranked within each round so the
    historical columns (transfers_balance, selected, value) and the live deadline
    fields (transfers_in/out_event, selected_by_percent, cost_change_start) share a scale."""
    if "transfers_balance" in rows:
        net, owned = rows.transfers_balance, rows.selected
        rise = rows.value - rows.groupby(["season", "player_id"]).value.transform("first")
    else:
        net = rows.transfers_in_event - rows.transfers_out_event
        owned, rise = rows.selected_by_percent, rows.cost_change_start
    group = [rows.season, rows.GW]
    rank = lambda values: pd.to_numeric(values, errors="coerce").groupby(group).rank(pct=True)
    return pd.DataFrame({"net_transfers_rank": rank(net).to_numpy(), "ownership_rank": rank(owned).to_numpy(),
                         "price_rise": pd.to_numeric(rise, errors="coerce").to_numpy(float), "base": base,
                         "position": rows.position.map(POSITION_CODES).to_numpy(float)})


class CrowdSignalModel(_Corrected):
    """M5: base model plus a correction from transfers, ownership and price moves."""

    def __init__(self, base, residual):
        self.base, self.residual = base, residual

    def _features(self, rows, base):
        return crowd_features(rows, base)


def train_crowd(root: Path, features_dir: Path, base_challenger: str, name: str | None = None) -> Path:
    import challengers  # pickle classes by module path, also when run as a script
    root = Path(root)
    data = _training_data(root, features_dir)
    crowd = pd.read_csv(Path(features_dir) / "player_fixture_features.csv", low_memory=False,
                        usecols=["season", "GW", "fixture", "player_id", "transfers_balance", "selected", "value"])
    data = data.merge(crowd, on=["season", "GW", "fixture", "player_id"], how="left", validate="one_to_one")
    residual, info = _residual_fit(data, crowd_features)
    return _save(root, name or f"crowd_{datetime.now(timezone.utc):%Y%m%d}",
        challengers.CrowdSignalModel(_base(root, base_challenger), residual), f"{base_challenger}+crowd_residual",
        plan_item="M5", base_challenger=base_challenger,
        description=f"{base_challenger} plus a correction from net transfers, ownership and price rises (ranked within round).",
        caveat="Live transfers are counted up to the lock, not the full window; history rows cover the whole window.", **info)


def player_codes(root: Path) -> pd.DataFrame:
    """(season, player_id, code) for the seasons with cup data, from players_raw."""
    root = Path(root)
    folders = {"2025-26": root / "data-source/data/2025-26", CURRENT_SEASON: root / "fpl-data/data" / CURRENT_SEASON}
    frames = [pd.read_csv(folder / "players_raw.csv", usecols=["id", "code"]).rename(columns={"id": "player_id"})
              .assign(season=season) for season, folder in folders.items()]
    return pd.concat(frames, ignore_index=True)


def cup_features(rows: pd.DataFrame, base: np.ndarray) -> pd.DataFrame:
    """M8: minutes outside the league before kickoff (unknown when the player has no code)."""
    frame = pd.DataFrame({column: pd.to_numeric(rows.get(column), errors="coerce") for column in CUP_FEATURES})
    frame["base"], frame["position"] = base, rows.position.map(POSITION_CODES).to_numpy(float)
    return frame


class CupMinutesModel(_Corrected):
    """M8: base model plus a correction from recent cup and European minutes.
    Rows without the cup columns (no fresh source at lock) keep the base prediction."""

    def __init__(self, base, residual):
        self.base, self.residual = base, residual

    def _features(self, rows, base):
        return cup_features(rows, base)

    def _parts(self, rows):
        if not set(CUP_FEATURES) <= set(rows):
            base = np.asarray(self.base.predict(rows), float)
            return base, np.zeros(len(rows))
        return super()._parts(rows)


def train_cup(root: Path, features_dir: Path, base_challenger: str, name: str | None = None) -> Path:
    import challengers  # pickle classes by module path, also when run as a script
    root = Path(root)
    folder = latest_download(root)
    if folder is None:
        raise FileNotFoundError("Run python src/cup_minutes.py download first")
    appearances, codes = load_appearances(folder), player_codes(root)
    data = _training_data(root, features_dir)
    residual, info = _residual_fit(data, cup_features,
        select=lambda rows: attach_cup_minutes(rows, appearances, codes, rows.kickoff_time))
    return _save(root, name or f"cup_minutes_{datetime.now(timezone.utc):%Y%m%d}",
        challengers.CupMinutesModel(_base(root, base_challenger), residual), f"{base_challenger}+cup_minutes_residual",
        plan_item="M8", base_challenger=base_challenger, needs=["cup_minutes"], cup_source=SOURCE,
        cup_download=str(folder), description=f"{base_challenger} plus a correction from minutes in cups and Europe "
        "in the 7 and 14 days before kickoff (FPL-Core-Insights, research only).", **info)


OPENFPL_FEATURES = [c for c in FEATURE_SETS["context"] if c != "position"] + EXTRA + ALL_MARKET_FEATURES


def _openfpl_matrix(rows: pd.DataFrame) -> pd.DataFrame:
    frame = enrich(market_enrich(rows.copy()))
    frame["was_home"] = frame.was_home.astype(str).str.lower().map({"true": 1., "false": 0., "1": 1., "0": 0., "1.0": 1., "0.0": 0.})
    return frame[OPENFPL_FEATURES].apply(pd.to_numeric, errors="coerce")


class PositionEnsemble:
    """M6: OpenFPL-style architecture (arXiv 2508.09992) with installed libraries:
    one random forest and one gradient-boosting model per position, averaged.
    LightGBM stands in for XGBoost; the features are this project's, not OpenFPL's."""

    def __init__(self, models: dict):
        self.models = models

    def predict(self, rows):
        matrix, prediction = _openfpl_matrix(rows), np.zeros(len(rows))
        positions = rows.position.to_numpy()
        for position, (forest, boosted) in self.models.items():
            mask = positions == position
            if mask.any():
                prediction[mask] = (forest.predict(matrix[mask]) + boosted.predict(matrix[mask])) / 2
        return prediction


def train_openfpl_style(root: Path, features_dir: Path, name: str | None = None) -> Path:
    root = Path(root)
    name = name or f"openfpl_style_{datetime.now(timezone.utc):%Y%m%d}"
    data = load_market_data(root, features_dir, seasons=[*SEASON_ORDER, CURRENT_SEASON],
                            extra_odds={CURRENT_SEASON: current_season_odds(root)})
    def fit(rows):
        matrix, models = _openfpl_matrix(rows), {}
        for position in POSITION_CODES:
            mask = rows.position.eq(position).to_numpy()
            target = rows.loc[mask, TARGET].to_numpy(float)
            forest = RandomForestRegressor(n_estimators=200, max_depth=12, min_samples_leaf=20, max_features=0.5,
                                           n_jobs=-1, random_state=0).fit(matrix[mask], target)
            boosted = LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=50,
                                    subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=0,
                                    verbose=-1).fit(matrix[mask], target)
            models[position] = (forest, boosted)
        return PositionEnsemble(models)

    # Retrospective check against the production recipe, both trained to 2025-26.
    past, current = data[data.season.ne(CURRENT_SEASON)], data[data.season.eq(CURRENT_SEASON)]
    actual = current[TARGET].to_numpy(float)
    base_prediction = np.asarray(_production_model(past, "market_hgb").predict(current), float)
    ensemble_prediction = fit(past).predict(current)
    check = {"rows": int(len(actual)), "production_recipe_MAE": float(np.abs(actual - base_prediction).mean()),
             "ensemble_MAE": float(np.abs(actual - ensemble_prediction).mean()),
             "production_recipe_RMSE": float(np.sqrt(((actual - base_prediction) ** 2).mean())),
             "ensemble_RMSE": float(np.sqrt(((actual - ensemble_prediction) ** 2).mean()))}
    models = fit(data).models
    import challengers  # pickle the class by module path, also when run as a script
    folder = root / CHALLENGERS / name
    folder.mkdir(parents=True, exist_ok=False)
    joblib.dump({"model": challengers.PositionEnsemble(models), "model_family": "position_rf_lgbm_ensemble",
                 "production_eligible": False}, folder / "model.joblib")
    return register(root, name, "model.joblib", plan_item="M6", training_rows=int(len(data)),
        description="OpenFPL-style position-specific random forest + gradient boosting ensemble on this project's features.",
        caveat="Not OpenFPL's own code or features: that needs xgboost (not installed) and their Understat pipeline.",
        retrospective_check=check)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    refit = sub.add_parser("refit", help="M1 refit challenger")
    refit.add_argument("--features", type=Path, required=True)
    refit.add_argument("--name")
    transfer = sub.add_parser("season-transfer", help="M2 challenger on top of a registered base")
    transfer.add_argument("--features", type=Path, required=True)
    transfer.add_argument("--base", required=True, help="registered challenger name, e.g. refit_20261022")
    transfer.add_argument("--name")
    crowd = sub.add_parser("crowd", help="M5 challenger on top of a registered base")
    crowd.add_argument("--features", type=Path, required=True)
    crowd.add_argument("--base", required=True)
    crowd.add_argument("--name")
    cup = sub.add_parser("cup-minutes", help="M8 challenger on top of a registered base")
    cup.add_argument("--features", type=Path, required=True)
    cup.add_argument("--base", required=True)
    cup.add_argument("--name")
    openfpl = sub.add_parser("openfpl-style", help="M6 position-specific ensemble")
    openfpl.add_argument("--features", type=Path, required=True)
    openfpl.add_argument("--name")
    args = parser.parse_args(argv)
    if args.command == "cup-minutes":
        print(train_cup(ROOT, args.features, args.base, args.name))
        return 0
    if args.command == "openfpl-style":
        print(train_openfpl_style(ROOT, args.features, args.name))
        return 0
    if args.command == "refit":
        print(train_refit(ROOT, args.features, args.name))
    elif args.command == "crowd":
        print(train_crowd(ROOT, args.features, args.base, args.name))
    else:
        print(train_season_transfer(ROOT, args.features, args.base, args.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
