"""Audited identity bridges: exact names plus repeated shared match evidence."""
from pathlib import Path
import re
import unicodedata

import pandas as pd

from external_context import team_key
from understat_features import identity_map


def name_key(value):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(value)).encode(
        "ascii", "ignore").decode().lower())


def match_evidence(fpl, understat):
    """Date/team matches must agree on minutes in at least three games."""
    left, right = fpl.copy(), understat.copy()
    left["day"] = pd.to_datetime(left.kickoff_time, utc=True).dt.date
    right["day"] = pd.to_datetime(right.date, utc=True).dt.date
    left["team_key"] = left.team.map(team_key)
    right["team_key"] = right.team.map(team_key)
    if left.duplicated(["day", "team_key"]).any() or right.duplicated(["day", "team_key"]).any():
        return 0, 0
    joined = left.merge(right, on=["day", "team_key"], suffixes=("_fpl", "_us"), validate="one_to_one")
    # Require positive corroboration, while tolerating small provider differences
    # in other matches. Absence disagreements or >=45-minute discrepancies are
    # identity conflicts, not evidence to smooth away.
    agree = joined.minutes.sub(joined.time).abs().le(1)
    conflict = (joined.minutes.eq(0) != joined.time.eq(0)) | joined.minutes.sub(joined.time).abs().ge(45)
    return int(agree.sum()), int(conflict.sum())


def extend_identities(root, history):
    root = Path(root)
    existing = identity_map(root)
    existing["evidence"] = "explicit_archive_mapping_via_stable_code"
    fpl = pd.read_csv(root / "data/processed/player_fixture_features.csv",
        usecols=["season", "player_id", "kickoff_time", "team", "minutes"], low_memory=False)
    history = history.copy()
    dates = pd.to_datetime(history.date, utc=True)
    year = dates.dt.year - dates.dt.month.lt(7).astype(int)
    history["season"] = year.astype(str) + "-" + ((year + 1) % 100).astype(str).str.zfill(2)
    bridges = existing[["code", "understat_id"]].drop_duplicates()
    by_code = dict(zip(bridges.code, bridges.understat_id))
    by_us = dict(zip(bridges.understat_id, bridges.code))
    audit, additions = [], []
    for season, matches in history.groupby("season"):
        raw_path = root / f"data-source/data/{season}/players_raw.csv"
        if not raw_path.exists():
            continue
        raw = pd.read_csv(raw_path)
        names = {}
        for player in raw.to_dict("records"):
            for name in [player["first_name"] + " " + player["second_name"], player["web_name"]]:
                names.setdefault(name_key(name), set()).add(int(player["id"]))
        for us_id, group in matches.groupby("understat_id"):
            candidates = set()
            for name in group.player_name.dropna().unique():
                candidates.update(names.get(name_key(name), set()))
            accepted = []
            for player_id in sorted(candidates):
                player = raw[raw.id.eq(player_id)].iloc[0]
                code = int(player.code)
                shared, conflicts = match_evidence(fpl[fpl.season.eq(season) & fpl.player_id.eq(player_id)], group)
                status = "insufficient_evidence"
                if shared >= 3 and conflicts == 0:
                    status = "validated"
                    if (code in by_code and by_code[code] != us_id) or (us_id in by_us and by_us[us_id] != code):
                        status = "identity_conflict"
                    else:
                        accepted.append((code, int(us_id)))
                audit.append(dict(season=season, player_id=player_id, code=code, understat_id=int(us_id),
                    matching_games=shared, conflicting_games=conflicts, status=status))
            if len(accepted) == 1:
                code, us_id = accepted[0]
                if code not in by_code:
                    additions.append(dict(code=code, understat_id=us_id,
                        evidence=f"exact_name_and_shared_matches:{season}"))
                    by_code[code], by_us[us_id] = us_id, code
            elif len(accepted) > 1:
                for record in audit:
                    if record["season"] == season and record["understat_id"] == int(us_id):
                        record["status"] = "ambiguous_candidates"
    if additions:
        addition_frame = pd.DataFrame(additions)
        rows = []
        for path in sorted((root / "data-source/data").glob("*/players_raw.csv")):
            raw = pd.read_csv(path, usecols=["id", "code"])
            raw["season"] = path.parent.name
            rows.append(raw.rename(columns={"id": "player_id"}).merge(addition_frame, on="code", validate="many_to_one"))
        existing = pd.concat([existing, *rows], ignore_index=True)
    if existing.duplicated(["season", "player_id"]).any() or existing.duplicated(["season", "understat_id"]).any():
        raise ValueError("Ambiguous extended identities")
    return existing, pd.DataFrame(audit)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    destination = root / "artifacts/model_research"
    history = pd.read_csv(destination / "understat_shot_history.csv")
    identities, audit = extend_identities(root, history)
    identities.to_csv(destination / "understat_identities.csv", index=False)
    audit.to_csv(destination / "understat_identity_audit.csv", index=False)
    print(identities.groupby("season").size().to_string())
    print(audit.status.value_counts().to_string())
