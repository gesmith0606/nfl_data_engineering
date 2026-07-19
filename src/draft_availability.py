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
from typing import Dict, Optional

import numpy as np
import pandas as pd


def _norm_cdf(z: float) -> float:
    """Standard normal CDF via ``math.erf`` — scipy-free on purpose.

    The HF Spaces deployment image does not ship scipy; importing it here
    took the whole API down on 2026-07-19 (module-level import chain:
    draft router -> this module). erf is exact for our needs.
    """
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

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
    p = _norm_cdf(z)
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
    p = pd.Series(
        [_norm_cdf(v) if math.isfinite(v) else np.nan for v in z],
        index=df.index,
        dtype=float,
    )
    p = p.clip(lower=_MIN_PROB, upper=_MAX_PROB)
    p = p.where(adp.notna(), np.nan)
    return p


# "Cost of waiting" walk stops (inclusive) once a candidate is this likely to
# survive to the target pick -- lower-VORP candidates beyond it contribute a
# vanishing amount of expected value, so continuing the walk just wastes
# cycles for no meaningful precision gain.
_SURVIVAL_WALK_CAP = 0.98


def expected_best_vorp_at_pick(
    available_df: pd.DataFrame,
    pick_number: float,
    vorp_col: str = "vorp",
    adp_col: str = "adp_rank",
    stdev_col: str = "adp_stdev",
) -> Dict[str, float]:
    """Expected VORP of the best player still available at ``pick_number``,
    per position -- the "cost of waiting" signal.

    Walks each position's candidate pool in VORP-descending order and asks:
    what is the probability THIS candidate is the best one still on the
    board when the user is next on the clock? That requires the candidate
    itself to survive to ``pick_number`` *and* every higher-VORP candidate
    to already be gone::

        P(candidate i is best available) = P(i survives) * PI_{j better than i} P(j gone)
        E[position] = sum_i P(candidate i is best available) * vorp_i

    The walk stops (inclusive of the candidate that triggers it) at the
    first candidate whose survival probability is already
    >= :data:`_SURVIVAL_WALK_CAP` -- see module docstring.

    NaN-safe: players missing ``vorp_col`` or ``adp_col`` are excluded from
    the walk for that position (no ADP means no availability model to run).

    Args:
        available_df: Board's available-player pool (needs a ``position``
            column plus ``vorp_col``/``adp_col``/optionally ``stdev_col``).
        pick_number: The overall pick number to evaluate availability at.
        vorp_col: Column holding VORP.
        adp_col: Column holding each player's ADP rank.
        stdev_col: Column holding each player's ADP stdev; missing/
            non-positive values fall back per :func:`prob_gone_before`.

    Returns:
        Dict mapping position -> expected VORP of the best player still
        available at ``pick_number``. Positions with no vorp/adp-eligible
        candidates are omitted (never a fabricated 0.0).
    """
    result: Dict[str, float] = {}
    if available_df.empty or "position" not in available_df.columns:
        return result
    if vorp_col not in available_df.columns or adp_col not in available_df.columns:
        return result

    has_stdev = stdev_col in available_df.columns

    for position, group in available_df.groupby("position"):
        candidates = group.copy()
        candidates[vorp_col] = pd.to_numeric(candidates[vorp_col], errors="coerce")
        candidates[adp_col] = pd.to_numeric(candidates[adp_col], errors="coerce")
        candidates = candidates.dropna(subset=[vorp_col, adp_col])
        if candidates.empty:
            continue
        candidates = candidates.sort_values(vorp_col, ascending=False)

        expected = 0.0
        prob_all_better_gone = 1.0
        for _, row in candidates.iterrows():
            adp = float(row[adp_col])
            stdev = (
                float(row[stdev_col])
                if has_stdev and pd.notna(row.get(stdev_col))
                else None
            )
            gone_prob = prob_gone_before(pick_number, adp, stdev)
            survive_prob = 1.0 - gone_prob
            p_is_best = survive_prob * prob_all_better_gone
            expected += p_is_best * float(row[vorp_col])
            if survive_prob >= _SURVIVAL_WALK_CAP:
                break
            prob_all_better_gone *= gone_prob

        result[str(position)] = expected

    return result


__all__ = [
    "prob_gone_before",
    "prob_gone_before_vectorized",
    "expected_best_vorp_at_pick",
]
