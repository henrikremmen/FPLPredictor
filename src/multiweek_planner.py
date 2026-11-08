"""Exact rolling 1–8 Gameweek transfer, squad, XI and captain planner."""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from fpl_app import AppError, ImportedTeam


from fpl_rules import HIT_COST, MAX_PER_CLUB, SQUAD_SHAPE as POSITION_COUNTS, START_LIMITS


CHIPS = ("bench_boost", "triple_captain", "free_hit", "wildcard")
FREE_HIT_POOL = 25


def chip_windows(team: ImportedTeam, events: list[int]) -> dict[str, set[int]]:
    """P2: Gameweeks in the horizon where each chip may be played (available, not past its expiry)."""
    windows = {}
    for chip in CHIPS:
        status = (team.chip_status or {}).get(chip) or {}
        if not status.get("available"):
            continue
        last = status.get("expires_after_gw") or 38
        windows[chip] = {event for event in events if event <= int(last)}
    return windows


def plan_multiweek(team: ImportedTeam, weeks: int | None = None,
                   discount: float = .9, max_weekly_transfers: int = 5,
                   allow_hits: bool = True, force_roll_now: bool = False,
                   terminal_ft_value: float = 1.5, chips: bool = False,
                   requirements: tuple[dict, ...] = (), banned_chips: tuple[tuple[str, int], ...] = ()) -> dict:
    """Solve transfers and free-transfer rollover jointly across the horizon.

    ``chips`` (P2) adds Bench Boost, Triple Captain, Free Hit and Wildcard as
    binary choices per Gameweek: at most one per Gameweek, each at most once,
    only while available and before its expiry (GW19 for the first set).
    ``requirements`` (P4) are hard constraints: ``{"kind": "own_by", "player_id",
    "event"}``, ``{"kind": "sell_in", "player_id", "event"}``,
    ``{"kind": "max_club", "team_id", "limit"}``, ``{"kind": "max_position",
    "position", "limit"}`` (starters). ``banned_chips`` forbids (chip, event)
    pairs; the chip calendar uses it to price the nearest alternative.
    """
    weekly = team.weekly_market
    if weekly is None:
        raise AppError("The multiple-week forecast is missing. Please update the forecast first.")
    available_events = sorted(int(value) for value in weekly.forecast_event.unique())
    weeks = int(weeks or min(8, len(available_events)))
    if not 1 <= weeks <= 8 or len(available_events) < weeks:
        raise AppError(f"The planner needs {weeks} complete Gameweeks (maximum 8).")
    events = available_events[:weeks]
    if not np.isfinite(terminal_ft_value) or terminal_ft_value < 0:
        raise AppError("Free-transfer reserve value must be finite and nonnegative.")
    frame = team.market.sort_values("id").drop_duplicates("id").reset_index(drop=True)
    ids = frame.id.astype(int).to_numpy()
    n, periods = len(frame), len(events)
    owned = set(team.squad.id.astype(int))
    initial = np.asarray([int(player_id in owned) for player_id in ids])
    prices = frame.price.astype(int).to_numpy()
    selling = team.squad.set_index("id").selling_price.astype(int).to_dict()
    sale_prices = np.asarray([
        selling.get(int(player_id), int(prices[index]))
        for index, player_id in enumerate(ids)
    ])

    # Five player vectors per period: squad, XI, captain, transfer-in, transfer-out.
    vector = n * periods
    x0, s0, c0, u0, v0 = 0, vector, 2 * vector, 3 * vector, 4 * vector
    scalar = 5 * vector
    ft0 = scalar                         # free transfers before each week, T+1
    free0 = ft0 + periods + 1           # free transfers consumed, T
    paid0 = free0 + periods             # paid transfers, T
    bank0 = paid0 + periods             # bank after transfers, T
    cap0 = bank0 + periods              # binary rollover cap, T
    hitflag0 = cap0 + periods            # binary paid-transfer max switch, T
    bench0 = hitflag0 + periods          # P1: continuous bench-slot shares, 4 slots × n × T
    chip0 = bench0 + 4 * vector          # P2: binary chip per period, CHIPS order, 4 × T
    tc0 = chip0 + 4 * periods            # triple-captain extra captain share, n × T
    fh0 = tc0 + vector                   # free-hit squad, binary n × T
    wc0 = fh0 + vector                   # wildcard transfers absorbed, T
    variables = wc0 + periods
    windows = chip_windows(team, events) if chips else {}
    banned = set(banned_chips)

    def chip_index(period, chip):
        return chip0 + period * 4 + CHIPS.index(chip)
    bench_weights = tuple(team.bench_weights or (0, 0, 0, 0))

    def slot_index(period, slot, player):
        return bench0 + (period * 4 + slot) * n + player

    def index(offset, period, player=None):
        return offset + period * n + player if player is not None else offset + period

    rows, cols, values, lower, upper = [], [], [], [], []

    def add(entries, lo=-np.inf, hi=np.inf):
        row = len(lower)
        for column, value in entries:
            if value:
                rows.append(row); cols.append(column); values.append(float(value))
        lower.append(float(lo)); upper.append(float(hi))

    for period, event in enumerate(events):
        for player, player_id in enumerate(ids):
            if player_id in team.locked_ids:
                add([(index(x0, period, player), 1)], 1, 1)
            if player_id in team.excluded_ids:
                add([(index(x0, period, player), 1)], 0, 0)
            if not bool(frame.loc[player].get("can_select", True)):
                add([(index(u0, period, player), 1)], 0, 0)
        # Squad composition and three-player club limit.
        add([(index(x0, period, player), 1) for player in range(n)], 15, 15)
        for position, count in POSITION_COUNTS.items():
            add([(index(x0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position], count, count)
        for team_id in sorted(frame.team_id.unique()):
            add([(index(x0, period, player), 1) for player in range(n)
                 if frame.loc[player, "team_id"] == team_id], hi=MAX_PER_CLUB)

        # Legal XI and one captain in the XI.
        # Bench Boost (P2): the whole squad plays, i.e. an "XI" of 15 with both keepers.
        boost = chip_index(period, "bench_boost")
        add([(index(s0, period, player), 1) for player in range(n)] + [(boost, -4)], 11, 11)
        add([(index(c0, period, player), 1) for player in range(n)], 1, 1)
        for position, (minimum, maximum) in START_LIMITS.items():
            extra = [(boost, -1)] if position == "GK" else [(boost, -(POSITION_COUNTS[position] - maximum))]
            add([(index(s0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position] + extra, hi=maximum)
            add([(index(s0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position] + ([(boost, -1)] if position == "GK" else []), lo=minimum)
        fh = chip_index(period, "free_hit")
        for player in range(n):
            # XI from the squad, or from the one-week Free Hit squad (y) when FH is played.
            add([(index(s0, period, player), 1), (index(x0, period, player), -1), (fh, -1)], hi=0)
            add([(index(s0, period, player), 1), (index(fh0, period, player), -1), (fh, 1)], hi=1)
            add([(index(fh0, period, player), 1), (fh, -1)], hi=0)
            add([(index(c0, period, player), 1),
                 (index(s0, period, player), -1)], hi=0)
            # Triple Captain: one extra captain share; Bench Boost: the squad outside the XI scores.
            add([(index(tc0, period, player), 1), (index(c0, period, player), -1)], hi=0)
        add([(index(tc0, period, player), 1) for player in range(n)] + [(chip_index(period, "triple_captain"), -1)], hi=0)
        # Free Hit squad: 15 legal players within the money of last week's squad.
        add([(index(fh0, period, player), 1) for player in range(n)] + [(fh, -15)], 0, 0)
        for position, count in POSITION_COUNTS.items():
            add([(index(fh0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position] + [(fh, -count)], 0, 0)
        for team_id in sorted(frame.team_id.unique()):
            add([(index(fh0, period, player), 1) for player in range(n)
                 if frame.loc[player, "team_id"] == team_id], hi=MAX_PER_CLUB)
        budget = [(index(fh0, period, player), prices[player]) for player in range(n)] + [(fh, 3000)]
        if period == 0:
            add(budget, hi=int(team.bank) + int(sale_prices @ initial) + 3000)
        else:
            budget += [(index(bank0, period - 1), -1)] + [(index(x0, period - 1, player), -sale_prices[player]) for player in range(n)]
            add(budget, hi=3000)
        # The main squad stands still in a Free Hit week.
        add([(index(u0, period, player), 1) for player in range(n)] + [(fh, max_weekly_transfers)],
            hi=max_weekly_transfers)
        add([(chip_index(period, chip), 1) for chip in CHIPS], hi=1)
        for player in range(n):
            # Squad transition and no buy+sell of the same player in one week.
            transition = [
                (index(x0, period, player), 1),
                (index(u0, period, player), -1),
                (index(v0, period, player), 1),
            ]
            if period == 0:
                add(transition, initial[player], initial[player])
            else:
                transition.append((index(x0, period - 1, player), -1))
                add(transition, 0, 0)
            add([(index(u0, period, player), 1),
                 (index(v0, period, player), 1)], hi=1)
            # A bench slot only for a squad player outside the XI.
            add([(slot_index(period, slot, player), 1) for slot in range(4)]
                + [(index(x0, period, player), -1), (index(s0, period, player), 1)], hi=0)
        for slot in range(4):
            add([(slot_index(period, slot, player), 1) for player in range(n)]
                + [(chip_index(period, "bench_boost"), 1), (chip_index(period, "free_hit"), 1)], hi=1)
        incoming = [(index(u0, period, player), 1) for player in range(n)]
        outgoing = [(index(v0, period, player), 1) for player in range(n)]
        add(incoming + [(column, -value) for column, value in outgoing], 0, 0)
        add(incoming + [(chip_index(period, "wildcard"), -(15 - max_weekly_transfers))], hi=max_weekly_transfers)
        if period == 0 and force_roll_now:
            add(incoming, 0, 0)

        # Exact bank evolution in £0.1m units.
        cash = [(index(bank0, period), 1)]
        if period:
            cash.append((index(bank0, period - 1), -1))
            rhs = 0
        else:
            rhs = int(team.bank)
        cash += [(index(v0, period, player), -sale_prices[player]) for player in range(n)]
        cash += [(index(u0, period, player), prices[player]) for player in range(n)]
        add(cash, rhs, rhs)

        # paid = max(0, transfers - available FT), free_used = transfers - paid.
        transfer_total = incoming
        add(transfer_total + [(index(free0, period), -1),
                              (index(paid0, period), -1), (index(wc0, period), -1)], 0, 0)
        add([(index(wc0, period), 1), (chip_index(period, "wildcard"), -15)], hi=0)
        add([(index(free0, period), 1), (index(ft0, period), -1)], hi=0)
        # The four inequalities below encode the max operator with hitflag.
        add([(index(paid0, period), -1), *transfer_total,
             (index(ft0, period), -1), (index(wc0, period), -1)], hi=0)
        add([(index(paid0, period), 1), *[(column, -value) for column, value in transfer_total],
             (index(ft0, period), 1), (index(hitflag0, period), 5)], hi=5)
        add([(index(paid0, period), 1), (index(hitflag0, period), -5)], hi=0)

        # FT_next = min(5, FT - free_used + 1).
        add([(index(ft0, period + 1), 1), (index(ft0, period), -1),
             (index(free0, period), 1)], hi=1)
        add([(index(ft0, period + 1), -1), (index(ft0, period), 1),
             (index(free0, period), -1), (index(cap0, period), -6)], hi=-1)
        add([(index(ft0, period + 1), -1),
             (index(cap0, period), 6)], hi=1)

    add([(index(ft0, 0), 1)], int(team.free_transfers), int(team.free_transfers))
    for chip in CHIPS:
        add([(chip_index(period, chip), 1) for period in range(periods)], hi=1)
    position_of = frame.position.to_numpy()
    player_of = {int(player_id): position for position, player_id in enumerate(ids)}
    for requirement in requirements:
        kind = requirement.get("kind")
        if kind in {"own_by", "sell_in"}:
            player = player_of.get(int(requirement["player_id"]))
            if player is None or int(requirement["event"]) not in events:
                raise AppError("A plan requirement names a player or Gameweek outside this plan.")
            period = events.index(int(requirement["event"]))
            if kind == "own_by":
                add([(index(x0, period, player), 1)], 1, 1)
            else:
                add([(index(v0, period, player), 1)], 1, 1)
        elif kind == "max_club":
            for period in range(periods):
                add([(index(x0, period, player), 1) for player in range(n)
                     if frame.loc[player, "team_id"] == int(requirement["team_id"])], hi=int(requirement["limit"]))
        elif kind == "max_position":
            for period in range(periods):
                add([(index(s0, period, player), 1) for player in range(n)
                     if position_of[player] == requirement["position"]], hi=int(requirement["limit"]))
        else:
            raise AppError(f"Unknown plan requirement: {kind}")

    matrix = csr_matrix((values, (rows, cols)), shape=(len(lower), variables))
    objective = np.zeros(variables)
    score_by_event = {}
    for period, event in enumerate(events):
        event_rows = weekly[weekly.forecast_event.eq(event)].set_index("id")
        score_column = "decision_points" if "decision_points" in event_rows else "recommended_points"
        scores = event_rows[score_column].reindex(ids).fillna(0).to_numpy(float)
        score_by_event[event] = scores
        weight = discount ** period
        for player in range(n):
            objective[index(s0, period, player)] = -weight * scores[player]
            objective[index(c0, period, player)] = -weight * scores[player]
            objective[index(u0, period, player)] = 1e-5
            for slot, bench_weight in enumerate(bench_weights):
                objective[slot_index(period, slot, player)] = -weight * bench_weight * scores[player]
            objective[index(tc0, period, player)] = -weight * scores[player]
        objective[index(paid0, period)] = HIT_COST * weight
    # A disclosed policy assumption, not predicted FPL points. Without a
    # terminal value the finite-horizon solver spends flexibility for pennies.
    objective[index(ft0, periods)] = -terminal_ft_value * discount ** periods

    lb, ub = np.zeros(variables), np.ones(variables)
    lb[ft0:free0], ub[ft0:free0] = 0, 5
    lb[free0:paid0], ub[free0:paid0] = 0, max_weekly_transfers
    lb[paid0:bank0], ub[paid0:bank0] = 0, max_weekly_transfers if allow_hits else 0
    lb[bank0:cap0], ub[bank0:cap0] = 0, 3000
    if not allow_hits:
        ub[hitflag0:bench0] = 0
    keeper = frame.position.eq("GK").to_numpy()
    for period in range(periods):  # slot 0 is the reserve keeper, slots 1–3 outfield
        for slot in range(4):
            start = slot_index(period, slot, 0)
            ub[start:start + n] = keeper if slot == 0 else ~keeper
    shares = {"free_hit": fh0, "triple_captain": tc0}
    # ponytail: a Free Hit squad is drawn from the 25 best per position that week; widen if a
    # cheaper enabler outside that pool ever matters.
    for period, event in enumerate(events):
        pool = np.zeros(n, bool)
        for position in POSITION_COUNTS:
            members = np.where(frame.position.to_numpy() == position)[0]
            pool[members[np.argsort(-score_by_event[event][members])[:FREE_HIT_POOL]]] = True
        ub[fh0 + period * n:fh0 + (period + 1) * n] = np.minimum(ub[fh0 + period * n:fh0 + (period + 1) * n], pool)
    for period, event in enumerate(events):
        for chip in CHIPS:
            if event not in windows.get(chip, set()) or (chip, event) in banned:
                ub[chip_index(period, chip)] = 0
                if chip in shares:  # drop the chip's player variables too, so the solver never branches on them
                    ub[shares[chip] + period * n:shares[chip] + (period + 1) * n] = 0
    ub[wc0:] = 15
    integrality = np.ones(variables, dtype=np.uint8)
    integrality[bench0:chip0] = 0  # an assignment polytope: integral once squad and XI are
    integrality[tc0:fh0] = 0       # the TC share follows the binary captain and chip choices
    result = milp(
        objective, integrality=integrality, bounds=Bounds(lb, ub),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 45, "mip_rel_gap": .005},
    )
    if result.x is None:
        raise AppError(f"Multi-week optimization failed: {result.message}")
    # HiGHS can return a feasible integer incumbent when the time limit is hit.
    # Validate it ourselves before presenting it as the best plan found, while
    # reserving global_optimum=True for a completed optimality proof.
    solution = result.x.copy()
    whole = integrality.astype(bool)  # bench, TC and BB shares are continuous
    solution[whole] = np.rint(result.x[whole])
    integral = np.max(np.abs(result.x[whole] - solution[whole])) <= 1e-5
    lhs = matrix @ solution
    feasible = bool(
        integral
        and np.all(solution >= lb - 1e-6)
        and np.all(solution <= ub + 1e-6)
        and np.all(lhs >= np.asarray(lower) - 1e-6)
        and np.all(lhs <= np.asarray(upper) + 1e-6)
    )
    if not feasible:
        raise AppError(f"The multi-week optimization provided no validated legal plan: {result.message}")
    result.x = solution
    raw_gap = getattr(result, "mip_gap", None)
    mip_gap = float(raw_gap) if raw_gap is not None and np.isfinite(raw_gap) else None
    dual_bound = getattr(result, 'mip_dual_bound', None)
    objective_upper_bound = (-float(dual_bound) if dual_bound is not None and np.isfinite(dual_bound)
                             else None)
    globally_optimal = bool(result.success and (mip_gap is None or mip_gap <= 1e-6))

    names = frame.set_index("id").name.astype(str).to_dict()
    weeks_payload, total = [], 0.0
    for period, event in enumerate(events):
        incoming_ids = ids[result.x[u0 + period*n:u0 + (period+1)*n] > .5].astype(int)
        outgoing_ids = ids[result.x[v0 + period*n:v0 + (period+1)*n] > .5].astype(int)
        starters = ids[result.x[s0 + period*n:s0 + (period+1)*n] > .5].astype(int)
        captain = ids[result.x[c0 + period*n:c0 + (period+1)*n] > .5].astype(int)
        scores = score_by_event[event]
        selected_points = float(sum(scores[np.where(ids == player)[0][0]] for player in starters))
        captain_points = float(scores[np.where(ids == captain[0])[0][0]])
        paid = int(round(result.x[index(paid0, period)]))
        chip = next((name for name in CHIPS if result.x[chip_index(period, name)] > .5), None)
        tc_points = captain_points if chip == "triple_captain" else 0.0
        projected = selected_points + captain_points + tc_points - HIT_COST * paid  # a Bench Boost XI already has 15
        squad_now = result.x[(fh0 if chip == "free_hit" else x0) + period * n:(fh0 if chip == "free_hit" else x0) + (period + 1) * n]
        bench_pool = [int(i) for i in ids[(squad_now > .5) & (result.x[s0 + period*n:s0 + (period+1)*n] < .5)]]
        bench_ids = ([int(ids[np.argmax(result.x[slot_index(period, slot, 0):slot_index(period, slot, 0) + n])])
                      for slot in range(4)] if chip not in {"bench_boost", "free_hit"} else bench_pool)
        bench_value = (0.0 if chip in {"bench_boost", "free_hit"} else
                       sum(w * float(scores[np.where(ids == player)[0][0]]) for w, player in zip(bench_weights, bench_ids)))
        positions = frame.set_index("id").position.astype(str).to_dict()
        counts = {position: sum(positions[int(player)] == position for player in starters)
                  for position in ("DEF", "MID", "FWD")}
        total += projected
        weeks_payload.append({
            "event": event,
            "squad_ids": [int(i) for i in ids[squad_now > .5]],
            "chip": chip,
            "transfers_out": [names[player] for player in outgoing_ids],
            "transfers_in": [names[player] for player in incoming_ids],
            "transfers_in_ids": incoming_ids.tolist(),
            "transfers_out_ids": outgoing_ids.tolist(),
            "free_transfers_before": int(round(result.x[index(ft0, period)])),
            "free_transfers_next_gw": int(round(result.x[index(ft0, period + 1)])),
            "paid_transfers": paid, "hit": HIT_COST * paid,
            "bank": round(float(result.x[index(bank0, period)]) / 10, 1),
            "captain": names[int(captain[0])],
            "formation": f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}",
            "starters": [names[int(player)] for player in starters],
            "starter_ids": starters.tolist(),
            "projected_points": round(projected, 2),
            "bench": [names[player] for player in bench_ids], "bench_ids": bench_ids,
            "bench_value": round(bench_value, 2),
        })
    return {
        "weeks": weeks_payload, "total_projected_points": round(total, 2),
        "discounted_objective_points": round(float(-result.fun), 2),
        "discount": discount, "global_optimum": globally_optimal,
        "allow_hits": allow_hits,
        "force_roll_now": force_roll_now,
        "terminal_ft_value": terminal_ft_value,
        "bench_weights": list(bench_weights),
        "chips_considered": sorted(windows) if chips else [],
        "requirements": list(requirements),
        "bench_note": "Bench places add weight × forecast in bench order (reserve GK, then 1–3); "
                      "projected_points is XI + captain only.",
        "free_transfers_after_horizon": int(result.x[index(ft0, periods)]),
        "solver_message": str(result.message),
        "mip_gap": mip_gap,
        "objective_upper_bound": objective_upper_bound,
        "caveat": (
            "Static prices and current injury information; recalculate before each deadline."
            if globally_optimal else
            "Best validated legal plan found within the time limit; global optimality is "
            "not proven. Prices are static, so recalculate before each deadline."
        ),
    }


def plan_with_context(team: ImportedTeam, chips: bool = False, requirements: tuple[dict, ...] = (),
                      **options) -> dict:
    """The plan plus a chip calendar (P2) and the cost of each requirement (P4).

    Chip calendar: each chip the plan plays is forbidden in that Gameweek and the
    plan is solved again; the difference is what that timing is worth, and the
    re-solve shows the nearest alternative week (or none). A requirement's cost is
    the drop in discounted plan points against the same plan without it.
    """
    plan = plan_multiweek(team, chips=chips, requirements=requirements, **options)
    calendar = []
    for week in plan["weeks"]:
        if not week.get("chip"):
            continue
        other = plan_multiweek(team, chips=chips, requirements=requirements,
                               banned_chips=((week["chip"], week["event"]),), **options)
        moved = next((w["event"] for w in other["weeks"] if w.get("chip") == week["chip"]), None)
        calendar.append({"chip": week["chip"], "event": week["event"], "alternative_event": moved,
                         "gain_over_alternative": round(plan["discounted_objective_points"]
                                                        - other["discounted_objective_points"], 2)})
    costs = []
    for number, requirement in enumerate(requirements):
        rest = tuple(r for i, r in enumerate(requirements) if i != number)
        free = plan_multiweek(team, chips=chips, requirements=rest, **options)
        costs.append({**requirement, "cost": round(free["discounted_objective_points"]
                                                   - plan["discounted_objective_points"], 2),
                      "weeks": len(plan["weeks"])})
    for week in plan["weeks"]:
        week["autosub"] = week_autosub_value(team, week)
    return {**plan, "chip_calendar": calendar, "requirement_costs": costs}


def week_autosub_value(team: ImportedTeam, week: dict, draws: int = 150) -> dict | None:
    """P3 for one planned week: the planned squad's XI forecast and its value with autosubs and VC."""
    from autosub_value import lineup_value
    from fpl_app import optimal_lineup
    if week.get("chip") in {"bench_boost", "free_hit"} or len(week["squad_ids"]) != 15:
        return None  # a Bench Boost has no bench; a Free Hit squad is not in the weekly market rows
    rows = team.weekly_market[team.weekly_market.forecast_event.eq(week["event"])]
    squad = rows[rows.id.isin(week["squad_ids"])].drop_duplicates("id")
    return lineup_value(optimal_lineup(squad), draws=draws) if len(squad) == 15 else None
