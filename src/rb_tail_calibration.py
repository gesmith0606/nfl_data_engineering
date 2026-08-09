"""RB magnitude-tail miscalibration correction (low-end boost + high-end shrink).

Lever 2 from ``.planning/CONSENSUS_ERROR_DECOMPOSITION.md`` finding #2 (and
#4, same root cause): RB projections under 8 pts under-project actuals by
~2.3-2.6 pts while the consensus sources stay roughly unbiased there;
projections of 14+ pts over-project actuals by ~1.2-1.4 pts. Both tails are
reliable (n 400-570), both consensus sources agree on direction. The gap is
concentrated in role-volatile committee backs (Swift, Barkley, Charbonnet,
Pacheco, ...).

Investigation (2026-08-09, joining the Sleeper matched-consensus backtest
against ``rb_role_signals.compute_snap_trend_signals`` for 2022-2024)
confirmed the low-end hypothesis and rejected the naive version of the
high-end hypothesis:

- **Low band (<8 pts)**: RBs whose trailing snap share is RISING
  (``snap_share_slope > 0.15``, i.e. a role expansion the rolling-average
  projection hasn't caught up to yet) are under-projected roughly 4x worse
  than the rest of the low band (bias -2.20 vs -0.47 on the matched-Sleeper
  2022-2024 sample). This is the same underlying signal
  (``rb_role_signals.compute_snap_trend_signals``) already used in
  production for the mirror-image down correction
  (``projection_engine._apply_rb_snap_collapse``) — this module reuses it
  rather than inventing a new one.
- **High band (14+ pts)**: the same snap-share-slope split shows almost NO
  differentiating power (bias 0.92 rising vs 0.90 not-rising) — the
  over-projection here is not concentrated in a role-change subpopulation,
  it is a generic magnitude/regression-to-the-mean effect across the whole
  band. A plain shrink-toward-position-mean (no role gating) is therefore
  the fitted lever for this tail, per the task's fallback guidance ("if
  investigation shows one tail is unfixable cheaply [with the same
  mechanism as the other], do the fixable one" — here both tails are
  fixable, just via two different mechanisms).

Lever
-----
1. **Low-end boost**: for RB rows projected <8 pts AND flagged as
   snap-share-rising, blend the projection toward the player's own trailing
   2-week actual fantasy points (an "opportunity-implied" signal — his most
   recent games already embed the expanded role) at weight
   :data:`LOW_BAND_WEIGHT`. Leak-free: strictly weeks < the projected week.
2. **High-end shrink**: for RB rows projected >=14 pts, blend the
   projection toward the mean projected_points of all RB rows in the same
   week's projection batch (that week's own model output for other
   players — no actuals, no leakage) at weight :data:`HIGH_SHRINK_FACTOR`.

Mirrors the ``early_season_prior.py`` / ``qb_starter_floor.py``
compute/apply pattern: opt-in via a CLI flag, additive provenance flags,
never touches non-RB rows or RB rows inside the 8-14 band.
"""

from typing import Optional, Set

import pandas as pd

from projection_engine import _cached_rb_name_map
from rb_role_signals import compute_snap_trend_signals
from scoring_calculator import calculate_fantasy_points_df

#: RB position filter.
RB_POSITION = "RB"

#: Upper bound (exclusive) of the low magnitude band.
LOW_BAND_MAX = 8.0

#: Lower bound (inclusive) of the high magnitude band.
HIGH_BAND_MIN = 14.0

#: Trailing snap-share-slope threshold above which an RB is flagged as
#: "role rising." Mirrors ``rb_role_signals.SNAP_COLLAPSE_THRESHOLD`` (0.18)
#: for the opposite direction; 0.15 empirically gives a clean bias split
#: (rising -2.20 vs not-rising -0.47 in the low band, 2022-2024 matched
#: Sleeper sample) without shrinking the firing population too far.
RISE_THRESHOLD = 0.15

#: Trailing window (weeks) for the low-band "opportunity-implied" signal —
#: mean fantasy points over the player's last 2 games (strictly before the
#: projected week).
TRAILING_WINDOW = 2

