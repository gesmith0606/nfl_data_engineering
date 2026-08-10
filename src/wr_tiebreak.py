"""WR near-tie ordinal tie-break lever.

Lever from ``.planning/WR_ORDERING_DIAGNOSIS.md`` finding #2: WR pairs we
misorder relative to Sleeper are near-ties in OUR OWN projections (median
|our_diff| 1.21 pts vs 3.51 pts typical) while the real outcomes on those
same pairs spread just as widely as normal (median |actual_diff| 6.1 vs 5.8
typical) — these are close calls for our engine specifically, not
genuinely-unresolvable coin-flip weeks (Sleeper calls the same pairs
correctly with an equally tight projection gap). This targets the ordinal
FantasyPros-style Accuracy Gap metric (``scripts/simulate_fp_accuracy.py``),
not point MAE — the diagnosis's compression check (finding #4) ruled out
"widen the whole distribution" as the fix, so this only nudges the specific
near-tied pairs, by a small capped amount.

Signal validation (2026-08-09, BEFORE this module was written, per the
mandatory gated-experiment process — see
``knowledge-vault/concepts/gated-experiment-coverage-check.md``): joined a
fresh baseline backtest's WR swap-loss (misordered) pair population against
a trailing target-share slope built directly from Bronze
``players/weekly``'s existing ``target_share`` column (no snap-count
name-matching join needed, unlike the RB lever — ``target_share`` is already
keyed by ``player_id``). Whichever side of a pair has the higher trailing
2-week-vs-prior-2-week target-share slope predicted the actual winner
**54.8%** of the time on the 5,428 misordered pairs with both signals
present (vs 51.2% on the general pair population — confirms the signal is
specifically useful for resolving close calls, not a generally strong
predictor, consistent with a "tie-break," not a magnitude corrector). A
3-week/3-week window was weaker (53.3%) so the 2/2 window (matching
``rb_role_signals.SNAP_RECENT_N``/``SNAP_PRIOR_N``) was kept.

Mechanism
---------
Within each week's WR pool, sorted by ``projected_points`` descending, for
every ADJACENT pair whose projection gap is <= :data:`EPSILON` (~1.5 pts,
matching the diagnosis's near-tie population), if the trailing target-share
slope DISAGREES with our current order (the lower-projected player of the
pair has the higher slope), nudge the pair apart by :data:`NUDGE` points
each (<= ``EPSILON / 2``, so a single firing cannot flip a pair whose true
gap was already large, and the total points moved per pair is small enough
that MAE impact is negligible — see gate report for the measured Δ). Pairs
where the signal already agrees with our order are left untouched (no
upside to touching them, and it keeps the firing population scoped to
exactly the diagnosed misorder mechanism).

Mirrors the ``rb_tail_calibration.py`` / ``early_season_prior.py`` opt-in
compute/apply pattern: additive provenance flag, never touches non-WR rows.
"""

from typing import Optional

import numpy as np
import pandas as pd

#: WR position filter.
WR_POSITION = "WR"

#: Near-tie threshold on our OWN projected_points gap (matches the
#: diagnosis's swap-loss median |our_diff| of 1.21 pts).
EPSILON = 1.5

#: Points moved from the higher- to the lower-projected member of a
#: qualifying pair (and vice versa) when the signal disagrees with our
#: order. Capped at <= EPSILON / 2 (0.75) so MAE impact stays small.
NUDGE = 0.5

#: Trailing / prior window (weeks) for the target-share slope signal.
#: Mirrors ``rb_role_signals.SNAP_RECENT_N`` / ``SNAP_PRIOR_N`` (2/2) — the
#: validated window (2/2 hit 54.8% on the misordered population vs 53.3%
#: for 3/3).
RECENT_N = 2
PRIOR_N = 2


