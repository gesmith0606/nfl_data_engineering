"""QB backup/spot-starter under-projection floor.

Lever 3 from ``.planning/CONSENSUS_ERROR_DECOMPOSITION.md`` finding #3: the
``<8 pts`` QB magnitude band has bias **-6.11** vs actuals (we badly
under-project it) while ESPN's comparable band is roughly balanced
(**+1.48**). The group is dominated by ~15 recurring backup/spot-start QBs
(Winston, Mullens, Browning, Rudolph, ...): when a backup is thrust into a
starting role, his own rolling-average history is still backup-level, so
the model prices him as a backup even though he is about to play a full
starter's workload.

This module raises a QB's projection to a starter-tier floor when BOTH:

  1. He is listed as the depth-chart **QB1** for the projected week
     (``data/bronze/depth_charts`` — a leak-free signal: depth-chart
     snapshots reflect the team's plan going into the week, not that
     week's outcome).
  2. His own trailing, pre-week usage is still backup-level: mean passing
     yards/game over strictly-prior current-season weeks
     (:func:`compute_qb_trailing_passing_yards`, leak-free by construction
     — the projected week is never included) is missing or below a
     backup-tier passing-yardage threshold.

Signal (2) is what keeps this from firing on every incumbent starter every
week — an established starter's own trailing passing yards stay well above
the threshold, so a bad-matchup or injury-report markdown is left alone;
only a player whose own history doesn't yet reflect a starter's workload
gets floored. Trailing passing yards is computed directly from Bronze
``players/weekly`` here (rather than reading a rolling column off the
projections DataFrame) because ``projection_engine.generate_weekly_projections``
only returns a fixed output-column whitelist — the internal
``passing_yards_std`` rolling feature does not survive to the caller — and
because computing it directly keeps this lever's behavior identical between
``generate_projections.py`` and ``backtest_projections.py``'s independently
rebuilt Silver features.

Floor value reuses ``projection_engine._STARTER_BASELINES['QB']`` — the
same conservative starter-tier stat line the rookie-fallback path already
uses — converted to fantasy points, then discounted by ``haircut`` (a first
spot start is a downside-skewed bet relative to a full-season starter-tier
expectation).

Mirrors the ``early_season_prior.py`` compute/apply pattern: opt-in via a
CLI flag, a pure floor-raise with a provenance column.
"""

import pandas as pd

from projection_engine import _ROLE_SCALE, _STARTER_BASELINES
from scoring_calculator import calculate_fantasy_points

#: Trailing (pre-week, current-season) passing yards/game below which a
#: depth-chart QB1 is still treated as running on backup-level history.
#: Reuses the projection engine's own backup-tier scale (40% of the
#: starter baseline) rather than a fresh magic number.
BACKUP_PASSING_YARDS_THRESHOLD = round(
    _STARTER_BASELINES["QB"]["passing_yards"] * _ROLE_SCALE["backup"], 1
)  # 230.0 * 0.40 = 92.0

#: Discount on the starter-tier baseline applied to get the floor — the one
#: knob. A first spot start is riskier than a full season of starter-tier
#: expectation, so the floor undershoots the raw baseline.
DEFAULT_HAIRCUT = 0.8

#: Week 1 is skipped: there are no strictly-prior current-season weeks yet,
#: so every player — including established starters — would show no
#: trailing history and read as "backup-level," making the trailing-usage
#: gate meaningless that week.
MIN_WEEK = 2

#: Position this lever applies to.
QB_STARTER_FLOOR_POSITION = "QB"


def compute_starter_tier_floor(
    scoring_format: str = "half_ppr", haircut: float = DEFAULT_HAIRCUT
) -> float:
    """Starter-tier QB floor in fantasy points.

    ``haircut * fantasy_points(_STARTER_BASELINES['QB'])`` — reuses the
    projection engine's existing 100%-role QB baseline rather than
    respecifying stat targets here.
    """
    points = calculate_fantasy_points(
        _STARTER_BASELINES["QB"], scoring_format=scoring_format
    )
    return round(points * haircut, 2)


