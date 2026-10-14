"""Append-only local forecast bundles for prospective challenger evaluation.

Hashes detect changes against the manifest; this is a local audit trail, not an
independent timestamp authority. Callers remain responsible for validating the
source manifests and training-label chronology before making predictions.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc(value):
    value = pd.Timestamp(value)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.tz_convert("UTC")


def freeze_forecasts(predictions, *, deadline, sources, models, destination):
    """Copy exact sources/models and freeze equal candidate cohorts before deadline.

    sources: list of {path, received_at}, with times from acquisition manifests.
    models: dictionary from prediction model name to its trained artifact path.
    No caller-supplied forecast timestamp is accepted.
    """
    started = utc(datetime.now(timezone.utc))
    deadline = utc(deadline)
    if started >= deadline:
        raise ValueError("Cannot freeze forecasts at or after deadline")
    required = ["model", "season", "GW", "player_id", "fixture", "prediction"]
    if set(required) - set(predictions):
        raise ValueError("Incomplete forecast schema")
    if predictions.empty or predictions[required].isna().any().any():
        raise ValueError("Empty or missing forecast values")
    if predictions[["season", "GW"]].drop_duplicates().shape[0] != 1:
        raise ValueError("Lock exactly one season/gameweek per bundle")
    if not np.isfinite(predictions.prediction.to_numpy(float)).all():
        raise ValueError("Nonfinite predictions")
    keys = ["season", "GW", "player_id", "fixture"]
    if predictions.duplicated(["model", *keys]).any():
        raise ValueError("Duplicate forecast keys")
    if set(predictions.model) != set(models):
        raise ValueError("Missing or extra model artifacts")
    cohorts = [set(map(tuple, group[keys].to_numpy())) for _, group in predictions.groupby("model")]
    if any(cohort != cohorts[0] for cohort in cohorts):
        raise ValueError("Candidate forecast cohorts differ")
    if not sources:
        raise ValueError("Source evidence required")
    for source in sources:
        if utc(source["received_at"]) > started:
            raise ValueError("Source observation lies after forecast creation")
        if not Path(source["path"]).is_file():
            raise ValueError("Missing source file")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": 1, "status": "incomplete", "started_at": str(started),
        "deadline": str(deadline), "season": str(predictions.season.iloc[0]),
        "GW": int(predictions.GW.iloc[0]), "rows": len(predictions), "files": [],
        "models": {}, "production_eligible": False,
        "timing_evidence": "local clock and acquisition manifests; not independent timestamping"}

    def copy_file(path, filename, kind, received_at=None):
        target = destination / filename
        shutil.copyfile(path, target)
        entry = {"file": filename, "kind": kind, "original_path": str(Path(path).resolve()), "sha256": digest(target)}
        if received_at is not None:
            entry["received_at"] = str(utc(received_at))
        manifest["files"].append(entry)

    for index, source in enumerate(sources):
        copy_file(source["path"], f"source_{index:04d}.bin", "source", source["received_at"])
    for index, (name, path) in enumerate(sorted(models.items())):
        filename = f"model_{index:03d}.joblib"
        copy_file(path, filename, "model")
        manifest["models"][name] = filename
    predictions.to_csv(destination / "predictions.csv", index=False)
    manifest["files"].append({"file": "predictions.csv", "kind": "predictions", "sha256": digest(destination / "predictions.csv")})
    completed = utc(datetime.now(timezone.utc))
    manifest["completed_at"] = str(completed)
    manifest["status"] = "locked" if completed < deadline else "missed_deadline"
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if completed >= deadline:
        raise ValueError("Deadline passed while materializing bundle")
    return manifest


def verify_lock(destination):
    destination = Path(destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    if manifest["status"] != "locked" or not utc(manifest["started_at"]) <= utc(manifest["completed_at"]) < utc(manifest["deadline"]):
        raise ValueError("Bundle was not locked before deadline")
    files = manifest["files"]
    filenames = [entry["file"] for entry in files]
    if (len(set(filenames)) != len(filenames) or "predictions.csv" not in filenames
            or not any(entry["kind"] == "source" for entry in files)
            or not manifest["models"]
            or set(manifest["models"].values()) != {entry["file"] for entry in files if entry["kind"] == "model"}):
        raise ValueError("Incomplete bundle manifest")
    for entry in manifest["files"]:
        if Path(entry["file"]).name != entry["file"]:
            raise ValueError("Invalid bundle path")
        if digest(destination / entry["file"]) != entry["sha256"]:
            raise ValueError(f"Changed locked file: {entry['file']}")
        if entry["kind"] == "source" and utc(entry["received_at"]) > utc(manifest["started_at"]):
            raise ValueError("Source is newer than forecast creation")
    return manifest
