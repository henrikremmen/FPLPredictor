"""Point distributions behind the Q10/Q50/Q90 columns (plan M9, finding F16).

Expected points add up over fixtures and scale with availability. Quantiles do
neither: the quantile of a sum is not the sum of quantiles, and "unavailable
with probability 1 - a" is a mixture with a point mass at zero, not a scaling
of every outcome. Example: 10 points if available, 0 if not, a = 0.5. The mean
is 5, but Q90 is 10; scaling Q90 gives 5.

Each fixture's distribution is rebuilt from its three model quantiles as a
piecewise-linear quantile function, fixtures are sampled independently with a
fixed seed and summed, and availability is applied as a mixture. Three
quantiles do not identify a distribution, so the tails are an assumption:
below Q10 the line runs to min(Q10, 0) at p = 0, above Q90 it extends by the
Q50→Q90 distance at p = 1.

ponytail: fixtures are independent (no shared team outcomes, plan M15) and
sampled (stratified; a single fixture is reproduced to about 0.01 point, sums carry
some Monte Carlo error); move to
a joint match simulation when bench value or mini-league odds need it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

LEVELS = (10, 50, 90)
DRAWS = 1000
SEED = 20261106
_KNOT_P = np.array([0.0, 0.1, 0.5, 0.9, 1.0])


def _knots(q10, q50, q90) -> np.ndarray:
    q10, q50, q90 = (np.asarray(q, float) for q in (q10, q50, q90))
    q50 = np.maximum(q50, q10)
    q90 = np.maximum(q90, q50)
    return np.stack([np.minimum(q10, 0.0), q10, q50, q90, q90 + (q90 - q50)], axis=1)


def quantile_function(knots: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Evaluate each row's piecewise-linear quantile function at its own ``p`` (rows × k)."""
    segment = np.clip(np.searchsorted(_KNOT_P, p, side="right") - 1, 0, 3)
    rows = np.arange(len(knots))[:, None]
    low, high = knots[rows, segment], knots[rows, segment + 1]
    share = (p - _KNOT_P[segment]) / (_KNOT_P[segment + 1] - _KNOT_P[segment])
    return low + share * (high - low)


def fixture_samples(q10, q50, q90, draws: int = DRAWS, seed: int = SEED) -> np.ndarray:
    """Draws (rows × draws) from each row's piecewise-linear quantile function."""
    knots = _knots(q10, q50, q90)
    # Latin hypercube: each row's draws cover every 1/draws slice of p once, so a
    # single fixture reproduces its own quantiles; rows are permuted independently.
    rng = np.random.default_rng(seed)
    strata = rng.permuted(np.tile(np.arange(draws), (len(q10), 1)), axis=1)
    u = (strata + rng.random((len(knots), draws))) / draws
    return quantile_function(knots, u)


def sum_by_group(samples: np.ndarray, groups) -> tuple[np.ndarray, np.ndarray]:
    """Sum independent fixture draws per group; returns (group keys, group × draws)."""
    keys, inverse = np.unique(np.asarray(groups), return_inverse=True)
    totals = np.zeros((len(keys), samples.shape[1]))
    np.add.at(totals, inverse, samples)
    return keys, totals


def mixture_quantiles(totals: np.ndarray, availability, levels=LEVELS) -> np.ndarray:
    """Quantiles of "0 with probability 1 - a, else a draw from ``totals``" (rows × levels).

    Exact for the empirical draws: mass below zero is a·F(<0), zero carries the
    unavailable mass, and the rest maps back to the draws' own quantiles.
    """
    totals = np.sort(np.asarray(totals, float), axis=1)
    n = totals.shape[1]
    a = np.clip(np.asarray(availability, float), 0.0, 1.0)[:, None]
    p = np.asarray(levels, float)[None, :] / 100
    below = a * (totals < 0).sum(axis=1, keepdims=True) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        inner = np.where(p <= below, p / a, (p - (1 - a)) / a)
    index = np.clip(np.ceil(np.nan_to_num(np.clip(inner, 0, 1)) * n).astype(int) - 1, 0, n - 1)
    drawn = np.take_along_axis(totals, index, axis=1)
    zero = (p > below) & (p <= below + (1 - a))
    return np.where(zero | (a == 0), 0.0, drawn)


def player_quantiles(rows: pd.DataFrame, availability: pd.Series | None = None,
                     key: str = "player_id") -> pd.DataFrame:
    """Q10/Q50/Q90 of each player's total over ``rows`` (one row per fixture).

    Returns ``prediction_q*`` (fully available) and, when ``availability`` (indexed
    by ``key``) is given, ``recommended_q*`` with availability as a mixture.
    """
    samples = fixture_samples(rows["prediction_q10"], rows["prediction_q50"], rows["prediction_q90"])
    keys, totals = sum_by_group(samples, rows[key].to_numpy())
    result = pd.DataFrame({key: keys})
    for level, values in zip(LEVELS, mixture_quantiles(totals, np.ones(len(keys))).T):
        result[f"prediction_q{level}"] = values
    a = availability.reindex(keys).fillna(1.0).to_numpy(float) if availability is not None else np.ones(len(keys))
    mixed = mixture_quantiles(totals, a)
    # One non-negative fixture: no sum to sample, so use its quantile function exactly.
    first = rows.drop_duplicates(key).set_index(key).reindex(keys)
    single = (rows[key].value_counts().reindex(keys).to_numpy() == 1) & (first["prediction_q10"].to_numpy() >= 0)
    if single.any():
        knots = _knots(*(first[f"prediction_q{level}"].to_numpy()[single] for level in LEVELS))
        p = np.asarray(LEVELS, float)[None, :] / 100
        own = quantile_function(knots, np.repeat(p, single.sum(), axis=0))
        share = a[single, None]
        with np.errstate(divide="ignore", invalid="ignore"):
            inner = np.clip((p - (1 - share)) / share, 0, 1)
        exact = np.where((p <= 1 - share) | (share == 0), 0.0, quantile_function(knots, np.nan_to_num(inner)))
        for index, level in enumerate(LEVELS):
            result.loc[single, f"prediction_q{level}"] = own[:, index]
        mixed[single] = exact
    if availability is not None:
        for level, values in zip(LEVELS, mixed.T):
            result[f"recommended_q{level}"] = values
    return result
