"""M9 audit: which Stable/Upside choices change when quantiles come from a distribution.

Compares the old method (per-GW quantiles summed over the horizon and scaled by
availability) with the new one (``point_distribution``) on one capture.
Balanced must not change. Writes report.json and report.md; reads only local
files plus the public picks of one team.

    python src/quantile_audit.py --team 5139814 --output artifacts/m9_quantile_audit_20261106
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from capture_fpl import read_gzip_json
from fpl_app import apply_risk_profile, build_market, import_team, latest_forecast, optimal_lineup

ROOT = Path(__file__).resolve().parents[1]
TOP = 10


def legacy_quantiles(market: pd.DataFrame, forecast_path: Path, events: list[int]) -> pd.DataFrame:
    """The pre-M9 columns: summed per-GW quantiles times availability."""
    path = forecast_path.parent / "horizon_forecast.csv"
    rows = pd.read_csv(path if path.exists() else forecast_path)
    rows = rows[rows.GW.isin(events)] if "GW" in rows else rows
    summed = rows.groupby("player_id")[["prediction_q10", "prediction_q50", "prediction_q90"]].sum()
    old = market.copy()
    for label in (10, 50, 90):
        old[f"prediction_q{label}"] = old.id.map(summed[f"prediction_q{label}"])
        old[f"recommended_q{label}"] = old[f"prediction_q{label}"] * old.availability
    return old


def _top(frame: pd.DataFrame) -> dict[str, list[str]]:
    eligible = frame[frame.can_select & frame.planned_fixtures.gt(0)]
    return {pos: group.sort_values(["decision_points", "id"], ascending=[False, True]).name.head(TOP).tolist()
            for pos, group in eligible.groupby("position")}


def _lineup(frame: pd.DataFrame, squad_ids: list[int]) -> dict:
    lineup = optimal_lineup(frame.set_index("id").loc[squad_ids].reset_index())
    starters = lineup["starters"]
    captain = starters.sort_values(["decision_points", "id"], ascending=[False, True]).iloc[0]["name"]
    return {"formation": lineup["formation"], "xi": sorted(starters.name), "captain": captain}


def audit(root: Path, team_id: int | None, horizons=(1, 3)) -> dict:
    team = import_team(str(team_id), root) if team_id else None
    capture = None
    results = []
    for horizon in horizons:
        target = team.target_event if team else None
        forecast_path = team.forecast_path if team else latest_forecast(root, target)
        capture = forecast_path.parent
        bootstrap, fixtures = read_gzip_json(capture / "bootstrap.json.gz"), read_gzip_json(capture / "fixtures.json.gz")
        new = build_market(bootstrap, fixtures, forecast_path, target, horizon)
        old = legacy_quantiles(new, forecast_path, list(range(target, target + horizon)))
        row = {"horizon": horizon, "events": list(range(target, target + horizon))}
        for profile in ("balanced", "stable", "upside"):
            a, b = apply_risk_profile(old, profile), apply_risk_profile(new, profile)
            top_a, top_b = _top(a), _top(b)
            entry = {"top_changes": {pos: {"in": [n for n in top_b[pos] if n not in top_a[pos]],
                                           "out": [n for n in top_a[pos] if n not in top_b[pos]]}
                                     for pos in top_a},
                     "max_abs_score_change": float((a.decision_points - b.decision_points).abs().max())}
            if team is not None:
                ids = team.squad.id.astype(int).tolist()
                entry["lineup_old"], entry["lineup_new"] = _lineup(a, ids), _lineup(b, ids)
            row[profile] = entry
        row["expected_points_unchanged"] = bool((old.recommended_points == new.recommended_points).all())
        row["q90_ratio_new_over_old_median"] = float((new.recommended_q90 / old.recommended_q90).median())
        row["q90_ratio_doubtful_median"] = float((new.recommended_q90 / old.recommended_q90)[new.availability.lt(1)].median())
        results.append(row)
    return {"capture": str(capture), "team_id": team_id, "top_n": TOP, "horizons": results}


def write(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, indent=2))
    lines = [f"# M9 quantile audit", "", f"Capture `{report['capture']}`, team {report['team_id']}.", ""]
    for row in report["horizons"]:
        lines += [f"## Horizon {row['horizon']} (GW{row['events'][0]}–{row['events'][-1]})", "",
                  f"Expected points unchanged: {row['expected_points_unchanged']}. Median Q90 new/old: "
                  f"{row['q90_ratio_new_over_old_median']:.2f} (doubtful players {row['q90_ratio_doubtful_median']:.2f}).", ""]
        for profile in ("balanced", "stable", "upside"):
            entry = row[profile]
            changed = {pos: c for pos, c in entry["top_changes"].items() if c["in"]}
            lines.append(f"- **{profile}**: max score change {entry['max_abs_score_change']:.2f}; "
                         f"top-{report['top_n']} changes: {changed or 'none'}")
            if "lineup_old" in entry:
                o, n = entry["lineup_old"], entry["lineup_new"]
                same = o == n
                lines.append(f"  - lineup: {'unchanged' if same else f'{o} → {n}'}")
        lines.append("")
    (output / "report.md").write_text("\n".join(lines))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit(ROOT, args.team)
    write(report, args.output)
    print((args.output / "report.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
