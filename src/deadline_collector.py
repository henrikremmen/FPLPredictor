"""Collect one immutable FPL snapshot in each pre-deadline checkpoint window.

Run ``python src/deadline_collector.py --check`` from cron every 10–15 minutes,
or use ``--watch`` on a machine that remains online.  Completed manifests are
the state: restarts never repeat an already completed checkpoint.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import pandas as pd
import requests

from capture_fpl import API, run


CHECKPOINTS = ((24.0, "24h"), (6.0, "6h"), (1.0, "1h"))


def checkpoint_for(deadline, observed_at=None) -> str | None:
    """Return the active checkpoint bucket, never backfilling missed buckets."""
    current = pd.Timestamp(observed_at or datetime.now(timezone.utc))
    if current.tzinfo is None:
        current = current.tz_localize("UTC")
    deadline = pd.Timestamp(deadline)
    hours = (deadline - current).total_seconds() / 3600
    if hours <= 0 or hours > CHECKPOINTS[0][0]:
        return None
    if hours > CHECKPOINTS[1][0]:
        return "24h"
    if hours > CHECKPOINTS[2][0]:
        return "6h"
    return "1h"


def completed_phases(root: Path, event: int) -> set[str]:
    completed = set()
    parent = root / "data" / "raw" / "live_fpl"
    for path in parent.glob("capture_*/manifest.json"):
        try:
            manifest = json.loads(path.read_text())
            target = manifest.get("target_event") or {}
            target_id = target.get("id") if isinstance(target, dict) else target
            if (manifest.get("status") == "complete" and int(target_id) == int(event)
                    and manifest.get("capture_phase") in {"24h", "6h", "1h"}):
                completed.add(manifest["capture_phase"])
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
    return completed


def next_event(timeout=30) -> dict | None:
    response = requests.get(
        API + "bootstrap-static/", timeout=timeout,
        headers={"User-Agent": "fplmodell-deadline-scheduler/1.0"},
    )
    response.raise_for_status()
    return next((event for event in response.json()["events"] if event.get("is_next")), None)


def collect_due(root: Path, observed_at=None):
    event = next_event()
    if event is None:
        return {"status": "idle", "reason": "No next FPL event"}
    phase = checkpoint_for(event["deadline_time"], observed_at)
    if phase is None:
        return {"status": "idle", "event": event["id"], "reason": "Outside checkpoint windows"}
    if phase in completed_phases(root, event["id"]):
        return {"status": "already_complete", "event": event["id"], "phase": phase}
    destination = run(root, capture_phase=phase)
    return {
        "status": "captured" if destination is not None else "skipped",
        "event": event["id"], "phase": phase,
        "destination": str(destination) if destination is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--watch", action="store_true", help="Poll every five minutes")
    parser.add_argument("--check", action="store_true", help="Run one scheduler check")
    args = parser.parse_args()
    if not args.watch and not args.check:
        parser.error("choose --check or --watch")
    while True:
        try:
            result = collect_due(args.root)
            print(json.dumps(result, indent=2), flush=True)
        except (requests.RequestException, ValueError) as exc:
            print(json.dumps({"status": "error", "error": str(exc)}), flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
