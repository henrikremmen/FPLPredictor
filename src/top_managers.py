"""Top-manager tracker: today's top 100, the all-time legacy 100 still playing, and the top 1%.

One local run after each deadline stores what those managers fielded in the
latest Gameweek (``data/local/top_managers/<season>/gwNN.json``); the app then
compares the user's squad against it without further FPL calls.

- top100: overall ranks 1-100, read in full.
- legacy: candidates are the top of Fantasy Football Pundit's all-time table
  (it links this season's FPL ids); we score them ourselves from FPL history
  and keep the best 100 who played the latest Gameweek. Built once a season,
  because FPL issues new ids every season.
- top1pct: a random sample of whole standings pages inside the top 1%; the
  points cutoff itself is read directly.

Run: ``python src/top_managers.py collect [--force] [--rebuild-legacy]``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import statistics
from threading import Lock
import time

import requests

from data_contract import ContractError, _missing, _raise, validate_bootstrap
from fpl_collect import season_of
from manager_analytics import AnalyticsService

ROOT = Path(__file__).resolve().parents[1]
API = "https://fantasy.premierleague.com/api/"
SEED_URL = "https://www.fantasyfootballpundit.com/all-time-fpl-manager-ranking-table/?page={}"
USER_AGENT = "fplmodell-readonly-app/1.0"
OVERALL_LEAGUE = 314
PAGE_SIZE = 50
TOP_SHARE = 0.01
SAMPLE_PAGES = 40            # 40 x 50 = 2,000 managers: EO within about ±2.2 pp (95%)
WORKERS = 4
MAX_RATE = 10.0              # requests per second across all workers
RETRY_STATUS = {429, 500, 502, 503, 504}
LEGACY_SEED_PAGES = 3        # 100 candidates per page
LEGACY_SIZE = 100
LEGACY_MIN_SEASONS = 5
LEGACY_DECAY = 0.8           # each older season weighs 80% of the next
SCHEMA = 1
COHORTS = ("top100", "legacy", "top1pct", "youtubers")
# Well-known FPL YouTubers and experts, this season's FPL ids (they change every season),
# each checked against entry/{id}/ (source: LiveFPL Elite). Add one line per creator.
CREATORS = {"2026-27": {
    41: "Let's Talk FPL", 3054: "FPL Harry", 1527: "FPLtips (Ryan)", 5133: "BigManBakar",
    70: "FPL Salah", 252: "Mark Sutherns (FPL General)", 3315: "Pras (FPL Wire)", 53517: "Ben Crellin",
    674: "Lee Giles", 209763: "Rich Clarke", 18124: "FPL Matthew", 22728: "Tom Freeman (Scout)",
    # found in the creators' shared mini-leagues, names checked against entry/{id}/
    120: "FPL Mate", 199: "FPL Raptor", 21: "FPL Fran", 84298: "Planet FPL (Suj)",
    298: "FPL Focal",  # "Oscar - | Focal Point": FPL Focal's host is Oscar
}}
LAST_EVENT = 38

PROGRESS = {"phase": "idle", "done": 0, "total": 0}
_progress_lock = Lock()


def _progress(phase: str | None = None, *, done: int | None = None, total: int | None = None,
              step: int = 0) -> None:
    with _progress_lock:
        if phase is not None:
            PROGRESS["phase"] = phase
        if total is not None:
            PROGRESS["total"] = total
        if done is not None:
            PROGRESS["done"] = done
        PROGRESS["done"] += step


class CollectError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Fetcher:
    """Throttled, retrying GETs shared by the worker threads."""

    def __init__(self, session: requests.Session | None = None, rate: float = MAX_RATE) -> None:
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.interval = 1 / rate
        self._lock = Lock()
        self._next = 0.0

    def _wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        time.sleep(max(0.0, start - now))

    def get(self, url: str, *, text: bool = False):
        error, status = "", None
        for attempt in range(3):
            self._wait()
            try:
                response = self.session.get(url, timeout=(10, 35))
            except requests.RequestException as exc:
                error = str(exc)
                time.sleep(attempt + 1)
                continue
            status = response.status_code
            if status == 200:
                try:
                    return response.text if text else response.json()
                except ValueError as exc:
                    raise CollectError(f"{url}: invalid JSON", status) from exc
            error = f"HTTP {status}"
            if status not in RETRY_STATUS or attempt == 2:
                break
            try:
                delay = float(response.headers.get("Retry-After", 2 ** (attempt + 1)))
            except ValueError:
                delay = 5.0
            if delay > 30:
                break  # a long rate limit: stop rather than keep knocking
            time.sleep(max(1.0, delay))
        raise CollectError(f"{url}: {error}", status)

    def many(self, urls: list[str], *, text: bool = False) -> dict[str, object]:
        """Fetch in parallel; a 404 (deleted team) is skipped, anything else fails the run."""
        def one(url: str):
            try:
                data = self.get(url, text=text)
            except CollectError as exc:
                if exc.status != 404:
                    raise
                data = None
            _progress(step=1)
            return url, data

        unique = list(dict.fromkeys(urls))
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return {url: data for url, data in pool.map(one, unique) if data is not None}


# --- boundary validation (data contract D3) -----------------------------------

def validate_standings(data, page: int) -> list[dict]:
    where = f"standings page {page}"
    if not isinstance(data, dict) or not isinstance(data.get("standings"), dict):
        raise ContractError([f"{where}: missing standings"])
    rows = data["standings"].get("results")
    if not isinstance(rows, list):
        raise ContractError([f"{where}: missing results"])
    problems = []
    for row in rows:
        problems += _missing(row, ("entry", "rank", "rank_sort", "total", "event_total",
                                   "player_name", "entry_name"), where)
    _raise(problems)
    return rows


def validate_picks(data, entry: int) -> dict:
    where = f"entry {entry} picks"
    if not isinstance(data, dict):
        raise ContractError([f"{where}: not a JSON object"])
    problems = _missing(data, ("picks", "entry_history", "active_chip"), where)
    _raise(problems)
    problems += _missing(data["entry_history"], ("event", "points", "total_points",
                                                 "event_transfers_cost", "bank", "value"), where)
    if len(data["picks"]) != 15:
        problems.append(f"{where}: {len(data['picks'])} picks, expected 15")
    for pick in data["picks"]:
        problems += _missing(pick, ("element", "multiplier", "is_captain"), where)
    _raise(problems)
    return data


# --- pure helpers ---------------------------------------------------------------

def seed_ids(html: str) -> list[int]:
    """FPL entry ids linked from an all-time ranking page, in table order."""
    found = re.findall(r"fantasy\.premierleague\.com/entry/(\d+)", html)
    return list(dict.fromkeys(int(value) for value in found))


def legacy_score(past: list[dict]) -> dict | None:
    """Recency-weighted mean of log10(overall rank); lower is better. None below the minimum."""
    seasons = sorted((row for row in past if (row.get("rank") or 0) > 0),
                     key=lambda row: str(row.get("season_name")), reverse=True)
    if len(seasons) < LEGACY_MIN_SEASONS:
        return None
    weights = [LEGACY_DECAY ** age for age in range(len(seasons))]
    score = sum(w * math.log10(row["rank"]) for w, row in zip(weights, seasons)) / sum(weights)
    ranks = [int(row["rank"]) for row in seasons]
    return {
        "legacy_score": round(score, 4),
        "typical_rank": round(10 ** score),
        "seasons": len(ranks),
        "top10k_seasons": sum(rank <= 10_000 for rank in ranks),
        "best_rank": min(ranks),
    }


def sample_pages(cutoff_page: int, season: str, event: int, count: int = SAMPLE_PAGES) -> list[int]:
    """Random standings pages inside the top 1%, reproducible per season and Gameweek."""
    rng = random.Random(f"{season}-gw{event}")
    return sorted(rng.sample(range(1, cutoff_page + 1), min(count, cutoff_page)))


def match_percent(mine: dict[int, float], theirs: dict[int, float]) -> float:
    """Weighted overlap of two multiplier vectors: 100 = same XI and captain, 0 = nothing shared."""
    ids = set(mine) | set(theirs)
    top = sum(min(mine.get(i, 0), theirs.get(i, 0)) for i in ids)
    bottom = sum(max(mine.get(i, 0), theirs.get(i, 0)) for i in ids)
    return round(100 * top / bottom, 1) if bottom else 0.0


def _share(counter: Counter, size: int) -> dict[str, float]:
    return {str(key): round(100 * value / size, 1) for key, value in counter.most_common()}


def cohort_summary(picks_by_entry: dict[int, dict]) -> dict:
    """Aggregates the app shows for any cohort: EO field, captains, chips, hits, average total."""
    size = len(picks_by_entry)
    field = AnalyticsService._field_metrics(picks_by_entry, size)
    captains = Counter(
        int(pick["element"]) for payload in picks_by_entry.values()
        for pick in payload["picks"] if pick["is_captain"]
    )
    chips = Counter(payload["active_chip"] for payload in picks_by_entry.values() if payload["active_chip"])
    history = [payload["entry_history"] for payload in picks_by_entry.values()]
    return {
        "size": size,
        "field": {str(pid): {key: round(value, 2) for key, value in row.items()}
                  for pid, row in field.items()},
        "captains": _share(captains, size) if size else {},
        "chips": _share(chips, size) if size else {},
        "average_hits": round(statistics.fmean(h["event_transfers_cost"] for h in history), 2) if size else 0,
        "average_total": round(statistics.fmean(h["total_points"] for h in history), 1) if size else None,
    }


def manager_row(entry: int, picks: dict, history: dict | None, transfers: list | None,
                event: int, extra: dict) -> dict:
    current = picks["entry_history"]
    captain = next((int(p["element"]) for p in picks["picks"] if p["is_captain"]), None)
    return {
        "entry": entry, **extra,
        "total": int(current["total_points"]), "event_points": int(current["points"]),
        "overall_rank": current.get("overall_rank"),
        "picks": [[int(p["element"]), int(p["multiplier"])] for p in picks["picks"]],
        "captain": captain, "chip": picks["active_chip"],
        "transfers": [[int(t["element_out"]), int(t["element_in"])]
                      for t in (transfers or []) if int(t.get("event", 0)) == event],
        "hits": int(current["event_transfers_cost"]),
        "bank": int(current["bank"]), "value": int(current["value"]),
        "chips_used": [{"name": c.get("name"), "event": c.get("event")}
                       for c in (history or {}).get("chips", [])],
    }


# --- collection -----------------------------------------------------------------

def _season_dir(root: Path, season: str) -> Path:
    return root / "data" / "local" / "top_managers" / season


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":")))
    tmp.replace(path)


def build_legacy(fetcher: Fetcher, season: str, event: int) -> dict:
    _progress("Finding all-time managers")
    candidates: list[int] = []
    for page in range(1, LEGACY_SEED_PAGES + 1):
        candidates += seed_ids(fetcher.get(SEED_URL.format(page), text=True))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        raise CollectError("The all-time ranking page listed no FPL ids; its layout may have changed.")
    histories = fetcher.many([f"{API}entry/{entry}/history/" for entry in candidates])
    scored = []
    for entry in candidates:
        history = histories.get(f"{API}entry/{entry}/history/")
        if not history or not any(int(row.get("event", 0)) == event for row in history.get("current", [])):
            continue  # not playing this season, or missed the latest Gameweek
        score = legacy_score(history.get("past", []))
        if score:
            scored.append({"entry": entry, **score})
    scored.sort(key=lambda row: row["legacy_score"])
    chosen = scored[:LEGACY_SIZE]
    profiles = fetcher.many([f"{API}entry/{row['entry']}/" for row in chosen])
    for row in chosen:
        profile = profiles.get(f"{API}entry/{row['entry']}/", {})
        row["name"] = f"{profile.get('player_first_name', '')} {profile.get('player_last_name', '')}".strip()
        row["team_name"] = profile.get("name", "")
    return {"season": season, "built_at": datetime.now(timezone.utc).isoformat(),
            "source": SEED_URL.format(1), "candidates": len(candidates), "managers": chosen}


def collect(root: Path = ROOT, *, fetcher: Fetcher | None = None, force: bool = False,
            rebuild_legacy: bool = False) -> dict:
    fetcher = fetcher or Fetcher()
    _progress("Reading FPL registry", done=0, total=0)
    bootstrap = validate_bootstrap(fetcher.get(API + "bootstrap-static/"))
    current = next((row for row in bootstrap["events"] if row["is_current"]), None)
    if current is None:
        raise CollectError("No Gameweek has started yet.")
    event, season = int(current["id"]), season_of(bootstrap)
    season_dir = _season_dir(root, season)
    path = season_dir / f"gw{event:02d}.json"
    if path.exists() and not force:
        existing = json.loads(path.read_text())
        if existing.get("event_finished"):
            _progress("Up to date")
            return existing

    legacy_path = season_dir / "legacy.json"
    if rebuild_legacy or not legacy_path.exists():
        legacy = build_legacy(fetcher, season, event)
        _write_json(legacy_path, legacy)
    else:
        legacy = json.loads(legacy_path.read_text())

    total_players = int(bootstrap["total_players"])
    top_n = math.ceil(total_players * TOP_SHARE)
    cutoff_page = math.ceil(top_n / PAGE_SIZE)
    pages = sample_pages(cutoff_page, season, event)
    page_set = sorted({1, 2, 3, cutoff_page, *pages})  # page 3: cached pages can disagree at a boundary
    legacy_meta = {int(row["entry"]): row for row in legacy["managers"]}
    creators = CREATORS.get(season, {})

    _progress("Reading overall standings", done=0, total=len(page_set))
    standings_url = f"{API}leagues-classic/{OVERALL_LEAGUE}/standings/?page_standings={{}}"
    raw = fetcher.many([standings_url.format(page) for page in page_set])
    standings = {page: validate_standings(raw[standings_url.format(page)], page)
                 for page in page_set if standings_url.format(page) in raw}
    if 1 not in standings or 2 not in standings or cutoff_page not in standings:
        raise CollectError("Overall standings pages are missing.")
    leaders = {int(row["entry"]): row for page in (3, 2, 1) for row in standings.get(page, [])}
    top100 = sorted(leaders.values(), key=lambda row: row["rank_sort"])[:100]
    inside = [row for row in standings[cutoff_page] if row["rank_sort"] <= top_n] or standings[cutoff_page]
    cutoff_row = max(inside, key=lambda row: row["rank_sort"])
    sample = {int(row["entry"]): row for page in pages for row in standings.get(page, [])
              if row["rank_sort"] <= top_n}

    tracked = {int(row["entry"]) for row in top100} | set(legacy_meta) | set(creators)
    picks_url = f"{API}entry/{{}}/event/{event}/picks/"
    urls = [picks_url.format(entry) for entry in tracked | set(sample)]
    urls += [f"{API}entry/{entry}/{kind}/" for entry in tracked for kind in ("history", "transfers")]
    _progress("Reading squads", done=0, total=len(urls))
    fetched = fetcher.many(urls)
    picks = {entry: validate_picks(fetched[picks_url.format(entry)], entry)
             for entry in tracked | set(sample) if picks_url.format(entry) in fetched}

    def rows(entries, extra_of) -> list[dict]:
        return [manager_row(entry, picks[entry], fetched.get(f"{API}entry/{entry}/history/"),
                            fetched.get(f"{API}entry/{entry}/transfers/"), event, extra_of(entry))
                for entry in entries if entry in picks]

    top_meta = {int(row["entry"]): row for row in top100}
    cohorts = {
        "top100": {
            **cohort_summary({e: picks[e] for e in top_meta if e in picks}),
            "managers": rows(top_meta, lambda e: {
                "name": top_meta[e]["player_name"], "team_name": top_meta[e]["entry_name"],
                "rank": top_meta[e]["rank"]}),
        },
        "legacy": {
            **cohort_summary({e: picks[e] for e in legacy_meta if e in picks}),
            "managers": rows(legacy_meta, lambda e: {
                key: legacy_meta[e].get(key) for key in (
                    "name", "team_name", "legacy_score", "typical_rank", "seasons",
                    "top10k_seasons", "best_rank")}),
        },
        "youtubers": {
            **cohort_summary({e: picks[e] for e in creators if e in picks}),
            "managers": rows(creators, lambda e: {"name": creators[e], "team_name": ""}),
        },
        "top1pct": {
            **cohort_summary({e: picks[e] for e in sample if e in picks}),
            "pages": pages, "population": top_n,
        },
    }
    snapshot = {
        "schema": SCHEMA, "season": season, "event": event,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "event_finished": bool(current["finished"]),
        "total_players": total_players,
        "cutoffs": {
            "top100_total": int(top100[-1]["total"]),
            "top1pct_rank": top_n, "top1pct_total": int(cutoff_row["total"]),
        },
        "cohorts": cohorts,
    }
    _write_json(path, snapshot)
    _progress("Done")
    return snapshot


# --- reading --------------------------------------------------------------------

def snapshots(root: Path = ROOT) -> list[dict]:
    """Every stored Gameweek of the newest season, oldest first."""
    seasons = sorted((root / "data" / "local" / "top_managers").glob("*-*"))
    if not seasons:
        return []
    return [json.loads(path.read_text()) for path in sorted(seasons[-1].glob("gw*.json"))]


def latest(root: Path = ROOT) -> dict | None:
    stored = snapshots(root)
    return stored[-1] if stored else None


def field_of(snapshot: dict | None, cohort: str = "top1pct") -> dict[int, dict]:
    if not snapshot:
        return {}
    return {int(pid): row for pid, row in snapshot["cohorts"][cohort]["field"].items()}


def _threshold(snapshot: dict, cohort: str) -> float | None:
    if cohort == "top100":
        return snapshot["cutoffs"]["top100_total"]
    if cohort == "top1pct":
        return snapshot["cutoffs"]["top1pct_total"]
    totals = [row["total"] for row in snapshot["cohorts"].get(cohort, {}).get("managers", [])]
    return statistics.median(totals) if totals else None


def compare(team, cohort: str, root: Path = ROOT) -> dict:
    """The user's squad against one cohort of the latest snapshot."""
    if cohort not in COHORTS:
        raise ValueError(f"Unknown cohort {cohort!r}")
    stored = snapshots(root)
    if not stored:
        return {"available": False, "cohort": cohort}
    snap = stored[-1]
    data = snap["cohorts"].get(cohort)
    if data is None:  # snapshot taken before this cohort existed
        return {"available": False, "cohort": cohort}
    field = field_of(snap, cohort)
    market = team.market.drop_duplicates("id").set_index("id")
    score = "decision_points" if "decision_points" in market else "recommended_points"

    def player(pid: int) -> dict:
        if pid not in market.index:
            return {"id": pid, "name": str(pid), "team": "", "position": ""}
        row = market.loc[pid]
        return {"id": pid, "name": str(row["name"]), "team": str(row["team"]),
                "position": str(row["position"]), "price": int(row["price"]),
                "projection": round(float(row.get(score, 0) or 0), 2)}

    mine = AnalyticsService._projected_multipliers(team)
    squad_ids = set(mine)
    size = max(1, data["size"])

    managers = []
    for row in data.get("managers", []):
        theirs = {pid: mult for pid, mult in row["picks"]}
        managers.append({
            **{k: v for k, v in row.items() if k not in {"picks", "transfers", "chips_used"}},
            "match": match_percent(mine, theirs),
            "shared": len(squad_ids & set(theirs)),
            "captain_name": player(row["captain"])["name"] if row["captain"] else None,
            "transfers": [{"out": player(o)["name"], "in": player(i)["name"]} for o, i in row["transfers"]],
            "chips_used": [c["name"] for c in row["chips_used"]],
            "fpl_url": f"https://fantasy.premierleague.com/entry/{row['entry']}/event/{snap['event']}",
        })
    managers.sort(key=lambda row: row.get("rank") or row.get("legacy_score") or 0)

    if cohort == "top1pct":
        previous = next((s for s in reversed(stored[:-1]) if s["event"] < snap["event"]), None)
        before = field_of(previous, cohort)
        delta = {pid: field.get(pid, {}).get("ownership", 0) - before.get(pid, {}).get("ownership", 0)
                 for pid in set(field) | set(before)} if previous else {}
        bought = sorted(((pid, d) for pid, d in delta.items() if d > 0), key=lambda x: -x[1])[:8]
        sold = sorted(((pid, d) for pid, d in delta.items() if d < 0), key=lambda x: x[1])[:8]
        moves_basis = f"ownership change since GW{previous['event']}" if previous else None
    else:
        ins = Counter(i for row in data["managers"] for _, i in row["transfers"])
        outs = Counter(o for row in data["managers"] for o, _ in row["transfers"])
        bought = [(pid, 100 * n / size) for pid, n in ins.most_common(8)]
        sold = [(pid, -100 * n / size) for pid, n in outs.most_common(8)]
        moves_basis = f"share of managers who made the transfer in GW{snap['event']}"

    threshold = _threshold(snap, cohort)
    yours = team.overall_points
    remaining = max(1, LAST_EVENT - snap["event"])
    decisions = AnalyticsService._decision_support(team, field, field, {})
    template = sorted(field.items(), key=lambda item: -item[1]["effective_ownership"])[:20]
    sample_size = data["size"]
    return {
        "available": True, "cohort": cohort,
        "meta": {
            "event": snap["event"], "season": snap["season"], "collected_at": snap["collected_at"],
            "event_finished": snap["event_finished"], "stale": snap["event"] < int(team.event),
            "size": sample_size, "total_players": snap["total_players"],
            "population": data.get("population", sample_size),
            "sample_pages": len(data.get("pages", [])),
            "margin_pp": round(196 * math.sqrt(0.25 / sample_size), 1) if cohort == "top1pct" and sample_size else None,
        },
        "catch_up": {
            "your_total": yours, "your_rank": team.overall_rank,
            "threshold": threshold, "cutoff_rank": snap["cutoffs"]["top1pct_rank"] if cohort == "top1pct" else 100 if cohort == "top100" else None,
            "gap": round(threshold - yours, 1) if threshold is not None and yours is not None else None,
            "per_gameweek": round((threshold - yours) / remaining, 1) if threshold is not None and yours is not None else None,
            "remaining_gameweeks": LAST_EVENT - snap["event"],
            "average_total": data["average_total"],
            "trend": [{"event": s["event"], "threshold": _threshold(s, cohort)} for s in stored],
        },
        "match": {"cohort": match_percent(mine, {pid: row["effective_ownership"] / 100 for pid, row in field.items()})},
        "moves": {
            "basis": moves_basis,
            "bought": [{**player(pid), "share": round(share, 1)} for pid, share in bought],
            "sold": [{**player(pid), "share": round(share, 1)} for pid, share in sold],
            "captains": [{**player(int(pid)), "share": share} for pid, share in list(data["captains"].items())[:5]],
            "chips": data["chips"], "average_hits": data["average_hits"],
        },
        "template": [{**player(pid), "effective_ownership": round(row["effective_ownership"], 1),
                      "ownership": round(row["ownership"], 1), "captain_rate": round(row["captain_rate"], 1),
                      "your_multiplier": mine.get(pid, 0) if pid in squad_ids else None}
                     for pid, row in template],
        "decisions": {key: decisions[key] for key in ("threats", "differentials", "leverage")},
        "managers": managers,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("collect", help="store the latest Gameweek for every cohort")
    run.add_argument("--force", action="store_true", help="retake a finished Gameweek")
    run.add_argument("--rebuild-legacy", action="store_true", help="rebuild the legacy list")
    args = parser.parse_args(argv)
    started = time.monotonic()
    snap = collect(force=args.force, rebuild_legacy=args.rebuild_legacy)
    sizes = ", ".join(f"{name} {snap['cohorts'][name]['size']}" for name in COHORTS)
    print(f"GW{snap['event']} {snap['season']}: {sizes}; top 1% cutoff "
          f"{snap['cutoffs']['top1pct_total']} pts; {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