def compute_qb_trailing_passing_yards(
    weekly_df: pd.DataFrame, season: int, week: int
) -> pd.DataFrame:
    """Per-QB trailing passing yards/game, strictly before ``week``.

    Args:
        weekly_df: Bronze ``players/weekly`` rows (any seasons/positions —
            filtered internally to QB rows in ``season`` with
            ``week < week``).
        season: NFL season.
        week: Projected week — only rows with a strictly earlier week
            contribute, so this is leak-free by construction (no shift
            bookkeeping needed since the current week is excluded outright).

    Returns:
        DataFrame with columns ``player_id``, ``trailing_passing_yards``,
        ``trailing_games``. Empty (with those columns) if the input lacks
        the required columns or has no qualifying rows.
    """
    empty = pd.DataFrame(
        columns=["player_id", "trailing_passing_yards", "trailing_games"]
    )
    required = {"player_id", "season", "week", "position", "passing_yards"}
    if weekly_df is None or weekly_df.empty or not required.issubset(weekly_df.columns):
        return empty

    hist = weekly_df[
        (weekly_df["season"] == season)
        & (weekly_df["week"] < week)
        & (weekly_df["position"] == QB_STARTER_FLOOR_POSITION)
    ]
    if hist.empty:
        return empty

    grouped = (
        hist.groupby("player_id")["passing_yards"]
        .agg(trailing_passing_yards="mean", trailing_games="count")
        .reset_index()
    )
    return grouped


def get_depth_chart_qb1_ids(depth_chart_df: pd.DataFrame, week: int) -> set:
    """Return the set of ``player_id`` (gsis_id) values listed as each
    team's depth-chart QB1 for ``week``.

    Args:
        depth_chart_df: Bronze ``depth_charts`` rows for one season (any
            weeks/game types — filtered internally to regular-season
            ``week``).
        week: NFL week being projected.

    Leak-free: depth-chart snapshots are the team's plan going into the
    week, not derived from that week's game result.
    """
    required = {"week", "position", "depth_team", "gsis_id"}
    if depth_chart_df is None or depth_chart_df.empty:
        return set()
    if not required.issubset(depth_chart_df.columns):
        return set()

    df = depth_chart_df
    if "game_type" in df.columns:
        df = df[df["game_type"] == "REG"]
    qb1 = df[
        (df["week"] == week)
        & (df["position"] == QB_STARTER_FLOOR_POSITION)
        & (df["depth_team"].astype(str) == "1")
    ]
    return set(qb1["gsis_id"].dropna().astype(str))


def apply_qb_starter_floor(
    proj_df: pd.DataFrame,
    depth_chart_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    haircut: float = DEFAULT_HAIRCUT,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Raise QB projections to a starter-tier floor for newly-designated starters.

    A row qualifies when ALL of:
      - ``position == 'QB'``
      - ``week >= MIN_WEEK``
      - listed as depth-chart QB1 for ``week``
        (:func:`get_depth_chart_qb1_ids`)
      - own trailing passing yards/game
        (:func:`compute_qb_trailing_passing_yards`) is backup-level: missing,
        or below :data:`BACKUP_PASSING_YARDS_THRESHOLD`

    ``points_col`` is raised to the floor only for qualifying rows currently
    below it — never lowered, and every other row is untouched.

    Args:
        proj_df: Projections with ``player_id``, ``position``, ``points_col``.
        depth_chart_df: Bronze ``depth_charts`` rows for ``season``.
        weekly_df: Bronze ``players/weekly`` rows covering at least
            ``season`` (any positions/seasons — filtered internally).
        season: NFL season.
        week: Projected week.
        scoring_format: Scoring format for the floor conversion.
        haircut: Discount on the starter-tier baseline (default
            :data:`DEFAULT_HAIRCUT`).
        points_col: Points column to floor in place.

    Returns:
        ``proj_df`` with ``points_col`` updated for qualifying rows and two
        new provenance columns: ``qb_starter_floor_flag`` (bool) and
        ``qb_starter_floor_value`` (float, NaN where not flagged).
    """
    proj = proj_df.copy()
    proj["qb_starter_floor_flag"] = False
    proj["qb_starter_floor_value"] = float("nan")

    if week < MIN_WEEK or proj.empty or "position" not in proj.columns:
        return proj

    qb1_ids = get_depth_chart_qb1_ids(depth_chart_df, week)
    if not qb1_ids:
        return proj

    is_qb = proj["position"] == QB_STARTER_FLOOR_POSITION
    is_qb1 = proj["player_id"].astype(str).isin(qb1_ids)

    trailing_df = compute_qb_trailing_passing_yards(weekly_df, season, week)
    trailing_lookup = (
        trailing_df.drop_duplicates("player_id")
        .assign(player_id=lambda d: d["player_id"].astype(str))
        .set_index("player_id")["trailing_passing_yards"]
    )
    trailing = proj["player_id"].astype(str).map(trailing_lookup)
    backup_level = trailing.isna() | (trailing < BACKUP_PASSING_YARDS_THRESHOLD)

    mask = is_qb & is_qb1 & backup_level
    if not mask.any():
        return proj

    floor = compute_starter_tier_floor(scoring_format=scoring_format, haircut=haircut)
    proj.loc[mask, "qb_starter_floor_flag"] = True
    proj.loc[mask, "qb_starter_floor_value"] = floor

    below_floor = mask & (proj[points_col] < floor)
    proj.loc[below_floor, points_col] = floor

    return proj
