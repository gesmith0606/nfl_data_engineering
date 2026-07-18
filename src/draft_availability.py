#!/usr/bin/env python3
"""
Pick-availability probability -- "will this player still be on the board?"

Models each player's ADP as a normal distribution (mean = ADP, spread =
their ADP standard deviation) and answers: what is the probability they are
gone (drafted by someone) before a given overall pick number?

Uses real per-player ADP stdev (Lane 1's Fantasy Football Calculator data,
column name ``adp_stdev`` / ``stdev`` when present) and degrades gracefully
to a position-agnostic fallback spread when it is absent -- today's ADP data
has no stdev column, and this module must not fail or return nonsense in
that case.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

# Clamp bounds -- never report certainty either way. A player projected to
# go pick 1 overall is still not *literally* 100% gone before pick 50 (an
# owner could reach for someone else / go off the board), and a player
# projected in the 15th round is never *literally* 0% likely to sneak off
# the board early.
_MIN_PROB = 0.01
_MAX_PROB = 0.99

# Fallback sigma (in picks) when no per-player stdev is available: a flat
# multiple of ADP with a floor, so early picks (low ADP) still get a
# reasonable spread instead of an unrealistically tight one.
_FALLBACK_SIGMA_FLOOR = 3.0
_FALLBACK_SIGMA_ADP_FRACTION = 0.15

# Column names checked (in order) for a per-player ADP standard deviation
# when the caller doesn't specify one explicitly. Lane 1's ADP refresh may
# land this as ``adp_stdev`` (post-merge board column) or ``stdev`` (raw
# ADP source column) -- either is used when present.
_STDEV_COLUMN_CANDIDATES = ("adp_stdev", "stdev", "adp_std")


def _fallback_sigma(adp: float) -> float:
    return max(_FALLBACK_SIGMA_FLOOR, _FALLBACK_SIGMA_ADP_FRACTION * adp)


def prob_gone_before(
    pick_number: float, adp: float, stdev: Optional[float]
) -> float:
    """Probability a player (given ADP) is drafted before ``pick_number``.

    Args:
        pick_number: The overall pick number to evaluate availability at.
        adp:         The player's average draft position (mean of the pick
                     distribution).
        stdev:       The player's ADP standard deviation, when known (e.g.
                     from Fantasy Football Calculator). ``None`` or a
                     non-finite/non-positive value falls back to
                     ``max(3.0, 0.15 * adp)``.

    Returns:
        Probability in ``[0.01, 0.99]`` that the player is gone before
        ``pick_number``, via ``Phi((pick_number - adp) / sigma)``.
    """
    sigma = (
        stdev
        if (stdev is not None and math.isfinite(stdev) and stdev > 0)
        else _fallback_sigma(adp)
    )
    z = (pick_number - adp) / sigma
    p = float(norm.cdf(z))
    return min(_MAX_PROB, max(_MIN_PROB, p))


def _resolve_stdev_col(df: pd.DataFrame) -> Optional[str]:
    for col in _STDEV_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    return None


def prob_gone_before_vectorized(
    df: pd.DataFrame,
    pick_number: float,
    adp_col: str = "adp_rank",
    stdev_col: Optional[str] = None,
) -> pd.Series:
    """Vectorized :func:`prob_gone_before` over a DataFrame of players.

    Args:
        df:         DataFrame of players.
        pick_number: The overall pick number to evaluate availability at.
        adp_col:    Column holding each player's ADP. Rows with a missing
                    ADP get ``NaN`` (no ADP means no availability model).
        stdev_col:  Column holding each player's ADP stdev. When ``None``
                    (default), auto-detects ``adp_stdev`` / ``stdev`` /
                    ``adp_std`` if present, else uses the fallback sigma for
                    every row.

    Returns:
        A ``pd.Series`` aligned to ``df.index`` of probabilities in
        ``[0.01, 0.99]`` (``NaN`` where ADP is missing).
    """
    if df.empty or adp_col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)

    adp = pd.to_numeric(df[adp_col], errors="coerce")

    resolved_stdev_col = stdev_col if stdev_col is not None else _resolve_stdev_col(df)
    if resolved_stdev_col is not None and resolved_stdev_col in df.columns:
        stdev = pd.to_numeric(df[resolved_stdev_col], errors="coerce")
    else:
        stdev = pd.Series(np.nan, index=df.index, dtype=float)

    fallback_sigma = np.maximum(_FALLBACK_SIGMA_FLOOR, _FALLBACK_SIGMA_ADP_FRACTION * adp)
    has_stdev = stdev.notna() & (stdev > 0) & np.isfinite(stdev)
    sigma = stdev.where(has_stdev, fallback_sigma)

    z = (pick_number - adp) / sigma
    p = pd.Series(norm.cdf(z), index=df.index)
    p = p.clip(lower=_MIN_PROB, upper=_MAX_PROB)
    p = p.where(adp.notna(), np.nan)
    return p


__all__ = ["prob_gone_before", "prob_gone_before_vectorized"]
