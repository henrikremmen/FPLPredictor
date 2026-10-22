"""Automatic prospective loop (plan M4): lock before the deadline, evaluate after
FPL checks the round, keep a leaderboard.

Before each deadline the production model (``incumbent``), every registered
challenger (``artifacts/challengers``) and FPL's own ``ep_next`` predict the same
player/fixture rows from the latest pre-deadline capture. The bundle and each
model's legal squad are frozen with ``prospective_lock`` / ``freeze_decisions``.
When FPL marks the round ``finished`` and ``data_checked``, every unevaluated
round is scored against a later capture and the leaderboard is rebuilt.

Nothing here changes the production model. The leaderboard only reports whether
a challenger meets the pre-registered criterion
(docs/prospective_criterion_2026-10-22.md). Locked bundles are never modified;
results go to ``artifacts/prospective_eval/``.

    python src/prospective_loop.py auto             # idempotent; run hourly
    python src/prospective_loop.py lock --event 8
    python src/prospective_loop.py evaluate
    python src/prospective_loop.py leaderboard
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

import freeze_decisions
from challengers import CHALLENGERS, registered
from fpl_collect import API, USER_AGENT
from prospective_decisions import evaluate_decisions
from prospective_evaluation import evaluate as evaluate_forecasts
from prospective_lock import digest, freeze_forecasts, utc, verify_lock

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = "incumbent"
LOCK_WINDOW_HOURS = 30
CRITERION = {
    "version": 1, "registered": "2026-10-22", "document": "docs/prospective_criterion_2026-10-22.md",
    "protocol": "loop-v1", "min_rounds": 8, "primary": "locked_team_points", "confidence": 0.95,
    "resamples": 10_000, "seed": 20261022, "guard": "mean weekly-points MAE difference <= 0",
}
# Rounds locked by hand before the loop existed: evaluated and shown, never counted.
LEGACY_ROUNDS = {
    "gw7_manual_20261010": {
        "protocol": "manual-2026-10-10",
        "forecasts": ["gw7_sources_20261010", "gw7_components_20261010", "gw7_injury_20261010"],
        "decisions": "gw7_decisions_with_injury_20261010",
    },
}


def _gz(path: Path):
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


def captures(root: Path) -> list[tuple[Path, dict]]:
    found = []
    for path in sorted((Path(root) / "data/raw/live_fpl").glob("capture_*/manifest.json")):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") == "complete" and (path.parent / "bootstrap.json.gz").exists():
            found.append((path.parent, manifest))
    return found


def _deadline(snapshot: Path, event: int) -> str:
    bootstrap = _gz(snapshot / "bootstrap.json.gz")
    return next(e["deadline_time"] for e in bootstrap["events"] if int(e["id"]) == event)


def forecast_capture(root: Path, event: int) -> tuple[Path, dict] | None:
    """Latest capture with frozen forecasts for ``event`` made before its deadline."""
    usable = [(snapshot, manifest) for snapshot, manifest in captures(root)
              if manifest.get("forecast_status") == "experimental_frozen"
              and event in manifest.get("forecast_horizons", [])
              and utc(manifest["forecast_at"]) < utc(_deadline(snapshot, event))]
    return max(usable, key=lambda pair: utc(pair[1]["forecast_at"]), default=None)


def outcome_capture(root: Path, gameweek: int, deadline: str) -> Path | None:
    """Latest capture taken after the deadline in which FPL has checked the round."""
    final = []
    for snapshot, manifest in captures(root):
        record = manifest.get("files", {}).get("bootstrap", {})
        if record.get("status") != 200 or utc(record["received_at"]) <= utc(deadline):
            continue
        event = next((e for e in _gz(snapshot / "bootstrap.json.gz")["events"] if int(e["id"]) == gameweek), {})
        if event.get("finished") and event.get("data_checked"):
            final.append((utc(record["received_at"]), snapshot))
    return max(final)[1] if final else None


def _benchmark_artifact(root: Path) -> Path:
    path = Path(root) / CHALLENGERS / "fpl_ep_next" / "benchmark.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": "fpl_ep_next", "production_eligible": False,
            "description": "FPL's ep_next from the pinned bootstrap, split evenly over the player's fixtures."}, indent=2))
    return path


CUP_MAX_AGE_HOURS = 24  # a cup download older than this is refreshed (current season only) at lock


def _needs(root: Path) -> set[str]:
    specs = [json.loads(path.read_text()) for path in (Path(root) / CHALLENGERS).glob("*/challenger.json")]
    return {need for spec in specs if spec.get("active", True) for need in spec.get("needs", [])}


def _attach_cup_minutes(root: Path, snapshot: Path, features: pd.DataFrame):
    """M8 inputs: recent cup/European minutes per row, with the source files as evidence."""
    import cup_minutes
    season = str(features.season.iloc[0])
    folder = cup_minutes.latest_download(root)
    manifest = json.loads((folder / "manifest.json").read_text()) if folder else None
    if manifest is None or (utc(datetime.now(timezone.utc)) - utc(manifest["finished_at"])).total_seconds() > CUP_MAX_AGE_HOURS * 3600:
        folder = cup_minutes.download(root, {season: cup_minutes.SEASONS[season]})
        manifest = json.loads((folder / "manifest.json").read_text())
    bootstrap = _gz(snapshot / "bootstrap.json.gz")
    codes = pd.DataFrame([{"season": season, "player_id": e["id"], "code": e["code"]} for e in bootstrap["elements"]])
    kickoffs = {f["id"]: f["kickoff_time"] for f in _gz(snapshot / "fixtures.json.gz")}
    attached = cup_minutes.attach_cup_minutes(features, cup_minutes.load_appearances(folder), codes,
                                              features.fixture.map(kickoffs))
    sources = [{"path": folder / name, "received_at": record["received_at"]}
               for name, record in manifest["files"].items() if name.startswith(season + "/")]
    return attached, sources


def lock(root: Path, event: int) -> Path:
    """Freeze incumbent, challengers and FPL ep_next on identical rows, plus each model's squad."""
    from capture_fpl import score_rows  # heavy import, only needed when locking
    root = Path(root)
    if any((root / "artifacts/prospective").glob(f"loop_gw{event}_*/manifest.json")):
        raise ValueError(f"GW{event} is already locked; one bundle per round keeps the leaderboard honest")
    found = forecast_capture(root, event)
    if found is None:
        raise ValueError(f"No capture with frozen GW{event} forecasts before the deadline")
    snapshot, manifest = found
    model_path = Path(manifest["model_path"])
    if digest(model_path) != manifest["model_sha256"]:
        raise ValueError("Production model changed since the capture's forecasts")
    sources = []
    for record in manifest["files"].values():
        if record.get("status") != 200 or not record.get("file"):
            continue
        source = snapshot / record["file"]
        if digest(source) != record["stored_sha256"]:
            raise ValueError(f"Changed snapshot source: {source.name}")
        sources.append({"path": source, "received_at": record["received_at"]})
    features_path = snapshot / "horizon_fixture_forecast.csv"
    features = pd.read_csv(features_path, low_memory=False)
    features = features[features.GW.eq(event)].reset_index(drop=True)
    if features.empty or features.fixture.isna().any():
        raise ValueError(f"GW{event}: no rows, or blank fixtures without an identity convention")
    sources.append({"path": features_path, "received_at": manifest["forecast_at"]})
    # The capture already scored these rows with production; drop its outputs so a
    # model without probabilities or quantiles cannot inherit them.
    features = features.drop(columns=[c for c in features if c == "prediction" or c.startswith(("p_", "prediction_q"))])

    if "cup_minutes" in _needs(root):
        features, cup_sources = _attach_cup_minutes(root, snapshot, features)
        sources += cup_sources

    keys = ["season", "GW", "player_id", "fixture"]
    models = {REFERENCE: model_path, **registered(root), "fpl_ep_next": _benchmark_artifact(root)}
    frames = []
    for name, path in models.items():
        if name == "fpl_ep_next":
            continue
        scored = score_rows(joblib.load(path)["model"], features)
        frames.append(scored[keys + [c for c in scored if c == "prediction" or c.startswith(("p_", "prediction_q"))]]
                      .assign(model=name))
    bootstrap = _gz(snapshot / "bootstrap.json.gz")
    ep_next = {int(e["id"]): float(e.get("ep_next") or 0) for e in bootstrap["elements"]}
    fixtures = features.groupby("player_id").fixture.transform("count")
    frames.append(features[keys].assign(model="fpl_ep_next", prediction=features.player_id.map(ep_next).fillna(0) / fixtures))
    predictions = pd.concat(frames, ignore_index=True)
    predictions["feature_snapshot_at"] = manifest["forecast_at"]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root / "artifacts/prospective" / f"loop_gw{event}_{stamp}"
    freeze_forecasts(predictions, deadline=_deadline(snapshot, event), sources=sources,
                     models=models, destination=destination)
    verify_lock(destination)
    freeze_decisions.run([destination], destination.with_name(destination.name + "_decisions"))
    return destination


