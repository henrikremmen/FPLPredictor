# Own data collection and scripted dataset (phase 1)

22 October 2026. Covers phase 1 of the [improvement plan](archive/forbedringsplan_2026-10-22.md):
D1 (automatic collection), D2 (scripted dataset), D3 (data contract) and the
backfill of 2026-27. Decision: GitHub Actions in the private repository
`henrikremmen/fpl-data`; FPL-Core-Insights is used only for research/validation;
player props are not enabled.

## Result against the acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| The workflow has run green manually | Met | `workflow_dispatch` (light) on 22 October at 15:42 UTC. Bot commit `4253bba` with a snapshot where all four calls returned HTTP 200. FPL does not block Actions IPs. |
| Vaastav-compatible CSVs for GW1–7 pass D3 | Met | `fpl-data/data/2026-27/gws/gw1–7.csv` and `merged_gw.csv`, 4,551 rows. The contract runs before writing and again from the files. GW1 is identical to vaastav's `gw1.csv` in all 610 rows and every column except `xP`. |
| `build_dataset.py` gives the same result as the notebook | Met | On the notebook's input (vaastav 2016-17 to 2026-27 GW1) the file is byte-identical to the notebook's file from 21 September: SHA-256 `be3d0b74…0c56`, 254,441 rows. A unit test runs the notebook's own cells on synthetic data and compares byte for byte. |

The training table now has 2026-27 GW1–7: 258,382 rows, of which 4,551 come from
`fpl-data` (F2 resolved). It lives in `data/processed/`, not in the third-party
checkout, and is ignored by Git.

## What was built

- `src/fpl_collect.py`: collection for `fpl-data`.
  - `auto` runs every hour. It takes a light snapshot daily after 02:30 UTC and
    in the T-24h/6h/1h windows, and a full round export when a round is
    `finished` and `data_checked`.
  - State is read from the files that already exist, so runs are idempotent.
  - `capture_endpoint`/`digest`/`now` (from `capture_fpl.py`) and
    `checkpoint_for` (from `deadline_collector.py`) were moved here unchanged
    and are re-exported there. The module uses only stdlib, requests, pandas and
    `data_contract.py`.
  - Requests run sequentially 0.5 s apart, with retry/backoff and the
    User-Agent `fplmodell-snapshot/1.0`.
  - The format follows vaastav (MIT, attribution in `fpl-data/README.md` and
    `collector/LICENSE-vaastav`). Additions: `code`, `history_past.csv`,
    `corrections.csv` and raw data with SHA-256 in the manifest.
  - `xP` is FPL's `ep_next` from the last snapshot before the round's deadline.
    Values already written are kept. GW1–3 have no snapshot and are left empty.
    GW4–7 are taken from the local `data/raw/live_fpl/capture_*`.
- `src/data_contract.py`: the D3 data contract.
  - Boundary validation of `bootstrap-static`, `fixtures`, `element-summary` and
    `event/{gw}/live`.
  - Row checks: no duplicate `(element, fixture)`, no missing kickoff, player
    count in the expected range, sum of `starts` = 11 per team and match,
    goals = own goals + opponents' own goals, minutes 0–120, price 3.0–20.0 and
    at most 0.1 change per day, and rows for both teams in every finished match.
  - `diff_rows` logs FPL corrections per cell. `map_codes` fails on an ambiguous
    `code`. New players mid-season are valid.
- `src/build_dataset.py`: replaces `notebooks/build_expanded_dataset.ipynb`.
  Own seasons replace vaastav's copy of the same season and must pass D3 first.
  `src/build_features.py` now reads from `data/processed/`.
- `fpl-data`: workflow `.github/workflows/collect.yml` (cron `17 * * * *` and
  `workflow_dispatch`, `contents: write`, no secrets), copies of the two
  modules, pinned versions of pandas and requests, and a README.
- Tests:
  - `tests/test_fpl_collect.py`: every D3 rule fails on its own, a new player
    mid-season is accepted, and the price limit holds.
  - Same file: `code` mapping, correction log, daily/checkpoint scheduling,
    export and `auto` end to end with a fake API, that nothing is written when
    the contract fails, the choice of xP and that the copies in `fpl-data` match
    the sources.
  - `tests/test_build_dataset.py`: notebook equivalence and that an own season
    replaces vaastav's and must pass the contract.

## Measured size

| Part | Per unit | Per season (estimate) |
|---|---|---|
| Light snapshot (four endpoints) | about 190 kB | about 480 snapshots, about 92 MB |
| Full export, raw data (`element_summaries.tar` 2.4 MB, live, bootstrap, manifest) | about 3.0 MB | 38 exports, about 115 MB |
| CSVs | `merged_gw.csv` 0.85 MB after GW7 | Small git deltas |

The total is around 200 MB per season, which is at the plan's limit. Everything
is in git for now. If the repository gets heavy, `element_summaries.tar` can move
to Release assets per round without changing the CSV format.

Actions usage: around 1 minute per hourly run plus 10–20 minutes per weekly
export, so around 800 of 2,000 free minutes per month in a private repository.

## Verification

```
.venv/bin/python -m unittest discover -s tests   -> Ran 169 tests in 2.3s, OK
npm run build --prefix frontend                  -> ✓ built
npm run test:e2e:workspace --prefix frontend     -> 10 passed, 2 skipped (screenshot tests)
npm run typecheck:mobile                         -> exit 0
npm run test:mobile                              -> 6 suites, 19 tests passed
```

Run after phase 2, with the phase 1 code in place.

`auto` has been run twice locally against the real API. The first run took a
daily snapshot. The second run in the same hour did nothing.

## Remaining and why

- **launchd fallback:** not built. Actions reaches FPL (the first run was
  green). To be built if FPL later blocks Actions.
- **Modules that still read only `data-source/data`:** `elo_features.py` and
  `understat_*.py` still see only vaastav's 2026-27 (GW1 results only). This is
  handled in phase 4 (M1) together with the refit.
- **`player_fixture_features.csv`:** not rebuilt. It belongs to a refit
  candidate in phase 4. The production model is unchanged.
- **FPL-Core-Insights:** cross-validation of our own CSVs has not been run yet.
  Per the decision, the source is for research only.
- **Raw data from before 22 October in `fpl-data`:** exists only for the export,
  not as daily snapshots backwards. Local `capture_*` is untouched and is used as
  the xP source.
