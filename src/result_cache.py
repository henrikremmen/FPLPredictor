"""T3: cached optimiser results, keyed on everything that can change the answer.

Key = forecast revision (forecast, model, squad, selling prices, bank, free
transfers, horizon, risk profile, chips, market) + preferences (locks,
exclusions, bench weights) + scenario overrides + the request's own options.
A fast answer under any other key would be a wrong answer.

U10: ``warm`` computes the usual pages in a background thread after an import
or refresh, so the strategy, transfer and plan pages open with results.

ponytail: an in-process dict (oldest dropped above 64 entries); move to a job
queue with IDs when several users or workers share the API (plan T6).
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
from threading import Lock, Thread
import time

from decision_workspace import context

MAX_ENTRIES = 64


def cache_key(team, endpoint: str, **options) -> str:
    """Forecast version + team + preferences + scenarios + request options, as one hash."""
    inputs = {
        "endpoint": endpoint, "revision": context(team)["revision"],
        "locked": sorted(int(i) for i in team.locked_ids), "excluded": sorted(int(i) for i in team.excluded_ids),
        "bench_weights": list(getattr(team, "bench_weights", ()) or ()),
        "scenarios": getattr(team, "scenario_overrides", None) or {}, "options": options,
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:24]


class ResultCache:
    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._items: OrderedDict[str, dict] = OrderedDict()
        self._gates: dict[str, Lock] = {}  # one per key being computed, so a key is never computed twice at once
        self._lock = Lock()
        self._max = max_entries

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._items.get(key)
            if entry is not None:
                self._items.move_to_end(key)
            return entry

    def put(self, key: str, result) -> None:
        with self._lock:
            self._items[key] = {"result": result, "computed_at": time.time()}
            self._items.move_to_end(key)
            while len(self._items) > self._max:
                dropped, _ = self._items.popitem(last=False)
                self._gates.pop(dropped, None)

    def compute(self, key: str, work):
        """Cached result for ``key``, computing it once when missing.

        A page that asks while ``warm`` (or another request) is computing the
        same key waits for that result instead of running the solver again.
        """
        with self._lock:
            gate = self._gates.setdefault(key, Lock())
        with gate:
            hit = self.get(key)
            if hit is not None:
                return hit["result"], True
            result = work()
            self.put(key, result)
            return result, False

    def warm(self, jobs: list[tuple[str, callable]]) -> Thread:
        """Compute missing keys in the background; failures are left for the page to report."""
        def run():
            for key, work in jobs:
                try:
                    self.compute(key, work)
                except Exception:  # the page recomputes and shows the error itself
                    pass
        thread = Thread(target=run, daemon=True)
        thread.start()
        return thread
