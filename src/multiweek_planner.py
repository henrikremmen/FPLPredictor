"""Exact rolling 1–8 Gameweek transfer, squad, XI and captain planner."""

from __future__ import annotations

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from fpl_app import AppError, ImportedTeam


POSITION_COUNTS = {"GK": 2, "DEF": 5, "MID": 5, "FWD": 3}
START_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}


def plan_multiweek(team: ImportedTeam, weeks: int | None = None,
                   discount: float = .9, max_weekly_transfers: int = 5,
                   allow_hits: bool = True) -> dict:
    """Solve transfers and free-transfer rollover jointly across the horizon."""
    weekly = team.weekly_market
    if weekly is None:
        raise AppError("Flerukersprognosen mangler. Oppdater prognosen først.")
    available_events = sorted(int(value) for value in weekly.forecast_event.unique())
    weeks = int(weeks or min(8, len(available_events)))
    if not 1 <= weeks <= 8 or len(available_events) < weeks:
        raise AppError(f"Planleggeren trenger {weeks} komplette Gameweeks (maks 8).")
    events = available_events[:weeks]
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
    variables = hitflag0 + periods

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
        # Squad composition and three-player club limit.
        add([(index(x0, period, player), 1) for player in range(n)], 15, 15)
        for position, count in POSITION_COUNTS.items():
            add([(index(x0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position], count, count)
        for team_id in sorted(frame.team_id.unique()):
            add([(index(x0, period, player), 1) for player in range(n)
                 if frame.loc[player, "team_id"] == team_id], hi=3)

        # Legal XI and one captain in the XI.
        add([(index(s0, period, player), 1) for player in range(n)], 11, 11)
        add([(index(c0, period, player), 1) for player in range(n)], 1, 1)
        for position, (minimum, maximum) in START_LIMITS.items():
            add([(index(s0, period, player), 1) for player in range(n)
                 if frame.loc[player, "position"] == position], minimum, maximum)
        for player in range(n):
            add([(index(s0, period, player), 1),
                 (index(x0, period, player), -1)], hi=0)
            add([(index(c0, period, player), 1),
                 (index(s0, period, player), -1)], hi=0)

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
        incoming = [(index(u0, period, player), 1) for player in range(n)]
        outgoing = [(index(v0, period, player), 1) for player in range(n)]
        add(incoming + [(column, -value) for column, value in outgoing], 0, 0)
        add(incoming, hi=max_weekly_transfers)

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
                              (index(paid0, period), -1)], 0, 0)
        add([(index(free0, period), 1), (index(ft0, period), -1)], hi=0)
        # The four inequalities below encode the max operator with hitflag.
        add([(index(paid0, period), -1), *transfer_total,
             (index(ft0, period), -1)], hi=0)
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
        objective[index(paid0, period)] = 4 * weight

    lb, ub = np.zeros(variables), np.ones(variables)
    lb[ft0:free0], ub[ft0:free0] = 0, 5
    lb[free0:paid0], ub[free0:paid0] = 0, max_weekly_transfers
    lb[paid0:bank0], ub[paid0:bank0] = 0, max_weekly_transfers if allow_hits else 0
    lb[bank0:cap0], ub[bank0:cap0] = 0, 3000
    if not allow_hits:
        ub[hitflag0:] = 0
    integrality = np.ones(variables, dtype=np.uint8)
    result = milp(
        objective, integrality=integrality, bounds=Bounds(lb, ub),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": 45, "mip_rel_gap": .005},
    )
    if result.x is None:
        raise AppError(f"Flerukersoptimeringen feilet: {result.message}")
    # HiGHS can return a feasible integer incumbent when the time limit is hit.
    # Validate it ourselves before presenting it as the best plan found, while
    # reserving global_optimum=True for a completed optimality proof.
    solution = np.rint(result.x)
    integral = np.max(np.abs(result.x - solution)) <= 1e-5
    lhs = matrix @ solution
    feasible = bool(
        integral
        and np.all(solution >= lb - 1e-6)
        and np.all(solution <= ub + 1e-6)
        and np.all(lhs >= np.asarray(lower) - 1e-6)
        and np.all(lhs <= np.asarray(upper) + 1e-6)
    )
    if not feasible:
        raise AppError(f"Flerukersoptimeringen ga ingen validert lovlig plan: {result.message}")
    result.x = solution
    raw_gap = getattr(result, "mip_gap", None)
    mip_gap = float(raw_gap) if raw_gap is not None and np.isfinite(raw_gap) else None
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
        projected = selected_points + captain_points - 4 * paid
        positions = frame.set_index("id").position.astype(str).to_dict()
        counts = {position: sum(positions[int(player)] == position for player in starters)
                  for position in ("DEF", "MID", "FWD")}
        total += projected
        weeks_payload.append({
            "event": event,
            "transfers_out": [names[player] for player in outgoing_ids],
            "transfers_in": [names[player] for player in incoming_ids],
            "free_transfers_before": int(round(result.x[index(ft0, period)])),
            "paid_transfers": paid, "hit": 4 * paid,
            "bank": round(float(result.x[index(bank0, period)]) / 10, 1),
            "captain": names[int(captain[0])],
            "formation": f"{counts['DEF']}-{counts['MID']}-{counts['FWD']}",
            "starters": [names[int(player)] for player in starters],
            "projected_points": round(projected, 2),
        })
    return {
        "weeks": weeks_payload, "total_projected_points": round(total, 2),
        "discounted_objective_points": round(float(-result.fun), 2),
        "discount": discount, "global_optimum": globally_optimal,
        "allow_hits": allow_hits,
        "solver_message": str(result.message),
        "mip_gap": mip_gap,
        "caveat": (
            "Statiske priser og dagens skadeinformasjon; beregn planen på nytt før hver frist."
            if globally_optimal else
            "Beste validerte lovlige plan funnet innen tidsgrensen; global optimalitet er "
            "ikke bevist. Prisene er statiske, så beregn planen på nytt før hver frist."
        ),
    }