#: Blend weight toward the trailing opportunity-implied PPG for flagged
#: low-band rows. 0.4 chosen from an empirical sweep (MAE bottoms out
#: ~0.3-0.4; bias roughly halves by 0.4 without giving back the MAE gain
#: that higher weights cost via the noisier 2-game trailing sample).
LOW_BAND_WEIGHT = 0.4

#: Blend weight toward the same-week RB position mean for high-band rows.
#: 0.15 chosen from an empirical sweep — brings the 14+ band bias close to
#: zero (1.35 -> 0.13 in the matched-Sleeper sample) while still improving
#: MAE monotonically at that weight.
HIGH_SHRINK_FACTOR = 0.15


def compute_rb_trailing_opportunity_ppg(
    weekly_df: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    window: int = TRAILING_WINDOW,
) -> pd.DataFrame:
    """Per-RB trailing fantasy PPG over the last ``window`` weeks, strictly before ``week``.

    Args:
        weekly_df: Bronze ``players/weekly`` rows (any seasons/positions —
            filtered internally to RB rows in ``season`` with
            ``week - window <= row_week < week``).
        season: NFL season.
        week: Projected week — only strictly-earlier weeks contribute, so
            this is leak-free by construction.
        scoring_format: Scoring format for the fantasy-points conversion.
        window: Number of trailing weeks to average (default 2).

    Returns:
        DataFrame with columns ``player_id``, ``trailing_opp_ppg``,
        ``trailing_opp_games``. Empty (with those columns) if the input
        lacks the required columns or has no qualifying rows.
    """
    empty = pd.DataFrame(
        columns=["player_id", "trailing_opp_ppg", "trailing_opp_games"]
    )
    required = {"player_id", "season", "week", "position"}
    if weekly_df is None or weekly_df.empty or not required.issubset(weekly_df.columns):
        return empty

    hist = weekly_df[
        (weekly_df["season"] == season)
        & (weekly_df["week"] < week)
        & (weekly_df["week"] >= week - window)
        & (weekly_df["position"] == RB_POSITION)
    ]
    if hist.empty:
        return empty

    scored = calculate_fantasy_points_df(
        hist, scoring_format=scoring_format, output_col="_trail_opp_pts"
    )
    grouped = (
        scored.groupby("player_id")["_trail_opp_pts"]
        .agg(trailing_opp_ppg="mean", trailing_opp_games="count")
        .reset_index()
    )
    return grouped


def compute_rb_rising_ids(
    snap_counts_df: Optional[pd.DataFrame],
    weekly_df: Optional[pd.DataFrame],
    season: int,
    week: int,
    threshold: float = RISE_THRESHOLD,
) -> Set[str]:
    """Return ``player_id`` values for RBs flagged as snap-share-rising for ``week``.

    Reuses ``rb_role_signals.compute_snap_trend_signals`` — the same
    leak-safe trailing-2-vs-prior-2-week snap-share computation the
    production down-correction (``projection_engine._apply_rb_snap_collapse``)
    already relies on. Lag contract mirrors that function exactly: only
    snap rows from ``week <= week`` in the target season (or any prior
    season) are passed in, and the signal itself only ever looks at weeks
    strictly before ``week``.

    Args:
        snap_counts_df: Bronze ``players/snaps`` rows (multi-season).
        weekly_df: Bronze ``players/weekly`` rows, used to map snap-count
            display names to ``player_id`` (:func:`projection_engine._cached_rb_name_map`).
        season: NFL season.
        week: Projected week.
        threshold: Slope threshold above which a player is "rising"
            (default :data:`RISE_THRESHOLD`).

    Returns:
        Set of ``player_id`` strings. Empty if snap data is unavailable.
    """
    if snap_counts_df is None or snap_counts_df.empty:
        return set()

    snaps_lagged = snap_counts_df[
        ((snap_counts_df["season"] == season) & (snap_counts_df["week"] <= week))
        | (snap_counts_df["season"] < season)
    ].copy()
    if snaps_lagged.empty:
        return set()

    pw_map = None
    if weekly_df is not None and not weekly_df.empty:
        pw_map = _cached_rb_name_map(weekly_df)

    signals = compute_snap_trend_signals(snaps_lagged, player_weekly=pw_map)
    if signals.empty or "player_id" not in signals.columns:
        return set()

    rising = signals[
        (signals["week"] == week)
        & (signals["season"] == season)
        & (signals["snap_share_slope"] > threshold)
    ]
    rising = rising.dropna(subset=["player_id"])
    return set(rising["player_id"].astype(str))


