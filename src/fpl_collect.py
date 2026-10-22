"""Automatic public FPL collection for the fpl-data repository (plan D1).

Runs hourly from GitHub Actions (``auto``). Every decision comes from files
already on disk, so reruns are idempotent:

* Light snapshot (bootstrap-static, fixtures, event-status, set-piece notes)
  once a day after 02:30 UTC, when price changes have settled, and in the
  T-24h/6h/1h deadline windows.
* Full round export once FPL marks a Gameweek ``finished`` and
  ``data_checked``: element-summary for every player, ``event/{gw}/live`` and
  fixtures, written as vaastav-compatible CSVs plus a stable ``code`` column.
  FPL corrections to earlier rounds are logged in ``corrections.csv`` before
  the files are rewritten.

The CSV layout follows github.com/vaastav/Fantasy-Premier-League (MIT licence,
Copyright (c) 2017-19 Vaastav Anand). Only stdlib, requests, pandas and
``data_contract.py`` are used, so both files can be copied unchanged into
fpl-data. Failed requests or contract violations exit non-zero.

    python src/fpl_collect.py --data-root fpl-data auto
    python src/fpl_collect.py --data-root fpl-data export --xp-snapshots data/raw/live_fpl
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import time

import pandas as pd
import requests

from data_contract import (
    ContractError, diff_rows, validate_bootstrap, validate_element_summary,
    validate_fixtures, validate_gameweeks, validate_live, validate_price_moves,
)

API = 'https://fantasy.premierleague.com/api/'
USER_AGENT = 'fplmodell-snapshot/1.0'
REQUEST_INTERVAL = 0.5  # at most two requests per second
CHECKPOINTS = ((24.0, "24h"), (6.0, "6h"), (1.0, "1h"))
DAILY_AFTER = pd.Timedelta(hours=2, minutes=30)  # UTC, after FPL price changes
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "AM"}
CLEANED_COLUMNS = [
    'first_name', 'second_name', 'goals_scored', 'assists', 'total_points', 'minutes',
    'goals_conceded', 'creativity', 'influence', 'threat', 'bonus', 'bps', 'ict_index',
    'clean_sheets', 'red_cards', 'yellow_cards', 'selected_by_percent', 'now_cost',
    'element_type',
]


class CollectError(RuntimeError):
    """A request failed; the run must end red rather than leave a silent gap."""


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def capture_endpoint(endpoint, directory, name):
    record = {'endpoint': endpoint, 'url': API+endpoint, 'started_at': now()}
    for attempt in range(3):
        try:
            r = requests.get(record['url'], timeout=(10, 35),
                headers={'User-Agent': USER_AGENT, 'Cache-Control': 'no-cache'})
            record.update(received_at=now(), status=r.status_code,
                http_date=r.headers.get('Date'), age=r.headers.get('Age'))
            if r.status_code in [429, 500, 502, 503, 504] and attempt < 2:
                try:
                    delay = float(r.headers.get('Retry-After', 2**(attempt+1)))
                except ValueError:
                    delay = 5
                if delay > 30:
                    r.raise_for_status()  # defer long rate limits to a future run
                time.sleep(max(1, delay))
                continue
            r.raise_for_status()
            body = r.content
            data = r.json()
            path = directory / (name + '.json.gz')
            path.write_bytes(gzip.compress(body, mtime=0))
            record.update(file=path.name, sha256=digest(body), bytes=len(body),
                          stored_sha256=digest(path.read_bytes()))
            return data, record
        except (requests.RequestException, ValueError) as exc:
            record['error'] = str(exc)
            if attempt == 2 or record.get('status') == 429:
                return None, record
            time.sleep(attempt+1)
    return None, record


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


def fetch(endpoint: str, directory: Path, name: str, records: dict):
    data, record = capture_endpoint(endpoint, directory, name)
    records[name] = record
    if data is None:
        raise CollectError(f"{endpoint}: {record.get('error') or record.get('status')}")
    time.sleep(REQUEST_INTERVAL)
    return data


def season_of(bootstrap: dict) -> str:
    year = pd.Timestamp(bootstrap["events"][0]["deadline_time"]).year
    return f"{year}-{str(year + 1)[-2:]}"


def read_json_gz(path: Path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def stamped(staging: Path) -> str:
    """UTC time plus the staging folder's random suffix, unique even within one second."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + staging.name.rsplit("_", 1)[-1]


