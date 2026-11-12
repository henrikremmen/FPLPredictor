"""Copy check: whose public FPL squads in a mini-league look most like well-known YouTubers, or each other.

Similarity, not proof. Squads are public after each deadline. Every finished
Gameweek is compared with the creators in ``top_managers.CREATORS`` and with the
other league members, weighted by how rare the shared players and moves were,
and measured against a fixed random baseline of top-1M managers.

- Squad overlap: Jaccard of the 15-man squads, each player weighted by
  -ln(share of managers who owned him that round), averaged over rounds.
- Same-round buys: players both brought in the same round, each scored
  -log10(share of managers who bought him). A buy is a net squad change since
  the previous round, so wildcard re-edits count once and the return from a
  Free Hit is not a buy.
- Signal: each measure becomes a percentile against the baseline managers'
  values for the same creator and the stronger of the two counts; the member's
  best creator is then compared with the baseline managers' best creator (many
  creators and two measures would otherwise always find a match).

Run: ``python src/copy_check.py collect --entry <FPL id>`` (also part of the app's
Top managers Update). Writes ``data/local/copy_check/<season>/league_<id>.json``.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import random
import statistics
import time

from data_contract import validate_bootstrap
from fpl_app import AppError
from fpl_collect import season_of
from manager_analytics import AnalyticsService
from top_managers import (API, CREATORS, OVERALL_LEAGUE, WORKERS, CollectError, Fetcher,
                          _progress, _write_json, validate_standings)

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PAGES = 25          # x 3 managers = 75
BASELINE_PER_PAGE = 3
BASELINE_TOP_PAGE = 20_000   # overall ranks 1-1,000,000
MAX_MEMBERS = 50
STRONG, SOME = 95, 80        # signal percentiles


class _Client:
    """AnalyticsService client over the throttled Fetcher."""

    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def get(self, endpoint: str):
        try:
            return self.fetcher.get(API + endpoint)
        except CollectError as exc:
            raise AppError(str(exc)) from exc


def compact(timeline: dict, rounds: set[int]) -> dict[int, dict]:
    """Squad, chip and net buys for every finished round of one timeline."""
    out, before = {}, None
    for w in sorted(timeline["weeks"], key=lambda w: int(w["event"])):
        squad = [int(p["id"]) for p in w["picks"]]
        buys = [p for p in squad if p not in before] if before is not None else []
        if int(w["event"]) in rounds:
            out[int(w["event"])] = {"squad": squad, "chip": w["chip"], "buys": buys}
        if w["chip"] != "freehit":  # the squad after a Free Hit is compared with the one before it
            before = set(squad)
    return out


# --- measures (pure) ------------------------------------------------------------

def overlap(a: dict, b: dict, weight) -> tuple[float, dict[int, float]]:
    per = {}
    for g in sorted(set(a) & set(b)):
        mine, theirs = set(a[g]["squad"]), set(b[g]["squad"])
        union = sum(weight(g, p) for p in mine | theirs)
        per[g] = sum(weight(g, p) for p in mine & theirs) / union if union else 0.0
    return (statistics.fmean(per.values()) if per else 0.0), per


def same_buys(f: dict, c: dict) -> list[tuple[int, int]]:
    return [(g, p) for g in sorted(f) if g in c for p in f[g]["buys"] if p in c[g]["buys"]]


def follows(f: dict, c: dict) -> list[tuple[int, int]]:
    """Buys one round after the other made them (and not in the same round)."""
    return [(g, p) for g in sorted(f) if g - 1 in c
            for p in f[g]["buys"] if p in c[g - 1]["buys"] and p not in c.get(g, {}).get("buys", [])]


def same_chips(f: dict, c: dict) -> list[tuple[int, str]]:
    return [(g, f[g]["chip"]) for g in sorted(f) if f[g]["chip"] and c.get(g, {}).get("chip") == f[g]["chip"]]


def percentile(value: float, others: list[float]) -> float:
    return round(100 * sum(other < value for other in others) / len(others), 1) if others else 0.0


def combine(overlap_pct: float, buys_pct: float) -> float:
    """The stronger signal: a copied squad, or copied moves on top of an own squad."""
    return max(overlap_pct, buys_pct)


def label(score: float) -> str:
    return "Strong" if score >= STRONG else "Some" if score >= SOME else "Normal"


def build_report(league: dict, members: list[dict], creators: dict[int, str],
                 entries: dict[int, dict], baseline: list[int], weight, surprise,
                 share, player_names: dict[int, str]) -> dict:
    """Score every member against every creator and every other member."""
    base = [b for b in baseline if b in entries]
    leaders = {c: name for c, name in creators.items() if c in entries}
    present = [m for m in members if m["entry"] in entries]

    def pair(f: int, c: int) -> dict:
        ov, per = overlap(entries[f], entries[c], weight)
        buys = same_buys(entries[f], entries[c])
        return {"overlap": ov, "per_round": per, "buys": buys,
                "buy_score": sum(surprise(g, p) for g, p in buys)}

    def null(leader: int) -> list[dict]:
        return [pair(b, leader) for b in base if b != leader]

    def combined(stats: dict, against: list[dict]) -> float:
        return combine(percentile(stats["overlap"], [x["overlap"] for x in against]),
                       percentile(stats["buy_score"], [x["buy_score"] for x in against]))

    creator_null = {c: null(c) for c in leaders}
    friend_null = {m["entry"]: null(m["entry"]) for m in present}
    friend_base = {o: [combined(x, against) for x in against] for o, against in friend_null.items()}

    def alike(f: int, o: int) -> tuple[float, dict]:
        """0-100: how many baseline managers f is more alike to o than (same scale as the signal)."""
        stats = pair(f, o)
        return percentile(combined(stats, friend_null[o]), friend_base[o]), stats

    # ponytail: each baseline manager is also inside the null it is ranked against; a small
    # downward bias of its best score, leave-one-out if the baseline ever gets much smaller.
    base_best = [max((combined(pair(b, c), creator_null[c]) for c in leaders if c != b), default=0.0)
                 for b in base]

    rows = []
    for m in present:
        e = m["entry"]
        scored = [(combined(stats, creator_null[c]), c, stats)
                  for c in leaders if c != e for stats in [pair(e, c)]]
        if not scored:
            continue
        best, c, stats = max(scored, key=lambda x: (x[0], x[2]["buy_score"]))
        signal = percentile(best, base_best)
        against = creator_null[c]
        friends = [(*alike(e, o["entry"]), o) for o in present if o["entry"] != e]
        friends = [(score, o, fs) for score, fs, o in friends]
        friend = max(friends, key=lambda x: (x[0], x[2]["buy_score"]), default=None)
        rows.append({
            **m,
            "closest": {"entry": c, "name": leaders[c]},
            "signal": {"label": label(signal), "percentile": signal, "score": round(best, 1)},
            "overlap": round(stats["overlap"], 3),
            "overlap_typical": round(statistics.median(x["overlap"] for x in against), 3) if against else None,
            "overlap_percentile": percentile(stats["overlap"], [x["overlap"] for x in against]),
            "same_buys": len(stats["buys"]),
            "buys_percentile": percentile(stats["buy_score"], [x["buy_score"] for x in against]),
            "follows": len(follows(entries[e], entries[c])),
            "same_chips": [{"event": g, "chip": chip} for g, chip in same_chips(entries[e], entries[c])],
            "evidence": [{"event": g, "player": player_names.get(p, str(p)), "share": round(share(g, p), 2)}
                         for g, p in sorted(stats["buys"], key=lambda gp: -surprise(*gp))[:5]],
            "series": [{"event": g, "overlap": round(v, 3),
                        "typical": round(statistics.median(x["per_round"].get(g, 0.0) for x in against), 3)
                        if against else None}
                       for g, v in stats["per_round"].items()],
            "closest_friend": {
                "entry": friend[1]["entry"], "name": friend[1]["name"], "score": round(friend[0], 1),
                "same_buys": len(friend[2]["buys"]),
                "follows": len(follows(entries[e], entries[friend[1]["entry"]])),
            } if friend else None,
        })
    matrix = [[None if a["entry"] == b["entry"] else round(alike(a["entry"], b["entry"])[0], 1)
               for b in present] for a in present]
    return {
        "league": league, "members": rows, "baseline_size": len(base),
        "creators": [{"entry": c, "name": n} for c, n in leaders.items()],
        "friends": {"members": [{"entry": m["entry"], "name": m["name"]} for m in present],
                    "scores": matrix},
    }


# --- collection -----------------------------------------------------------------

def _baseline(fetcher: Fetcher, folder: Path, season: str) -> list[int]:
    path = folder / "baseline.json"
    if path.exists():
        return json.loads(path.read_text())["entries"]
    rng = random.Random(f"{season}-baseline")
    pages = rng.sample(range(1, BASELINE_TOP_PAGE + 1), BASELINE_PAGES)
    url = f"{API}leagues-classic/{OVERALL_LEAGUE}/standings/?page_standings={{}}"
    raw = fetcher.many([url.format(page) for page in pages])
    entries = []
    for page in pages:
        if url.format(page) in raw:
            rows = validate_standings(raw[url.format(page)], page)
            entries += [int(row["entry"]) for row in rng.sample(rows, min(BASELINE_PER_PAGE, len(rows)))]
    _write_json(path, {"season": season, "pages": pages, "entries": entries})
    return entries


def collect(root: Path = ROOT, entry: int = 0, *, fetcher: Fetcher | None = None) -> list[dict]:
    fetcher = fetcher or Fetcher()
    _progress("Copy check: reading leagues", done=0, total=0)
    bootstrap = validate_bootstrap(fetcher.get(API + "bootstrap-static/"))
    season, total = season_of(bootstrap), int(bootstrap["total_players"])
    rounds = {int(e["id"]) for e in bootstrap["events"] if e["finished"]}
    if not rounds:
        raise CollectError("No Gameweek has finished yet.")
    profile = fetcher.get(f"{API}entry/{int(entry)}/")
    leagues = [row for row in profile.get("leagues", {}).get("classic", []) if row.get("league_type") == "x"]
    standings = {int(row["id"]): validate_standings(
        fetcher.get(f"{API}leagues-classic/{int(row['id'])}/standings/"), 1)[:MAX_MEMBERS] for row in leagues}
    folder = root / "data" / "local" / "copy_check" / season
    baseline = _baseline(fetcher, folder, season)
    creators = CREATORS.get(season, {})

    everyone = sorted({int(r["entry"]) for rows in standings.values() for r in rows} | set(creators) | set(baseline))
    service = AnalyticsService(client=_Client(fetcher), ttl_seconds=3600)
    cache = root / "data" / "local" / "cache"
    _progress("Copy check: reading squads", done=0, total=len(everyone))

    def one(e: int):
        try:
            return e, compact(service.timeline(e, cache), rounds)
        except AppError:
            return e, None  # deleted or empty team
        finally:
            _progress(step=1)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        entries = {e: rows for e, rows in pool.map(one, everyone) if rows}

    players = sorted({p for rows in entries.values() for r in rows.values() for p in r["squad"] + r["buys"]})
    _progress("Copy check: reading player ownership", done=0, total=len(players))
    summaries = fetcher.many([f"{API}element-summary/{p}/" for p in players])
    selected, bought = {}, {}
    for p in players:
        for row in summaries.get(f"{API}element-summary/{p}/", {}).get("history", []):
            key = (int(row["round"]), p)  # a double Gameweek repeats the round's figures
            selected[key] = max(selected.get(key, 0), int(row["selected"]))
            bought[key] = max(bought.get(key, 0), int(row["transfers_in"]))
    fallback = {int(e["id"]): float(e.get("selected_by_percent") or 0) / 100 * total
                for e in bootstrap["elements"]}  # blank rounds have no history row

    def weight(g: int, p: int) -> float:
        return -math.log(max(selected.get((g, p)) or fallback.get(p) or 1, 1) / total)

    def surprise(g: int, p: int) -> float:
        return -math.log10(max(bought.get((g, p), 1), 1) / total)

    def share(g: int, p: int) -> float:
        return 100 * bought.get((g, p), 0) / total

    names = {int(e["id"]): e["web_name"] for e in bootstrap["elements"]}
    reports = []
    for row in leagues:
        members = [{"entry": int(r["entry"]), "name": r["player_name"], "team_name": r["entry_name"]}
                   for r in standings[int(row["id"])]]
        report = build_report({"id": int(row["id"]), "name": row["name"]}, members, creators, entries,
                              baseline, weight, surprise, share, names)
        report.update(season=season, event_through=max(rounds),
                      collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        _write_json(folder / f"league_{row['id']}.json", report)
        reports.append(report)
    _progress("Done")
    return reports


def report(root: Path, entry: int, league_id: int | None = None) -> dict:
    """The stored copy check for one of the entry's mini-leagues."""
    seasons = sorted((root / "data" / "local" / "copy_check").glob("*-*"))
    stored = [json.loads(p.read_text()) for p in sorted(seasons[-1].glob("league_*.json"))] if seasons else []
    mine = [r for r in stored if any(m["entry"] == int(entry) for m in r["friends"]["members"])]
    if not mine:
        return {"available": False}
    chosen = next((r for r in mine if r["league"]["id"] == league_id), mine[0])
    for row in chosen["members"]:
        row["is_you"] = row["entry"] == int(entry)
    return {"available": True, **chosen, "leagues": [r["league"] for r in mine]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("collect", help="score every mini-league of one FPL team")
    run.add_argument("--entry", type=int, required=True, help="your FPL team id")
    args = parser.parse_args(argv)
    started = time.monotonic()
    for rep in collect(entry=args.entry):
        flagged = [f"{m['name']} → {m['closest']['name']} ({m['signal']['label']})"
                   for m in rep["members"] if m["signal"]["label"] != "Normal"]
        print(f"{rep['league']['name']}: {len(rep['members'])} members; " + ("; ".join(flagged) or "nothing stands out"))
    print(f"{time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