def rounds(root: Path) -> dict[str, dict]:
    """Every round to evaluate: legacy hand-locked rounds and loop bundles."""
    prospective = Path(root) / "artifacts/prospective"
    found = {name: spec for name, spec in LEGACY_ROUNDS.items()
             if all((prospective / bundle).exists() for bundle in [*spec["forecasts"], spec["decisions"]])}
    for bundle in sorted(prospective.glob("loop_gw*")):
        if bundle.name.endswith("_decisions") or not (bundle / "manifest.json").exists():
            continue
        found[bundle.name] = {"protocol": CRITERION["protocol"], "forecasts": [bundle.name],
                              "decisions": bundle.name + "_decisions"}
    return found


def evaluate(root: Path) -> dict[str, str]:
    """Score every round FPL has checked; returns round -> evaluated/pending/done."""
    root = Path(root)
    prospective, results = root / "artifacts/prospective", root / "artifacts/prospective_eval"
    status = {}
    for name, spec in rounds(root).items():
        output = results / name
        parts = [(output / "forecasts" / bundle, prospective / bundle) for bundle in spec["forecasts"]]
        decisions = (output / "decisions", prospective / spec["decisions"])
        if all((path / "report.json").exists() for path, _ in [*parts, decisions]):
            status[name] = "done"
            continue
        lock_manifest = verify_lock(prospective / spec["forecasts"][0])
        snapshot = outcome_capture(root, int(lock_manifest["GW"]), lock_manifest["deadline"])
        if snapshot is None:
            status[name] = "pending"
            continue
        for destination, bundle in parts:
            if not (destination / "report.json").exists():
                evaluate_forecasts(bundle, snapshot, destination)
        if not (decisions[0] / "report.json").exists():
            evaluate_decisions(decisions[1], snapshot, decisions[0])
        (output / "round.json").write_text(json.dumps({
            "round": name, "protocol": spec["protocol"], "GW": int(lock_manifest["GW"]),
            "deadline": lock_manifest["deadline"], "outcome_snapshot": str(snapshot)}, indent=2))
        status[name] = "evaluated"
    return status


