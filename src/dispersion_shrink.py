"""Per-position dispersion shrinkage toward the same-week board centre.

Lever from ``.planning/SEASON_2026_MIDSEASON_RETRO.md``: through 2026 weeks
1-6 our weekly board was measurably **over-dispersed** relative to actuals
and relative to every consensus source.  Bias by our own projected-points
tier (w3-6, cons>=5 population, half-PPR) ran:

===========  ======  =========  =============
position     tier    our bias   Sleeper bias
===========  ======  =========  =============
QB           20+      **+3.55**         +0.37
WR           16-20    **+4.28**         +4.35
TE           12-16    **+4.01**         +1.34
RB           12-16    **+2.16**         +0.49
QB           <8       **-4.13**         +5.74
RB/WR/TE     <8        ~-1.2      ~-0.5
===========  ======  =========  =============

i.e. we push the top of each position too high and the bottom too low, while
the consensus tier biases stay comparatively flat.  Our within-week QB spread
was sd 3.81 vs Sleeper's 2.78.  This is a pure *calibration* defect: the
ordering information is unaffected, only the magnitudes are stretched.

Lever
-----
For each position pool on one week's board, pull every eligible row toward
that pool's own centre::

    adjusted = centre + k * (projected - centre)

with ``k`` = :data:`SHRINK_FACTOR` (0.8) and ``centre`` the mean of the
pool's *startable* rows (``projected_points >=`` :data:`MIN_CENTRE_PTS`).
No actuals, no consensus, no cross-week data — the centre comes from the
same batch being adjusted, so the lever is leak-free by construction and
runs identically in a backtest and in production.

Because the transform is affine and monotone *within* a position, it cannot
change ``position_rank`` — it improves MAE and leaves Spearman untouched.
Fixing the rank-ordering deficit is a separate problem (see the retro's QB
anchor lever).

Evidence (k fixed as a prior, replayed with this module on the published
2026 w3-6 boards, n=633, MAE against **actuals** — not against consensus)::

    baseline                       5.440   (gap vs Sleeper +0.169)
    shrink k=0.8                   5.390   (-0.050)
    QB Sleeper anchor w=0.5        5.405   (-0.035)
    both                           5.364   (-0.076, gap vs Sleeper +0.093)

Per position, the shrink moves RB 5.730 -> 5.699, WR 5.114 -> 5.088,
QB 5.908 -> 5.730 and TE 5.194 -> 5.198 (TE is the one position it does not
help, within noise at n=102).

A walk-forward pass (k fitted only on weeks < W, scored on held-out week W)
agrees with the fixed prior, so the gain is not an artefact of fitting the
weeks being scored.

The fitted-per-week ``k`` was stable (0.65 / 0.75 / 0.70 / 0.75 for weeks
3-6), so 0.8 is a conservative fixed prior rather than a tuned knob.  The
centre definition was re-validated against the production-faithful pool
(our own board only, which is all production can see): board-mean centring
gives -0.068 vs the -0.064 measured with a leakier eval-set centre, so the
lever does not depend on the study's framing.

Safety
------
Shrinkage *raises* low projections, so it must never touch a row that was
deliberately zeroed.  Eligibility therefore excludes:

- bye-week rows (``is_bye_week``) — a 0.0 bye projection shrunk toward a
  centre of ~9 would put a player who is not playing back on the board;
- any row already at or below 0 points, which covers everything
  ``apply_injury_adjustments`` zeroed out (``injury_multiplier == 0``).

``generate_projections.py`` additionally re-asserts the injury invariant
after this stage, so a sidelined player cannot survive even if a future
edit widens eligibility.

Mirrors the ``rb_tail_calibration`` / ``sleeper_consensus_anchor``
compute/apply pattern: additive provenance flag, per-position stats for the
run log, byte-identical no-op on an empty or ineligible board.

Note the deliberate overlap with ``rb_tail_calibration``'s high-band shrink
(opt-in, HOLD verdict): that lever shrinks RB 14+ rows toward the RB mean at
w=0.15.  Running both applies two shrinks to the same rows.  They are not
wired together because ``--rb-tail-calibration`` is off by default; if it is
ever shipped, reconcile the two rather than stacking them.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

#: Positions this lever adjusts.  K/DST are excluded: they are scored on a
#: different magnitude scale and were never part of the retro's measurement.
SUPPORTED_POSITIONS: Tuple[str, ...] = ("QB", "RB", "WR", "TE")

#: Shrink factor applied to each row's distance from its position centre.
#: 1.0 is a no-op; 0.8 is the shipped prior (see the module docstring's
#: walk-forward table).  Values outside (0, 1] are rejected.
SHRINK_FACTOR: float = 0.8

#: Minimum projected points for a row to contribute to its position's
#: centre.  Matches ``consensus_metrics.CONSENSUS_MIN_PTS`` so the centre is
#: the mean of the *startable* pool rather than being dragged down by the
#: deep-bench tail (whose size varies week to week with board composition).
MIN_CENTRE_PTS: float = 5.0

#: Minimum number of rows above :data:`MIN_CENTRE_PTS` required before a
#: position's centre is trusted.  Below this the position is skipped
#: (no-op) rather than shrunk toward a centre set by one or two rows.
MIN_CENTRE_ROWS: int = 5

#: Minimum projected points for a row to be ADJUSTED (as opposed to merely
#: contributing to the centre).  Equal to :data:`MIN_CENTRE_PTS`, so the
#: lever calibrates exactly the startable population the retro measured and
#: leaves the deep bench alone.
#:
#: This matters more than it looks.  Shrinkage pulls low rows UP, and the
#: sub-5 tail is the bulk of the board, so adjusting it inflates the whole
#: board: on 2026 w3-6, adjusting every positive row moved the board's total
#: projected points **+11.2%** (and on the live week-7 board, 2069 -> 2266)
#: while adjusting only the >=5 pool left the total flat (-0.0%).  The retro
#: measured nothing below 5 pts — its "<8 pts" tier means 5-8 within the
#: cons>=5 population — so inflating the bench would be an unevidenced
#: change to exactly the rows ``waiver_wire.py`` / ``stream_dst_k.py``
#: discriminate between.
#:
#: The cost is small and was measured, not assumed: the wider rule scores
#: 5.346 pooled MAE vs 5.364 for this one (the gap is 59 of 633 eval rows,
#: 9.3%, where our projection is <5 but consensus is >=5), i.e. this keeps
#: ~81% of the gain for none of the distortion.  The transform stays
#: monotone across the boundary — a row at 5.00 becomes 5 + 0.2*(centre-5),
#: still above an untouched 4.99 row — so no ordering inverts.
MIN_SHRINK_PTS: float = MIN_CENTRE_PTS

#: Interval columns translated alongside the point estimate.  The lever is a
#: per-row LOCATION correction, so the band is shifted by the same delta
#: rather than shrunk by ``k``: that keeps each interval's WIDTH — and hence
#: the conformal/quantile coverage property those bands were calibrated for
#: — intact, while preserving ``floor <= point <= ceiling``.  Narrowing them
#: by ``k`` instead would silently under-cover.
#:
#: Without this, calibrating the point alone breaks the invariant for rows
#: pulled UP toward the centre: the live week-7 board produced 21 rows with
#: ``projected_points > projected_ceiling`` (e.g. C.Sutton floor 2.83 /
#: point 7.12 / ceiling 6.29) against 0 in the levers-off control.  With
#: ``--ml`` the router attaches the band BEFORE this stage runs, so the
#: generator cannot be relied on to re-derive it afterwards.
INTERVAL_COLS: Tuple[str, ...] = ("projected_floor", "projected_ceiling")

#: Provenance column added to every returned frame.
FLAG_COL: str = "dispersion_shrink_flag"


def compute_position_centres(
    proj_df: pd.DataFrame,
    positions: Sequence[str] = SUPPORTED_POSITIONS,
    points_col: str = "projected_points",
    min_centre_pts: float = MIN_CENTRE_PTS,
    min_centre_rows: int = MIN_CENTRE_ROWS,
) -> Dict[str, float]:
    """Mean projected points of each position's startable pool.

    The centre is computed from ``proj_df`` alone — the same batch that will
    be shrunk — so it introduces no leakage and needs no external data.

    Args:
        proj_df: One week's projections with ``position`` and ``points_col``.
        positions: Positions to compute a centre for.
        points_col: Points column to average.
        min_centre_pts: Minimum points for a row to contribute to the centre.
        min_centre_rows: Minimum qualifying rows before a centre is trusted.

    Returns:
        ``{position: centre}``, omitting any position with fewer than
        ``min_centre_rows`` qualifying rows.  Empty if the input lacks the
        required columns.
    """
    if (
        proj_df is None
        or proj_df.empty
        or "position" not in proj_df.columns
        or points_col not in proj_df.columns
    ):
        return {}

    eligible = _eligible_mask(proj_df, positions, points_col)
    pool = proj_df[eligible & (proj_df[points_col] >= min_centre_pts)]
    if pool.empty:
        return {}

    centres: Dict[str, float] = {}
    for pos, grp in pool.groupby("position"):
        if len(grp) >= min_centre_rows:
            centres[str(pos)] = float(grp[points_col].mean())
    return centres


def _eligible_mask(
    proj_df: pd.DataFrame,
    positions: Sequence[str],
    points_col: str,
    min_pts: float = 0.0,
) -> pd.Series:
    """Rows this lever is allowed to touch.

    Excludes bye-week rows and anything at or below zero points, so a row
    that ``apply_injury_adjustments`` zeroed (``injury_multiplier == 0``)
    can never be shrunk back onto the board.  ``min_pts`` additionally
    restricts adjustment to the startable pool (see
    :data:`MIN_SHRINK_PTS`); it is 0.0 when computing centres, where every
    live row of the position is a candidate contributor.
    """
    mask = proj_df["position"].isin(list(positions)) & (proj_df[points_col] > 0)
    if min_pts > 0.0:
        mask = mask & (proj_df[points_col] >= min_pts)
    if "is_bye_week" in proj_df.columns:
        mask = mask & ~proj_df["is_bye_week"].fillna(False).astype(bool)
    return mask


def apply_dispersion_shrink(
    proj_df: pd.DataFrame,
    k: float = SHRINK_FACTOR,
    positions: Sequence[str] = SUPPORTED_POSITIONS,
    points_col: str = "projected_points",
    min_centre_pts: float = MIN_CENTRE_PTS,
    min_centre_rows: int = MIN_CENTRE_ROWS,
    min_shrink_pts: float = MIN_SHRINK_PTS,
    centres: Optional[Dict[str, float]] = None,
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    """Shrink each position's projections toward that position's board centre.

    Args:
        proj_df: One week's projections with ``position`` and ``points_col``.
        k: Shrink factor in (0, 1]; 1.0 is an explicit no-op.
        positions: Positions to adjust.
        points_col: Points column, adjusted in place.
        min_centre_pts: Minimum points to contribute to a position's centre.
        min_centre_rows: Minimum qualifying rows before a centre is trusted.
        min_shrink_pts: Minimum points for a row to be ADJUSTED (default
            :data:`MIN_SHRINK_PTS`); rows below it keep their projection so
            the deep bench is not inflated. Pass 0.0 to adjust every live
            row (the wider rule — see :data:`MIN_SHRINK_PTS` for the
            measured trade-off).
        centres: Pre-computed centres, for callers that need to reuse the
            exact centres of another batch.  Computed from ``proj_df`` when
            omitted (the normal path).

    Returns:
        ``(adjusted_df, stats)``.  ``adjusted_df`` is a copy with
        ``points_col`` updated and :data:`FLAG_COL` (bool, default False)
        added.  ``stats`` holds one dict per adjusted position with keys
        ``position``, ``centre``, ``k``, ``n_rows``, ``n_centre_rows``,
        ``sd_before``, ``sd_after``, ``mean_abs_change``.

    Raises:
        ValueError: If ``k`` is outside ``(0, 1]``.
    """
    if not 0.0 < k <= 1.0:
        raise ValueError(f"dispersion shrink k must be in (0, 1], got {k!r}")

    proj = proj_df.copy()
    if FLAG_COL not in proj.columns:
        proj[FLAG_COL] = False

    stats: List[Dict[str, object]] = []
    if (
        proj.empty
        or "position" not in proj.columns
        or points_col not in proj.columns
        or k == 1.0
    ):
        return proj, stats

    if centres is None:
        centres = compute_position_centres(
            proj,
            positions=positions,
            points_col=points_col,
            min_centre_pts=min_centre_pts,
            min_centre_rows=min_centre_rows,
        )
    if not centres:
        return proj, stats

    eligible = _eligible_mask(proj, positions, points_col, min_pts=min_shrink_pts)
    n_centre = (
        proj[
            _eligible_mask(proj, positions, points_col)
            & (proj[points_col] >= min_centre_pts)
        ]
        .groupby("position")
        .size()
        .to_dict()
    )

    for pos, centre in centres.items():
        mask = eligible & (proj["position"] == pos)
        if not mask.any():
            continue
        before = proj.loc[mask, points_col].astype(float)
        after = (centre + k * (before - centre)).clip(lower=0).round(2)
        proj.loc[mask, points_col] = after
        proj.loc[mask, FLAG_COL] = True

        # Translate the predictive interval by the same delta (see
        # INTERVAL_COLS) so the band keeps its width and still brackets the
        # calibrated point estimate.
        delta = after - before
        for col in INTERVAL_COLS:
            if col in proj.columns:
                shifted = proj.loc[mask, col].astype(float) + delta
                proj.loc[mask, col] = shifted.clip(lower=0).round(2)
        stats.append(
            {
                "position": pos,
                "centre": round(float(centre), 2),
                "k": float(k),
                "n_rows": int(mask.sum()),
                "n_centre_rows": int(n_centre.get(pos, 0)),
                "sd_before": round(float(before.std(ddof=0)), 2),
                "sd_after": round(float(after.std(ddof=0)), 2),
                "mean_abs_change": round(float((after - before).abs().mean()), 2),
            }
        )

    return proj, stats
