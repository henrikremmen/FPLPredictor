"""Freeze static legal GW squads/captains before observing prospective results."""
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil

import pandas as pd

from decision_backtest import optimize_squad
from prospective_lock import digest, utc, verify_lock


def run(bundles, destination):
    bundles, destination = [Path(path) for path in bundles], Path(destination)
    manifests = [verify_lock(path) for path in bundles]
    identity = {(m["season"], m["GW"], m["deadline"]) for m in manifests}
    if len(identity) != 1:
        raise ValueError("Decision bundles refer to different rounds")
    season, gw, deadline = next(iter(identity))
    if utc(datetime.now(timezone.utc)) >= utc(deadline):
        raise ValueError("Cannot select a prospective squad after deadline")
    reference = bundles[0]
    bootstrap_candidates = []
    for entry in manifests[0]["files"]:
        if entry["kind"] != "source":
            continue
        try:
            with gzip.open(reference / entry["file"], "rt") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and {"elements", "teams", "events"}.issubset(payload):
            bootstrap_candidates.append((entry, payload))
    if not bootstrap_candidates:
        raise ValueError("No pinned bootstrap source")
    entry, bootstrap = min(bootstrap_candidates, key=lambda pair: utc(pair[0]["received_at"]))
    market = pd.DataFrame([{"player_id": p["id"], "name": p["web_name"], "team": p["team"],
        "position": {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}[p["element_type"]],
        "value": p["now_cost"]} for p in bootstrap["elements"]
        if p["element_type"] in [1, 2, 3, 4] and p.get("can_select", True)])
    candidates = {}
    for bundle in bundles:
        frame = pd.read_csv(bundle / "predictions.csv")
        for model, rows in frame.groupby("model"):
            weekly = rows.groupby("player_id").prediction.sum().sort_index()
            if model in candidates and not candidates[model].equals(weekly):
                raise ValueError("Inconsistent duplicate reference forecast")
            candidates[model] = weekly
    choices, summary = [], []
    for model, values in sorted(candidates.items()):
        data = market.merge(values.rename("prediction"), on="player_id", validate="one_to_one")
        if len(data) != len(market):
            raise ValueError("Missing forecast for selectable player")
        chosen = optimize_squad(data)
        squad = chosen["squad"].copy()
        squad["starter"] = squad.player_id.isin(chosen["starters"].player_id)
        squad["captain"] = squad.player_id.eq(int(chosen["captain"].player_id))
        squad["model"], squad["season"], squad["GW"] = model, season, gw
        choices.append(squad)
        summary.append({"model": model, "predicted_points": chosen["objective"],
            "squad_cost": int(squad.value.sum()), "captain_id": int(chosen["captain"].player_id)})
    destination.mkdir(parents=True, exist_ok=False)
    pd.concat(choices).to_csv(destination / "selections.csv", index=False)
    shutil.copyfile(reference / entry["file"], destination / "bootstrap.json.gz")
    files = ["selections.csv", "bootstrap.json.gz"]
    for index, bundle in enumerate(bundles):
        name = f"forecast_{index}.csv"
        shutil.copyfile(bundle / "predictions.csv", destination / name)
        files.append(name)
    completed = utc(datetime.now(timezone.utc))
    manifest = {"status": "locked" if completed < utc(deadline) else "missed_deadline",
        "completed_at": str(completed), "deadline": deadline, "season": season, "GW": gw,
        "scope": "static 100m squad, XI and captain; no transfers, chips, vice-captain or autosubs",
        "price_observed_at": entry["received_at"], "summary": summary,
        "source_bundles": [{"path": str(p), "manifest_sha256": digest(p / "manifest.json")} for p in bundles],
        "files": {name: digest(destination / name) for name in files}}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if manifest["status"] != "locked":
        raise ValueError("Deadline passed while selecting squads")
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    parser.add_argument("bundles", nargs="+")
    args = parser.parse_args()
    print(json.dumps(run(args.bundles, args.destination), indent=2))