def round_table(root: Path) -> pd.DataFrame:
    """One row per evaluated round and model."""
    rows = []
    for meta_path in sorted((Path(root) / "artifacts/prospective_eval").glob("*/round.json")):
        meta = json.loads(meta_path.read_text())
        found = {}
        for report_path in sorted((meta_path.parent / "forecasts").glob("*/report.json")):
            for metric in json.loads(report_path.read_text())["metrics"]:
                found.setdefault(metric["model"], {
                    "fixture_MAE": metric["fixture_points"]["MAE"], "fixture_RMSE": metric["fixture_points"]["RMSE"],
                    "weekly_MAE": metric["weekly_points"]["MAE"], "weekly_RMSE": metric["weekly_points"]["RMSE"],
                    "brier_60plus": metric.get("minutes", {}).get("brier_60plus"),
                })
        for metric in json.loads((meta_path.parent / "decisions" / "report.json").read_text())["metrics"]:
            if metric["model"] in found:
                found[metric["model"]].update(team_points=metric["actual_points"],
                                              captain_points=metric["captain_points_before_doubling"])
        rows += [{"round": meta["round"], "protocol": meta["protocol"], "GW": meta["GW"], "model": model, **values}
                 for model, values in found.items()]
    return pd.DataFrame(rows)


def _interval(differences: np.ndarray) -> tuple[float | None, float | None]:
    if len(differences) < 2:
        return None, None
    rng = np.random.default_rng(CRITERION["seed"])
    means = rng.choice(differences, (CRITERION["resamples"], len(differences)), replace=True).mean(axis=1)
    tail = (1 - CRITERION["confidence"]) / 2 * 100
    return float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail))


