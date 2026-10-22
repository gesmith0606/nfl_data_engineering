"""Empirically calibrated floor/ceiling bands from in-season residual quantiles.

Finding from the 2026 full-model assessment
(``.planning/MODEL_ASSESSMENT_2026_10_21.md``): the published floor/ceiling
band covered only **29.8%** of actual outcomes against its ~80% design target
(QB 60.9%, RB 32.9%, WR 24.8%, TE 20.9%, n=1,757 player-weeks over 2026 w1-6).
The band shown on the site and used by the lineup tools was close to
meaningless.

Two separate causes, both visible in the numbers:

1. **The fallback band is multiplicative and symmetric.**
   ``projection_engine._FLOOR_CEILING_MULT`` gives ``floor = pts * (1 - m)``
   and ``ceiling = pts * (1 + m)`` with m = 0.35-0.45. A 4-point TE therefore
   gets a +/-1.4 band when its real residual spread is -5.3/+6.5. Width
   collapses exactly where most of the board sits.
2. **Fantasy residuals are asymmetric.** Far more actuals fall *below* the
   floor than above the ceiling (TE 51.1% vs 28.1%, WR 45.4% vs 29.8%,
   RB 40.7% vs 26.4%) because scoring is right-skewed off a hard zero: a
   player busts to 0-2 points far more easily than a symmetric band allows.
   Only QB was roughly centred (19.0% / 20.1%).

Lever
-----
Replace the multiplicative band with per-position **linear-in-projection**
residual quantiles::

    floor   = projection + (a_lo + b_lo * projection)
    ceiling = projection + (a_hi + b_hi * projection)

Separate ``lo``/``hi`` coefficients make the band asymmetric; the linear term
makes its width grow with the projection, which the data requires: residual
spread correlates with projection size for RB/WR/TE (+0.50/+0.43/+0.45) but
not QB (+0.02), and width/projection falls from ~3.4x in the 0-4 pt tier to
~1.2x at 16+. Neither a purely additive nor a purely multiplicative band fits
that shape.

Coefficients are fitted from **completed weeks of the same season only**
(:func:`fit_band_offsets`), so the lever is leak-free and self-adapting: it
needs no pre-trained model and no historical constants, and it re-fits as the
season accumulates. Before enough weeks exist (weeks 1-2) it reports no
offsets and the caller keeps whatever band it already had.

Evidence (walk-forward: fit on weeks < W, score coverage on held-out week W,
2026, half-PPR)::

    week 3   29.0% -> 82.8%
    week 4   34.6% -> 84.1%
    week 5   30.5% -> 82.1%
    week 6   27.9% -> 83.7%
    pooled   30.6% -> 83.2%     (target ~80%)

Per position on the pooled held-out weeks: QB 85.3%, RB 80.7%, WR 84.3%,
TE 83.8%.

Safety
------
The fit is a straight line through binned quantiles, so it extrapolates
outside the projection range that supported it — for QB, whose board is almost
entirely 12+ points, the line implies a *floor above the projection* down at
5 points. :func:`apply_calibrated_bands` therefore clamps unconditionally to
``floor <= projection <= ceiling`` and ``floor >= 0``, which also preserves the
invariant the rest of the pipeline assumes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

#: Positions this lever calibrates.
SUPPORTED_POSITIONS: Tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: Lower/upper residual quantiles — a nominal 80% central interval.
LO_QUANTILE: float = 0.10
HI_QUANTILE: float = 0.90

#: Projection bins the empirical quantiles are measured in before the line is
#: fitted through them. Chosen to match the tiers the assessment measured.
PROJECTION_BINS: Tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, 16.0, 100.0)

#: Minimum rows for a position before its band is fitted at all.
MIN_POSITION_ROWS: int = 40

#: Minimum rows in a projection bin before that bin contributes a quantile
#: point to the line fit.
MIN_BIN_ROWS: int = 10

#: Provenance column added to every returned frame.
FLAG_COL: str = "band_calibration_flag"


def fit_band_offsets(
    hist_df: pd.DataFrame,
    positions: Sequence[str] = SUPPORTED_POSITIONS,
    points_col: str = "projected_points",
    actual_col: str = "actual_points",
    lo_quantile: float = LO_QUANTILE,
    hi_quantile: float = HI_QUANTILE,
    min_position_rows: int = MIN_POSITION_ROWS,
    min_bin_rows: int = MIN_BIN_ROWS,
) -> Dict[str, Tuple[float, float, float, float]]:
    """Fit per-position ``(a_lo, b_lo, a_hi, b_hi)`` residual-quantile lines.

    Call with *completed* player-weeks only — rows that have both a projection
    and a settled actual. In production that means strictly earlier weeks of
    the season being projected, which is what keeps the lever leak-free.

    Args:
        hist_df: Completed player-weeks with ``position``, ``points_col`` and
            ``actual_col``.
        positions: Positions to fit.
        points_col: Projected-points column.
        actual_col: Actual-points column.
        lo_quantile: Lower residual quantile (default 0.10).
        hi_quantile: Upper residual quantile (default 0.90).
        min_position_rows: Minimum rows before a position is fitted.
        min_bin_rows: Minimum rows before a bin contributes a quantile point.

    Returns:
        ``{position: (a_lo, b_lo, a_hi, b_hi)}``, omitting any position with
        too little history. Empty when nothing can be fitted — the caller then
        leaves its existing band untouched.
    """
    required = {"position", points_col, actual_col}
    if hist_df is None or hist_df.empty or not required.issubset(hist_df.columns):
        return {}

    live = hist_df[
        hist_df["position"].isin(list(positions))
        & hist_df[points_col].notna()
        & hist_df[actual_col].notna()
        & (hist_df[points_col] > 0)
    ].copy()
    if live.empty:
        return {}

    live["_resid"] = live[actual_col] - live[points_col]
    offsets: Dict[str, Tuple[float, float, float, float]] = {}

    for pos, grp in live.groupby("position"):
        if len(grp) < min_position_rows:
            continue
        binned = grp.assign(_tier=pd.cut(grp[points_col], list(PROJECTION_BINS)))
        xs: List[float] = []
        q_lo: List[float] = []
        q_hi: List[float] = []
        for _tier, bin_grp in binned.groupby("_tier", observed=True):
            if len(bin_grp) < min_bin_rows:
                continue
            xs.append(float(bin_grp[points_col].mean()))
            q_lo.append(float(np.percentile(bin_grp["_resid"], lo_quantile * 100)))
            q_hi.append(float(np.percentile(bin_grp["_resid"], hi_quantile * 100)))

        if len(xs) < 2:
            # Only one usable bin — fall back to a flat (additive) band, which
            # is still far better calibrated than a multiplicative one.
            offsets[str(pos)] = (
                float(np.percentile(grp["_resid"], lo_quantile * 100)),
                0.0,
                float(np.percentile(grp["_resid"], hi_quantile * 100)),
                0.0,
            )
            continue

        design = np.vstack([np.ones(len(xs)), np.asarray(xs)]).T
        (a_lo, b_lo), *_ = np.linalg.lstsq(design, np.asarray(q_lo), rcond=None)
        (a_hi, b_hi), *_ = np.linalg.lstsq(design, np.asarray(q_hi), rcond=None)
        offsets[str(pos)] = (float(a_lo), float(b_lo), float(a_hi), float(b_hi))

    return offsets


def apply_calibrated_bands(
    proj_df: pd.DataFrame,
    offsets: Dict[str, Tuple[float, float, float, float]],
    points_col: str = "projected_points",
    floor_col: str = "projected_floor",
    ceiling_col: str = "projected_ceiling",
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    """Overwrite floor/ceiling with the calibrated band for fitted positions.

    Rows whose position has no fitted offsets keep their existing band, as do
    bye-week and injury-zeroed rows (projection <= 0), which must stay at zero.

    The band is clamped to ``0 <= floor <= projection <= ceiling``. That clamp
    is load-bearing rather than cosmetic: the fitted line is only supported
    over the projection range that produced it, and QB boards are almost
    entirely 12+ points, so the QB line implies a floor *above* the projection
    for a hypothetical 5-point QB.

    Args:
        proj_df: Projections with ``position`` and ``points_col``.
        offsets: Output of :func:`fit_band_offsets`.
        points_col: Projected-points column.
        floor_col: Floor column to write.
        ceiling_col: Ceiling column to write.

    Returns:
        ``(adjusted_df, stats)``. ``stats`` holds one dict per calibrated
        position with keys ``position``, ``n_rows``, ``mean_width_before``,
        ``mean_width_after``.
    """
    proj = proj_df.copy()
    if FLAG_COL not in proj.columns:
        proj[FLAG_COL] = False

    stats: List[Dict[str, object]] = []
    if proj.empty or "position" not in proj.columns or points_col not in proj.columns:
        return proj, stats
    if not offsets:
        return proj, stats

    for col in (floor_col, ceiling_col):
        if col not in proj.columns:
            proj[col] = np.nan

    for pos, (a_lo, b_lo, a_hi, b_hi) in offsets.items():
        mask = (proj["position"] == pos) & (proj[points_col] > 0)
        if not mask.any():
            continue

        pts = proj.loc[mask, points_col].astype(float)
        width_before = float(
            (proj.loc[mask, ceiling_col] - proj.loc[mask, floor_col]).mean()
        )

        floor = pts + (a_lo + b_lo * pts)
        ceiling = pts + (a_hi + b_hi * pts)
        # Clamp: never above the point estimate, never below zero, and the
        # ceiling never below it.
        floor = floor.clip(lower=0.0).clip(upper=pts).round(2)
        ceiling = ceiling.clip(lower=pts).round(2)

        proj.loc[mask, floor_col] = floor
        proj.loc[mask, ceiling_col] = ceiling
        proj.loc[mask, FLAG_COL] = True

        stats.append(
            {
                "position": pos,
                "n_rows": int(mask.sum()),
                "mean_width_before": (
                    round(width_before, 2) if np.isfinite(width_before) else None
                ),
                "mean_width_after": round(float((ceiling - floor).mean()), 2),
            }
        )

    return proj, stats


def load_completed_player_weeks(
    season: int,
    week: int,
    data_root: str,
    scoring: str = "half_ppr",
) -> pd.DataFrame:
    """Gather this season's completed (projection, actual) pairs before ``week``.

    Joins each earlier week's published Gold board to Bronze weekly actuals.
    Strictly ``< week``, so a production call for week W can only ever see
    settled outcomes.

    Args:
        season: NFL season.
        week: Week being projected; only weeks strictly before it contribute.
        data_root: Root ``data`` directory.
        scoring: Scoring format of the boards to read.

    Returns:
        DataFrame with ``position``, ``projected_points``, ``actual_points``
        (empty when nothing has settled yet).
    """
    import glob as globmod
    import os

    from scoring_calculator import calculate_fantasy_points_df

    empty = pd.DataFrame(columns=["position", "projected_points", "actual_points"])

    weekly_dir = os.path.join(
        data_root, "bronze", "players", "weekly", f"season={season}"
    )
    weekly_files = sorted(globmod.glob(os.path.join(weekly_dir, "*.parquet")))
    if not weekly_files:
        return empty
    try:
        weekly = pd.read_parquet(weekly_files[-1])
    except Exception:
        return empty
    if weekly.empty or "week" not in weekly.columns:
        return empty

    frames: List[pd.DataFrame] = []
    for prior in range(1, int(week)):
        board_glob = os.path.join(
            data_root,
            "gold",
            "projections",
            f"season={season}",
            f"week={prior}",
            f"projections_{scoring}_*.parquet",
        )
        boards = sorted(globmod.glob(board_glob))
        if not boards:
            continue
        try:
            board = pd.read_parquet(boards[-1])
        except Exception:
            continue
        if board.empty or "player_id" not in board.columns:
            continue

        week_actuals = weekly[weekly["week"] == prior]
        if week_actuals.empty:
            continue
        scored = calculate_fantasy_points_df(
            week_actuals, scoring_format=scoring, output_col="actual_points"
        )
        scored = scored.sort_values("actual_points", ascending=False).drop_duplicates(
            "player_id"
        )

        board = board.copy()
        board["player_id"] = board["player_id"].astype(str).str.strip()
        scored = scored.copy()
        scored["player_id"] = scored["player_id"].astype(str).str.strip()

        merged = board.merge(
            scored[["player_id", "actual_points"]], on="player_id", how="inner"
        )
        if not merged.empty:
            frames.append(merged[["position", "projected_points", "actual_points"]])

    if not frames:
        return empty
    return pd.concat(frames, ignore_index=True)