def apply_rb_tail_calibration(
    proj_df: pd.DataFrame,
    snap_counts_df: Optional[pd.DataFrame],
    weekly_df: Optional[pd.DataFrame],
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    low_weight: float = LOW_BAND_WEIGHT,
    high_shrink: float = HIGH_SHRINK_FACTOR,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Boost snap-rising low-band RBs and shrink high-band RBs toward the position mean.

    Low-band rows (``points_col < LOW_BAND_MAX``) qualify for the boost when
    the player is snap-share-rising (:func:`compute_rb_rising_ids`) AND has
    a trailing opportunity-implied PPG (:func:`compute_rb_trailing_opportunity_ppg`).
    High-band rows (``points_col >= HIGH_BAND_MIN``, evaluated AFTER the
    low-band boost so a boosted row that crosses into the high band is
    still eligible) are shrunk toward the same-week RB position mean
    unconditionally — the investigation found no role-based subpopulation
    split for this tail, only a generic magnitude effect.

    Args:
        proj_df: Projections with ``player_id``, ``position``, ``points_col``.
        snap_counts_df: Bronze ``players/snaps`` rows (multi-season).
        weekly_df: Bronze ``players/weekly`` rows.
        season: NFL season.
        week: Projected week.
        scoring_format: Scoring format for the trailing-PPG conversion.
        low_weight: Blend weight toward trailing opportunity PPG (default
            :data:`LOW_BAND_WEIGHT`).
        high_shrink: Blend weight toward the position mean (default
            :data:`HIGH_SHRINK_FACTOR`).
        points_col: Points column to adjust in place.

    Returns:
        ``proj_df`` with ``points_col`` updated and two new provenance
        columns: ``rb_tail_low_boost_flag`` / ``rb_tail_high_shrink_flag``
        (bool, both default False).
    """
    proj = proj_df.copy()
    proj["rb_tail_low_boost_flag"] = False
    proj["rb_tail_high_shrink_flag"] = False

    if proj.empty or "position" not in proj.columns or "player_id" not in proj.columns:
        return proj

    is_rb = proj["position"] == RB_POSITION
    if not is_rb.any():
        return proj

    # --- Low-band boost ---
    low_mask = is_rb & (proj[points_col] < LOW_BAND_MAX)
    if low_mask.any():
        rising_ids = compute_rb_rising_ids(snap_counts_df, weekly_df, season, week)
        if rising_ids:
            is_rising = proj["player_id"].astype(str).isin(rising_ids)
            trail_df = compute_rb_trailing_opportunity_ppg(
                weekly_df, season, week, scoring_format=scoring_format
            )
            trail_lookup = (
                trail_df.drop_duplicates("player_id")
                .assign(player_id=lambda d: d["player_id"].astype(str))
                .set_index("player_id")["trailing_opp_ppg"]
            )
            trail = proj["player_id"].astype(str).map(trail_lookup)
            boost_mask = low_mask & is_rising & trail.notna()
            if boost_mask.any():
                proj.loc[boost_mask, points_col] = (
                    (1.0 - low_weight) * proj.loc[boost_mask, points_col]
                    + low_weight * trail[boost_mask]
                ).clip(lower=0).round(2)
                proj.loc[boost_mask, "rb_tail_low_boost_flag"] = True

    # --- High-band shrink (evaluated after the boost, on the current
    # points_col, so a boosted row that crosses into the high band is
    # still eligible for the shrink pass) ---
    high_mask = is_rb & (proj[points_col] >= HIGH_BAND_MIN)
    if high_mask.any():
        pos_mean = proj.loc[is_rb, points_col].mean()
        proj.loc[high_mask, points_col] = (
            (1.0 - high_shrink) * proj.loc[high_mask, points_col]
            + high_shrink * pos_mean
        ).round(2)
        proj.loc[high_mask, "rb_tail_high_shrink_flag"] = True

    return proj