def summarize(table: pd.DataFrame) -> list[dict]:
    """Per model: totals over all rounds; criterion statistics over loop-v1 rounds only."""
    if table.empty:
        return []
    reference = table[table.model.eq(REFERENCE)].set_index("round")
    summary = []
    for model, frame in table.groupby("model"):
        counted = frame[frame.protocol.eq(CRITERION["protocol"])].set_index("round")
        common = counted.index.intersection(reference.index)
        points = (counted.loc[common, "team_points"] - reference.loc[common, "team_points"]).dropna().to_numpy(float)
        mae = (counted.loc[common, "weekly_MAE"] - reference.loc[common, "weekly_MAE"]).dropna().to_numpy(float)
        low, high = _interval(points)
        row = {
            "model": model, "rounds_shown": int(len(frame)), "rounds_counted": int(len(points)),
            "team_points_total": float(frame.team_points.sum()), "weekly_MAE_mean": float(frame.weekly_MAE.mean()),
            "fixture_RMSE_mean": float(frame.fixture_RMSE.mean()),
            "team_points_diff_mean": float(points.mean()) if len(points) else None,
            "team_points_diff_ci": [low, high] if low is not None else None,
            "weekly_MAE_diff_mean": float(mae.mean()) if len(mae) else None,
        }
        row["criterion_met"] = bool(model != REFERENCE and len(points) >= CRITERION["min_rounds"]
                                    and low is not None and low > 0 and row["weekly_MAE_diff_mean"] <= 0)
        summary.append(row)
    return sorted(summary, key=lambda row: (row["model"] != REFERENCE, -row["team_points_total"]))


MIN_CALIBRATION_ROUNDS = 6  # plan M7: isotonic recalibration only after this many final rounds


def calibration_rows(root: Path, model: str = REFERENCE) -> pd.DataFrame:
    """Frozen playing-time probabilities and observed minutes from evaluated rounds."""
    frames = []
    for meta_path in sorted((Path(root) / "artifacts/prospective_eval").glob("*/round.json")):
        for scored in sorted((meta_path.parent / "forecasts").glob("*/scored_predictions.csv")):
            frame = pd.read_csv(scored)
            frame = frame[frame.model.eq(model)]
            if {"p_zero_minutes", "p_60plus_minutes"} <= set(frame) and len(frame):
                frames.append(frame.assign(round=meta_path.parent.name))
                break  # the reference appears in every bundle of a round; take it once
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fit_minutes_calibration(root: Path, model: str = REFERENCE) -> Path:
    """M7: isotonic maps for P(appearance) and P(60+). Research artifact only."""
    from sklearn.isotonic import IsotonicRegression
    rows = calibration_rows(root, model)
    rounds_available = rows["round"].nunique() if len(rows) else 0
    if rounds_available < MIN_CALIBRATION_ROUNDS:
        raise ValueError(f"M7 needs {MIN_CALIBRATION_ROUNDS} evaluated rounds; {rounds_available} available")
    maps = {
        "appearance": IsotonicRegression(out_of_bounds="clip").fit(1 - rows.p_zero_minutes, rows.minutes.gt(0)),
        "60plus": IsotonicRegression(out_of_bounds="clip").fit(rows.p_60plus_minutes, rows.minutes.ge(60)),
    }
    folder = Path(root) / CHALLENGERS / f"minutes_calibration_{datetime.now(timezone.utc):%Y%m%d}"
    folder.mkdir(parents=True, exist_ok=False)
    joblib.dump({"maps": maps, "model": model, "rounds": sorted(rows["round"].unique()),
                 "production_eligible": False}, folder / "calibration.joblib")
    return folder