def compute_wr_target_share_slope(
    weekly_df: pd.DataFrame,
    season: int,
    week: int,
    recent_n: int = RECENT_N,
    prior_n: int = PRIOR_N,
) -> pd.DataFrame:
    """Leak-free trailing target-share slope per WR ``player_id``.

    For week t: ``recent`` = mean target_share over weeks [t-recent_n, t-1];
    ``prior`` = mean target_share over the ``prior_n`` weeks before that.
    Only weeks strictly before ``week`` are read, so this is leak-free by
    construction (same contract as ``rb_role_signals.compute_snap_trend_signals``).

    Args:
        weekly_df: Bronze ``players/weekly`` rows (any seasons/positions —
            filtered internally to WR rows in ``season``).
        season: NFL season.
        week: Projected week.
        recent_n: Trailing window size (default 2).
        prior_n: Prior window size (default 2).

    Returns:
        DataFrame with columns ``player_id``, ``target_share_slope``. Empty
        (with those columns) if required columns/data are missing.
    """
    empty = pd.DataFrame(columns=["player_id", "target_share_slope"])
    required = {"player_id", "season", "week", "position", "target_share"}
    if weekly_df is None or weekly_df.empty or not required.issubset(weekly_df.columns):
        return empty

    hist = weekly_df[
        (weekly_df["season"] == season)
        & (weekly_df["week"] < week)
        & (weekly_df["position"] == WR_POSITION)
    ]
    if hist.empty:
        return empty

    recent = hist[hist["week"] >= week - recent_n]
    prior = hist[
        (hist["week"] < week - recent_n)
        & (hist["week"] >= week - recent_n - prior_n)
    ]
    if recent.empty or prior.empty:
        return empty

    recent_mean = recent.groupby("player_id")["target_share"].mean()
    prior_mean = prior.groupby("player_id")["target_share"].mean()
    slope = (recent_mean - prior_mean).dropna()
    if slope.empty:
        return empty

    out = slope.rename("target_share_slope").reset_index()
    out["player_id"] = out["player_id"].astype(str)
    return out


def apply_wr_tiebreak(
    proj_df: pd.DataFrame,
    weekly_df: Optional[pd.DataFrame],
    season: int,
    week: int,
    points_col: str = "projected_points",
    epsilon: float = EPSILON,
    nudge: float = NUDGE,
) -> pd.DataFrame:
    """Nudge apart adjacent near-tied WR pairs whose trailing target-share
    slope disagrees with our projected order.

    Args:
        proj_df: Projections with ``player_id``, ``position``, ``points_col``.
        weekly_df: Bronze ``players/weekly`` rows (multi-season; already
            loaded by callers for other signals, e.g. the defensive-strength
            table — no extra I/O needed for this lever).
        season: NFL season.
        week: Projected week.
        points_col: Points column to adjust in place.
        epsilon: Near-tie threshold on the pair's own projection gap.
        nudge: Points moved between a qualifying pair's two members.

    Returns:
        ``proj_df`` with ``points_col`` updated and one new provenance
        column: ``wr_tiebreak_flag`` (bool, default False).
    """
    proj = proj_df.copy()
    proj["wr_tiebreak_flag"] = False

    if proj.empty or "position" not in proj.columns or "player_id" not in proj.columns:
        return proj

    is_wr = proj["position"] == WR_POSITION
    if is_wr.sum() < 2:
        return proj

    slope_df = compute_wr_target_share_slope(weekly_df, season, week)
    if slope_df.empty:
        return proj
    slope_lookup = slope_df.set_index("player_id")["target_share_slope"]

    wr_sorted = proj.loc[is_wr].sort_values(points_col, ascending=False)
    ids = wr_sorted["player_id"].astype(str).to_numpy()
    pts = wr_sorted[points_col].to_numpy(dtype=float)
    row_idx = wr_sorted.index.to_numpy()

    deltas = pd.Series(0.0, index=proj.index)
    fired: set = set()

    for k in range(len(wr_sorted) - 1):
        diff = pts[k] - pts[k + 1]
        if diff > epsilon:
            continue
        slope_hi = slope_lookup.get(ids[k], np.nan)
        slope_lo = slope_lookup.get(ids[k + 1], np.nan)
        if pd.isna(slope_hi) or pd.isna(slope_lo):
            continue
        if slope_lo > slope_hi:
            # Signal disagrees with our order: the lower-projected player
            # has the stronger trailing opportunity trend. Nudge apart.
            deltas.loc[row_idx[k]] -= nudge
            deltas.loc[row_idx[k + 1]] += nudge
            fired.add(row_idx[k])
            fired.add(row_idx[k + 1])

    if fired:
        fired_idx = list(fired)
        proj.loc[fired_idx, points_col] = (
            proj.loc[fired_idx, points_col] + deltas.loc[fired_idx]
        ).clip(lower=0).round(2)
        proj.loc[fired_idx, "wr_tiebreak_flag"] = True

    return proj