def snapshot_manifests(root: Path) -> list[dict]:
    """Complete snapshot manifests below ``root`` (light snapshots or capture_* folders)."""
    manifests = []
    for path in sorted(Path(root).glob("**/manifest.json")):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") == "complete" and (path.parent / "bootstrap.json.gz").exists():
            manifests.append({**manifest, "directory": str(path.parent)})
    return manifests


def _target_id(manifest: dict):
    target = manifest.get("target_event") or {}
    return target.get("id") if isinstance(target, dict) else target


def due_phases(bootstrap: dict, manifests: list[dict], observed) -> list[str]:
    """Daily snapshot after 02:30 UTC plus the active deadline checkpoint, each once."""
    observed = pd.Timestamp(observed)
    phases = []
    today = observed.date().isoformat()
    if observed >= observed.normalize() + DAILY_AFTER and not any(
            "daily" in m.get("capture_phases", []) and str(m.get("started_at", "")).startswith(today)
            for m in manifests):
        phases.append("daily")
    target = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    phase = checkpoint_for(target["deadline_time"], observed) if target else None
    if phase and not any(phase in m.get("capture_phases", []) and _target_id(m) == target["id"]
                         for m in manifests):
        phases.append(phase)
    return phases


def light_snapshot(snapshots: Path, directory: Path, bootstrap: dict, records: dict,
                   phases: list[str], observed) -> Path:
    """Complete a staged snapshot (bootstrap already fetched) and move it into place."""
    season = season_of(bootstrap)
    target = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    validate_fixtures(fetch("fixtures/", directory, "fixtures", records))
    fetch("event-status/", directory, "event_status", records)
    fetch("team/set-piece-notes/", directory, "set_piece_notes", records)
    previous = max(snapshot_manifests(snapshots), key=lambda m: m["started_at"], default=None)
    if previous is not None:
        days = (pd.Timestamp(observed) - pd.Timestamp(previous["started_at"])).total_seconds() / 86400
        validate_price_moves(read_json_gz(Path(previous["directory"]) / "bootstrap.json.gz"),
                             bootstrap, days)
    manifest = {
        "started_at": records["bootstrap"]["started_at"], "finished_at": now(),
        "status": "complete", "capture_phases": phases, "season": season,
        "target_event": {"id": target["id"], "deadline_time": target["deadline_time"]} if target else None,
        "files": records,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    final = snapshots / season / stamped(directory)
    final.parent.mkdir(parents=True, exist_ok=True)
    directory.rename(final)
    return final


def load_xp(directories, season_dir: Path | None = None) -> dict[int, dict[int, str]]:
    """FPL ``ep_next`` per Gameweek from the latest complete snapshot before its deadline.

    Values already written to a round file win: they were recorded before the
    deadline and must not change when a later run lacks the snapshot.
    """
    best = {}
    for directory in directories:
        for manifest in snapshot_manifests(directory):
            target = manifest.get("target_event")
            if not isinstance(target, dict) or not target.get("deadline_time"):
                continue
            started = pd.Timestamp(manifest["started_at"])
            if started >= pd.Timestamp(target["deadline_time"]):
                continue
            if target["id"] not in best or started > pd.Timestamp(best[target["id"]]["started_at"]):
                best[target["id"]] = manifest
    xp = {
        int(gw): {e["id"]: e.get("ep_next") or "" for e in
                  read_json_gz(Path(m["directory"]) / "bootstrap.json.gz")["elements"]}
        for gw, m in best.items()
    }
    for path in sorted((season_dir / "gws").glob("gw*.csv")) if season_dir else []:
        if path.stem[2:].isdigit():
            old = pd.read_csv(path, usecols=["element", "xP"], dtype=str, keep_default_na=False)
            known = {int(e): value for e, value in zip(old["element"], old["xP"]) if value != ""}
            xp.setdefault(int(path.stem[2:]), {}).update(known)
    return xp


def gameweek_rows(bootstrap: dict, fixtures: list, summaries: dict, xp: dict,
                  events) -> pd.DataFrame:
    """vaastav ``merged_gw`` rows for ``events``: name, position, team, xP, history, code, GW."""
    teams = {team["id"]: team["name"] for team in bootstrap["teams"]}
    sides = {fixture["id"]: (fixture["team_h"], fixture["team_a"]) for fixture in fixtures}
    events = set(events)
    records = []
    for element in bootstrap["elements"]:
        for row in summaries[element["id"]]["history"]:
            if row["round"] not in events:
                continue
            home, away = sides.get(row["fixture"], (None, None))
            records.append({
                "name": f"{element['first_name']} {element['second_name']}",
                "position": POSITIONS[element["element_type"]],
                "team": teams.get(home if row["was_home"] else away, ""),
                "xP": xp.get(row["round"], {}).get(element["id"], ""),
                **row, "code": element["code"], "GW": row["round"],
            })
    history = sorted({key for summary in summaries.values() for row in summary["history"] for key in row})
    frame = pd.DataFrame.from_records(records, columns=["name", "position", "team", "xP", *history, "code", "GW"])
    return frame.sort_values(["GW", "element", "fixture"]).reset_index(drop=True)


def _csv(frame: pd.DataFrame) -> str:
    return frame.to_csv(index=False, lineterminator="\n")


def _strings(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)


def write_season(season_dir: Path, bootstrap: dict, fixtures: list, summaries: dict,
                 rows: pd.DataFrame, events, observed_at: str) -> int:
    """Write vaastav files for one season; return the number of logged corrections."""
    gws = season_dir / "gws"
    gws.mkdir(parents=True, exist_ok=True)
    corrections = []
    for gw in events:
        text = _csv(rows[rows["GW"] == gw].drop(columns="GW"))
        path = gws / f"gw{gw}.csv"
        if path.exists():
            old = path.read_text()
            if old == text:
                continue
            corrections.append(diff_rows(_strings(old), _strings(text)).assign(GW=gw, detected_at=observed_at))
        path.write_text(text)
    (gws / "merged_gw.csv").write_text(_csv(rows))
    if corrections:
        log = season_dir / "corrections.csv"
        pd.concat(corrections).to_csv(log, mode="a", header=not log.exists(), index=False)

    elements = bootstrap["elements"]
    keys = sorted({key for element in elements for key in element})
    raw = pd.DataFrame([{key: str(element.get(key)) for key in keys} for element in elements])
    (season_dir / "players_raw.csv").write_text(_csv(raw))
    frame = pd.DataFrame(elements)
    cleaned = frame[CLEANED_COLUMNS].copy()
    cleaned["element_type"] = cleaned["element_type"].map(POSITIONS)
    cost = frame["now_cost"] / 10
    cleaned["value_per_m"] = (frame["total_points"] / cost).round(1).where(cost > 0, "")
    (season_dir / "cleaned_players.csv").write_text(_csv(cleaned))
    (season_dir / "player_idlist.csv").write_text(_csv(frame[["first_name", "second_name", "id"]]))
    (season_dir / "fixtures.csv").write_text(_csv(pd.DataFrame.from_records(fixtures)))
    (season_dir / "teams.csv").write_text(_csv(pd.DataFrame.from_records(bootstrap["teams"])))
    past = [{"element": e["id"], "code": e["code"], **row}
            for e in elements for row in summaries[e["id"]]["history_past"]]
    (season_dir / "history_past.csv").write_text(_csv(pd.DataFrame.from_records(past)))
    return sum(len(change) for change in corrections)


def export(data_root: Path, xp_dirs=()) -> dict:
    """Full export of every finished, data-checked Gameweek; validate before writing."""
    data_root = Path(data_root)
    started = now()
    staging = Path(tempfile.mkdtemp(prefix="export_", dir=data_root))
    records = {}
    try:
        bootstrap = validate_bootstrap(fetch("bootstrap-static/", staging, "bootstrap", records))
        fixtures = validate_fixtures(fetch("fixtures/", staging, "fixtures", records))
        season = season_of(bootstrap)
        season_dir = data_root / "data" / season
        checked = [e["id"] for e in bootstrap["events"] if e["finished"] and e["data_checked"]]
        if not checked:
            return {"season": season, "events": [], "corrections": 0}
        new = [gw for gw in checked if not (season_dir / "gws" / f"gw{gw}.csv").exists()]
        summaries_dir = staging / "element_summaries"
        summaries_dir.mkdir()
        summaries = {}
        for element in sorted(bootstrap["elements"], key=lambda e: e["id"]):
            pid = element["id"]
            payload = fetch(f"element-summary/{pid}/", summaries_dir, f"player_{pid}", records)
            summaries[pid] = validate_element_summary(payload, pid)
        for gw in new:
            validate_live(fetch(f"event/{gw}/live/", staging, f"live_gw{gw}", records), gw)
        xp = load_xp([data_root / "snapshots", *xp_dirs], season_dir)
        rows = gameweek_rows(bootstrap, fixtures, summaries, xp, checked)
        validate_gameweeks(rows, fixtures)
        corrections = write_season(season_dir, bootstrap, fixtures, summaries, rows, checked, started)

        with tarfile.open(staging / "element_summaries.tar", "w") as tar:
            for path in sorted(summaries_dir.iterdir()):
                tar.add(path, arcname=path.name)
        shutil.rmtree(summaries_dir)
        manifest = {"started_at": started, "finished_at": now(), "status": "complete",
                    "season": season, "checked_events": checked, "new_events": new,
                    "corrections": corrections, "rows": len(rows), "files": records}
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
        raw = season_dir / "raw" / f"export_{stamped(staging)}"
        raw.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(raw)
        return {"season": season, "events": new, "corrections": corrections, "raw": str(raw)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def auto(data_root: Path, xp_dirs=(), observed_at=None, phases=None) -> dict:
    """Hourly entry point. ``phases`` forces a light snapshot and skips the export."""
    data_root = Path(data_root)
    observed = pd.Timestamp(observed_at or now())
    snapshots = data_root / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="pending_", dir=data_root))
    records = {}
    result = {"light_snapshot": None, "export": None}
    try:
        bootstrap = validate_bootstrap(fetch("bootstrap-static/", directory, "bootstrap", records))
        due = phases or due_phases(bootstrap, snapshot_manifests(snapshots), observed)
        if due:
            result["light_snapshot"] = str(light_snapshot(snapshots, directory, bootstrap, records, due, observed))
        season_dir = data_root / "data" / season_of(bootstrap)
        pending = [e["id"] for e in bootstrap["events"] if e["finished"] and e["data_checked"]
                   and not (season_dir / "gws" / f"gw{e['id']}.csv").exists()]
        if pending and phases is None:
            result["export"] = export(data_root, xp_dirs)
        return result
    finally:
        if directory.exists():
            shutil.rmtree(directory)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["auto", "light", "export"])
    parser.add_argument("--data-root", type=Path, required=True, help="fpl-data checkout")
    parser.add_argument("--phase", default="manual", help="label for a forced light snapshot")
    parser.add_argument("--xp-snapshots", type=Path, nargs="*", default=[],
                        help="extra snapshot folders (e.g. data/raw/live_fpl) for pre-deadline xP")
    args = parser.parse_args(argv)
    try:
        if args.mode == "export":
            result = export(args.data_root, args.xp_snapshots)
        else:
            result = auto(args.data_root, args.xp_snapshots,
                          phases=[args.phase] if args.mode == "light" else None)
    except (CollectError, ContractError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