def leaderboard(root: Path) -> dict:
    output = Path(root) / "artifacts/prospective_eval"
    output.mkdir(parents=True, exist_ok=True)
    table = round_table(root)
    table.to_csv(output / "leaderboard_rounds.csv", index=False)
    criterion_text = (Path(root) / CRITERION["document"])
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "criterion": CRITERION,
              "criterion_document_sha256": hashlib.sha256(criterion_text.read_bytes()).hexdigest()
              if criterion_text.exists() else None,
              "production_change": "never automatic; see criterion document", "models": summarize(table)}
    calibration = calibration_rows(root)
    result["minutes_calibration"] = {"rounds": int(calibration["round"].nunique()) if len(calibration) else 0,
                                     "needed": MIN_CALIBRATION_ROUNDS}
    (output / "leaderboard.json").write_text(json.dumps(result, indent=2))
    lines = ["| Model | Rounds (counted) | Team points | Δ team pts/round | 95% CI | Weekly MAE | Δ MAE | Criterion |",
             "|---|---:|---:|---:|---|---:|---:|---|"]
    fmt = lambda value: "–" if value is None else f"{value:+.2f}"
    for row in result["models"]:
        ci = "–" if row["team_points_diff_ci"] is None else f"{row['team_points_diff_ci'][0]:+.2f} … {row['team_points_diff_ci'][1]:+.2f}"
        lines.append(f"| {row['model']} | {row['rounds_shown']} ({row['rounds_counted']}) | {row['team_points_total']:.0f} | "
                     f"{fmt(row['team_points_diff_mean'])} | {ci} | {row['weekly_MAE_mean']:.3f} | "
                     f"{fmt(row['weekly_MAE_diff_mean'])} | {'met' if row['criterion_met'] else 'not met'} |")
    (output / "leaderboard.md").write_text(
        f"# Prospective leaderboard\n\nGenerated {result['generated_at']}. Criterion v{CRITERION['version']} "
        f"({CRITERION['document']}); only `{CRITERION['protocol']}` rounds count. "
        "The loop never changes the production model.\n\n" + "\n".join(lines) + "\n\n"
        f"Playing-time calibration (M7): {result['minutes_calibration']['rounds']} of "
        f"{MIN_CALIBRATION_ROUNDS} evaluated rounds needed.\n")
    return result


def auto(root: Path, now=None, run_capture=None) -> dict:
    """Hourly: lock the next round inside the window, refresh outcomes, evaluate, rebuild the leaderboard."""
    root = Path(root)
    now = utc(now or datetime.now(timezone.utc))
    if run_capture is None:
        from capture_fpl import run as run_capture
    response = requests.get(API + "bootstrap-static/", timeout=(10, 35), headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    events = response.json()["events"]
    result = {"locked": None, "captured": []}
    upcoming = next((e for e in events if e.get("is_next")), None)
    if upcoming:
        deadline, event = utc(upcoming["deadline_time"]), int(upcoming["id"])
        hours = (deadline - now).total_seconds() / 3600
        locked = any((Path(root) / "artifacts/prospective").glob(f"loop_gw{event}_*/manifest.json"))
        if 0 < hours <= LOCK_WINDOW_HOURS and not locked:
            found = forecast_capture(root, event)
            if found is None or (deadline - utc(found[1]["forecast_at"])).total_seconds() / 3600 > LOCK_WINDOW_HOURS:
                run_capture(root, "loop")
                result["captured"].append("loop")
            result["locked"] = str(lock(root, event))
    checked = {int(e["id"]) for e in events if e.get("finished") and e.get("data_checked")}
    for name, spec in rounds(root).items():
        manifest = json.loads((Path(root) / "artifacts/prospective" / spec["forecasts"][0] / "manifest.json").read_text())
        done = (Path(root) / "artifacts/prospective_eval" / name / "round.json").exists()
        if not done and int(manifest["GW"]) in checked and outcome_capture(root, int(manifest["GW"]), manifest["deadline"]) is None:
            run_capture(root, "outcomes")
            result["captured"].append("outcomes")
            break
    result["evaluation"] = evaluate(root)
    result["leaderboard"] = [(row["model"], row["rounds_shown"], row["criterion_met"]) for row in leaderboard(root)["models"]]
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["auto", "lock", "evaluate", "leaderboard"])
    parser.add_argument("--event", type=int)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.command == "lock":
        if args.event is None:
            parser.error("lock needs --event")
        result = {"locked": str(lock(args.root, args.event))}
    elif args.command == "evaluate":
        result = evaluate(args.root)
    elif args.command == "leaderboard":
        result = leaderboard(args.root)
    else:
        result = auto(args.root)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
