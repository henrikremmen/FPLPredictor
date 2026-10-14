"""Dated injury scenarios for challenger forecasts, not calibrated probabilities.

The FPL next-round percentage is evidence only for its named round. For later
rounds we expose conservative/return-as-reported scenarios rather than inventing
an empirically calibrated recovery curve. Unknown return dates remain unknown.
"""
import re

import numpy as np
import pandas as pd

MONTHS = {name: i for i, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class AvailabilityScenarioModel:
    """Serializable point adjustment on explicitly supplied scenario factors."""
    def __init__(self, scenario):
        if scenario not in {"conservative", "reported_return"}:
            raise ValueError("Unknown availability scenario")
        self.scenario = scenario

    def predict(self, rows):
        factor = rows[f"{self.scenario}_factor"].to_numpy(float)
        prediction = rows.prediction.to_numpy(float)
        if not np.isfinite(factor).all() or ((factor < 0) | (factor > 1)).any() or not np.isfinite(prediction).all():
            raise ValueError("Invalid scenario inputs")
        return prediction * factor


def reported_return(player: dict, captured_at) -> pd.Timestamp | None:
    captured_at = pd.Timestamp(captured_at)
    if captured_at.tzinfo is None:
        raise ValueError("Capture timestamp must include timezone")
    news_added = pd.to_datetime(player.get("news_added"), utc=True, errors="coerce")
    if pd.isna(news_added) or news_added > captured_at:
        return None
    news = player.get("news")
    if not isinstance(news, str):
        return None
    match = re.search(r"\bExpected back (\d{1,2}) ([A-Z][a-z]{2})(?: (20\d{2}))?\b", news)
    if not match or match[2] not in MONTHS:
        return None
    year = int(match[3]) if match[3] else news_added.year
    try:
        result = pd.Timestamp(year=year, month=MONTHS[match[2]], day=int(match[1]), tz="UTC")
        # Resolve New Year from the news timestamp, never the forecast GW.
        if not match[3] and result.date() < news_added.date():
            if news_added.month >= 10 and result.month <= 3:
                result = result.replace(year=year + 1)
            else:
                return None
    except ValueError:
        return None
    # An elapsed estimate is stale; it is not confirmation of recovery.
    return result if result.date() >= captured_at.date() else None


def availability_scenarios(player: dict, fixtures: list[dict], captured_at,
                           next_event: int) -> pd.DataFrame:
    """Return one row per team fixture, preserving double-gameweek timing.

Scenarios multiply underlying model forecasts. A factor of one means no
extra injury penalty, not certainty of playing or starting. The reported-return
scenario is intentionally not selected as a production point estimate.
"""
    capture = pd.Timestamp(captured_at)
    if capture.tzinfo is None:
        raise ValueError("Capture timestamp must include timezone")
    chance = player.get("chance_of_playing_next_round")
    try:
        factor = float(chance) / 100 if chance is not None else (1. if player.get("status", "a") == "a" else .75)
    except (TypeError, ValueError):
        raise ValueError("Invalid FPL availability percentage") from None
    if not np.isfinite(factor) or not 0 <= factor <= 1:
        raise ValueError("Invalid FPL availability percentage")
    return_at = reported_return(player, capture)
    rows = []
    for fixture in fixtures:
        if player["team"] not in [fixture.get("team_h"), fixture.get("team_a")]:
            continue
        event = fixture.get("event")
        if event is None or event < next_event:
            continue
        kickoff = pd.to_datetime(fixture.get("kickoff_time"), utc=True, errors="coerce")
        if pd.notna(kickoff) and kickoff <= capture:
            continue
        after_return = return_at is not None and pd.notna(kickoff) and kickoff >= return_at
        # Retain the explicit next-round percentage even if news dates disagree.
        reported = 1. if after_return and event > next_event else factor
        rows.append({"player_id": int(player["id"]), "fixture": fixture["id"], "GW": event,
            "kickoff_time": kickoff, "captured_at": capture,
            "news_added": player.get("news_added"), "news": player.get("news") or "",
            "reported_return": return_at, "conservative_factor": factor,
            "reported_return_factor": reported,
            "basis": ("official_next_round" if event == next_event and chance is not None else
                      "reported_return_scenario" if after_return else "unresolved_future_availability"),
            "calibrated": False})
    return pd.DataFrame(rows)


def evaluate_snapshot(snapshot, destination):
    """Materialize reproducible scenario forecasts without editing a live model."""
    import gzip
    import hashlib
    import json
    from pathlib import Path
    snapshot, destination = Path(snapshot), Path(destination)
    manifest = json.loads((snapshot / "manifest.json").read_text())
    captured = manifest["files"]["bootstrap"]["received_at"]
    with gzip.open(snapshot / "bootstrap.json.gz", "rt") as handle:
        bootstrap = json.load(handle)
    with gzip.open(snapshot / "fixtures.json.gz", "rt") as handle:
        fixtures = json.load(handle)
    forecast = pd.read_csv(snapshot / "horizon_fixture_forecast.csv")
    next_event = next(int(event["id"]) for event in bootstrap["events"] if event.get("is_next"))
    profiles = pd.concat([availability_scenarios(player, fixtures, captured, next_event)
                          for player in bootstrap["elements"] if player.get("element_type") in [1, 2, 3, 4]],
                         ignore_index=True)
    joined = forecast[["player_id", "fixture", "GW", "prediction"]].merge(
        profiles, on=["player_id", "fixture", "GW"], validate="one_to_one", how="left")
    if joined.conservative_factor.isna().any():
        raise ValueError("Missing availability scenario for forecast fixtures")
    joined["conservative_points"] = joined.prediction * joined.conservative_factor
    joined["reported_return_points"] = joined.prediction * joined.reported_return_factor
    summary = {"source_snapshot": str(snapshot), "captured_at": captured,
        "production_eligible": False, "calibrated": False,
        "rows": len(joined), "players": int(joined.player_id.nunique()),
        "players_with_changed_horizon": int(joined.loc[
            joined.reported_return_factor.ne(joined.conservative_factor), "player_id"].nunique()),
        "source_hashes": {name: hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
            for name in ["bootstrap.json.gz", "fixtures.json.gz", "horizon_fixture_forecast.csv"]}}
    destination.mkdir(parents=True, exist_ok=False)
    joined.to_csv(destination / "fixture_scenarios.csv", index=False)
    (destination / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("destination")
    args = parser.parse_args()
    print(json.dumps(evaluate_snapshot(args.snapshot, args.destination), indent=2))
