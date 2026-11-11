# Deadline backtest: source audit

`05_deadline_backtest.ipynb` audits historical evidence using `src/deadline_audit.py`. It does not substitute fixture-timed data for missing deadline snapshots.

| Season | Gameweeks | Verified bootstrap snapshots | Approved deadline gameweeks |
|---|---:|---:|---:|
| 2022–23 | 38 | 38 | 0 |
| 2023–24 | 38 | 38 | 0 |
| 2024–25 | 38 | 38 | 0 |
| 2025–26 | 38 | 38 | 0 |

The result is `DATA_REPORT_ONLY`: no deadline model was trained and no deadline scores were produced. This audit does not establish that suitable archives cannot exist elsewhere.

## Sources and evidence

- [FPL-Armband backfill documentation](https://github.com/beeradb/FPL-Armband/blob/main/docs/backfill.md): Wayback bootstrap snapshots without complete fixture/history snapshots.
- [Randdalf/fplcache](https://github.com/Randdalf/fplcache): bootstrap archives.
- [TopMarx/fpl](https://github.com/TopMarx/fpl): a 2025 manifest recorded in July 2026 does not establish pre-deadline availability.
- Historical vaastav data: useful match history, but timing must be independently verified.

The audit pins source commits and verifies 152 payloads against manifests, including decompressed SHA hashes, timestamps, seasons, deadlines, events and player registries. It does not refetch every Wayback response. Bootstrap data alone cannot approve a gameweek.

Raw evidence is stored under `data/raw/deadline_audit/audit_*/`, with sidecars containing source URL, response status, download time and SHA. A current download timestamp is not evidence of historical availability. Reports include coverage flags and explicit approval status.

## Feature and evaluation contracts

`deadline_features` uses versioned registries, schedules and histories with a common UTC cutoff. Blank gameweeks and target outcomes remain separate from feature construction. `deadline_evaluation` fixes form, HGB and ensemble aggregation, player-ID captain tie-breaking and the bootstrap-defined candidate universe.

Full chronological evaluation remains deferred until qualified data exists. It requires verified fixtures, versioned player history, complete labels, adapters and timing evidence. Do not force `audit_approved` to bypass missing evidence.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_deadline.py' -v
```

Checks cover UTC cutoffs, hashes, registry changes, blanks and double gameweeks, rescheduled fixtures, transfers, unique labels, captain tie-breaking and equal candidate universes.
