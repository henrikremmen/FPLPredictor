from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import os
import sys
import tempfile
import types
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from build_dataset import main, season_dirs
from data_contract import ContractError

NAMES = {1: "Ash", 2: "Birch", 3: "Cedar", 4: "Dale"}


def season_rows(season, with_team, fixtures):
    """Two players per club; the older season lacks the own-team column like vaastav."""
    rows = []
    for fixture, gw, home, away, hs, as_, kickoff in fixtures:
        for team, opponent, was_home in ((home, away, True), (away, home, False)):
            for k in range(2):
                row = {"name": f"{NAMES[team]} {k}", "position": "MID" if k else None,
                       "element": team * 10 + k, "fixture": fixture, "opponent_team": opponent,
                       "was_home": was_home, "kickoff_time": kickoff, "team_h_score": hs,
                       "team_a_score": as_, "minutes": 90, "total_points": 2 + k, "value": 50 + k}
                if with_team:
                    row["team"] = NAMES[team]
                    row["GW"] = gw
                else:
                    row["round"] = gw
                rows.append(row)
    return pd.DataFrame(rows)


def write_sources(data):
    old = [(1, 1, 1, 2, 2, 0, "2019-08-10T14:00:00Z"), (2, 1, 3, 4, 1, 1, "2019-08-10T16:00:00Z"),
           (3, 2, 2, 1, None, None, "2019-08-17T14:00:00Z"), (4, 2, 4, 3, 0, 3, "2019-08-17T14:00:00Z")]
    new = [(1, 1, 1, 3, 1, 0, "2020-09-12T14:00:00Z"), (2, 1, 2, 4, 2, 2, "2020-09-12T16:00:00Z"),
           (3, 2, 3, 1, 0, 1, "2020-09-19T14:00:00Z"), (4, 2, 4, 2, 1, 0, "2020-09-19T14:00:00Z"),
           (5, 2, 1, 4, 2, 1, "2020-09-22T19:00:00Z")]  # club 1 and 4 double Gameweek
    first = season_rows("2019-20", False, old)
    moved = first[first["fixture"] == 3].assign(kickoff_time="2019-08-10T12:00:00Z")  # postponed copy
    first = pd.concat([first, first.head(1), moved], ignore_index=True)
    for season, frame in (("2019-20", first), ("2020-21", season_rows("2020-21", True, new))):
        (data / season / "gws").mkdir(parents=True)
        frame.to_csv(data / season / "gws" / "merged_gw.csv", index=False)
    pd.DataFrame({"id": list(NAMES), "name": list(NAMES.values())}).to_csv(data / "2020-21" / "teams.csv", index=False)
    pd.DataFrame({"season": "2019-20", "team": list(NAMES), "team_name": list(NAMES.values())}).to_csv(
        data / "master_team_list.csv", index=False)


def run_notebook(workdir: Path) -> None:
    """Execute the original notebook's code cells in ``workdir`` (display is a no-op)."""
    notebook = json.loads((ROOT / "notebooks" / "build_expanded_dataset.ipynb").read_text())
    display = types.ModuleType("IPython.display")
    display.display = lambda *args, **kwargs: None
    modules = {"IPython": types.ModuleType("IPython"), "IPython.display": display}
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        namespace = {}
        for cell in notebook["cells"]:
            source = "".join(cell["source"])
            if cell["cell_type"] == "code" and not source.lstrip().startswith("%"):
                exec(compile(source, "build_expanded_dataset.ipynb", "exec"), namespace)
    finally:
        os.chdir(cwd)
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class BuildDatasetTest(unittest.TestCase):
    def test_script_output_is_byte_identical_to_notebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data-source" / "data"
            write_sources(data)
            with redirect_stdout(io.StringIO()):
                run_notebook(Path(tmp))
            notebook_output = (data / "cleaned_merged_seasons_team_aggregated_expanded.csv").read_bytes()
            output = Path(tmp) / "processed.csv"
            with redirect_stdout(io.StringIO()):
                main(["--vaastav-data", str(data), "--own-data", "", "--output", str(output)])
            self.assertEqual(output.read_bytes(), notebook_output)
            frame = pd.read_csv(output)
            self.assertEqual(len(frame), 36)  # duplicate and postponed copy removed
            self.assertTrue(frame["team"].notna().all())

    def test_own_season_replaces_vaastav_copy_and_must_pass_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            vaastav, own = Path(tmp) / "v", Path(tmp) / "own"
            write_sources(vaastav)
            (own / "2020-21" / "gws").mkdir(parents=True)
            (vaastav / "2020-21" / "gws" / "merged_gw.csv").rename(own / "2020-21" / "gws" / "merged_gw.csv")
            (vaastav / "2020-21" / "gws").mkdir(exist_ok=True)
            pd.DataFrame({"element": [1]}).to_csv(vaastav / "2020-21" / "gws" / "merged_gw.csv", index=False)
            self.assertEqual(season_dirs(vaastav, own)["2020-21"], own / "2020-21")
            pd.DataFrame({"id": [1], "event": [1], "team_h": [1], "team_a": [3], "finished": [True],
                          "team_h_score": [1], "team_a_score": [0]}).to_csv(own / "2020-21" / "fixtures.csv", index=False)
            with self.assertRaises(ContractError):  # synthetic season is far too small to be real
                main(["--vaastav-data", str(vaastav), "--own-data", str(own), "--output", str(Path(tmp) / "o.csv")])


if __name__ == "__main__":
    unittest.main()
