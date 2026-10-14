"""Cache public Understat JSON responses with hashes and collection times.

Historical match dates never substitute for observed provider availability.
Resume reuses immutable response files and checks their hashes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import requests


def fetch(session, folder, name, endpoint):
    path = folder / f"{name}.json"
    meta_path = folder / f"{name}.meta.json"
    if path.exists():
        meta = json.loads(meta_path.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta["sha256"]:
            raise ValueError(f"Changed cached response: {path}")
        return json.loads(path.read_text())
    url = f"https://understat.com/{endpoint}"
    started = datetime.now(timezone.utc).isoformat()
    response = session.get(url, timeout=(10, 40), headers={"X-Requested-With": "XMLHttpRequest"})
    response.raise_for_status()
    data = response.json()
    received = datetime.now(timezone.utc).isoformat()
    path.write_bytes(response.content)
    meta_path.write_text(json.dumps({"url": url, "started_at": started, "received_at": received,
        "sha256": hashlib.sha256(response.content).hexdigest(), "http_date": response.headers.get("Date")}, indent=2))
    time.sleep(.3)
    return data


def capture(destination, seasons):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    summary = {"source": "understat.com public JSON", "seasons": {}, "status": "collecting"}
    for season in seasons:
        league = fetch(session, destination, f"league_{season}", f"getLeagueData/EPL/{season}")
        completed = [match for match in league["dates"] if match["isResult"]]
        for index, match in enumerate(completed):
            data = fetch(session, destination, f"match_{match['id']}", f"getMatchData/{match['id']}")
            if not {"shots", "rosters"}.issubset(data):
                raise ValueError(f"Incomplete match schema: {match['id']}")
            if (index + 1) % 25 == 0:
                print(f"{season}: {index + 1}/{len(completed)} matches", flush=True)
        summary["seasons"][str(season)] = {"completed_matches": len(completed), "players": len(league["players"])}
        (destination / "manifest.json").write_text(json.dumps(summary, indent=2))
    summary["status"] = "complete"
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    (destination / "manifest.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination")
    parser.add_argument("--seasons", nargs="+", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(capture(args.destination, args.seasons), indent=2))
