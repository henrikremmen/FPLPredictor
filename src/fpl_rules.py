"""T4: one set of FPL rules for scoring, the planner, the shadow season and backtests.

Each module that applies a rule imports it from here, and
``tests/test_fpl_rules.py`` checks the boundaries (selling price rounding,
free-transfer cap, hits, chip halves, formations). ``RULES_VERSION`` is also
written to every data manifest. The fpl-data collector keeps a copy of the
string, because it must stay standalone; a test checks that the two match.
"""

from __future__ import annotations

RULES_VERSION = "fpl-2026-27"

SQUAD_SHAPE = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
START_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
MAX_PER_CLUB = 3
BUDGET = 1000  # £100.0m in tenths
HIT_COST = 4
FREE_TRANSFER_CAP = 5
CAPTAIN_MULTIPLIER, TRIPLE_CAPTAIN_MULTIPLIER = 2, 3
CHIP_HALVES = ((1, 19), (20, 38))  # each chip once per half; the first set expires after GW19


def selling_price(purchase_price: int, current_price: int) -> int:
    """Half of any rise, rounded down to £0.1m; the full fall when the price dropped (tenths)."""
    if current_price < purchase_price:
        return current_price
    return purchase_price + (current_price - purchase_price) // 2


def hit_cost(transfers: int, free_transfers: int, chip: str | None = None) -> int:
    """Points deducted for transfers beyond the free ones; none under a Wildcard or Free Hit."""
    if chip in {"wildcard", "free_hit"}:
        return 0
    return HIT_COST * max(0, transfers - free_transfers)


def next_free_transfers(available: int, used: int, chip: str | None = None) -> int:
    """Free transfers for the next Gameweek: unused ones roll, plus one, capped at five.
    A Wildcard or Free Hit week keeps the saved transfers (none are used up)."""
    remaining = available if chip in {"wildcard", "free_hit"} else max(0, available - used)
    return min(FREE_TRANSFER_CAP, remaining + 1)


def chip_half(event: int) -> tuple[int, int]:
    """The (first, last) Gameweek of the chip set that ``event`` belongs to."""
    return CHIP_HALVES[0] if event <= CHIP_HALVES[0][1] else CHIP_HALVES[1]


def legal_formation(counts: dict[str, int], players: int = 11) -> bool:
    """A legal XI (or a 15-man Bench Boost "XI" with ``players=15``)."""
    if sum(counts.get(p, 0) for p in START_LIMITS) != players:
        return False
    if players == 15:
        return all(counts.get(p, 0) == n for p, n in SQUAD_SHAPE.items())
    return all(low <= counts.get(p, 0) <= high for p, (low, high) in START_LIMITS.items())
