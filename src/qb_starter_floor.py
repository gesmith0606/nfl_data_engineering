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

**v2 (2026-08-09)**: adds a second, faster-updating detection path using
``data/bronze/players/injuries`` (see ``.planning/QB_STARTER_FLOOR_GATE.md``
v1 HOLD verdict / follow-up). v1's depth-chart-QB1 signal lags real role
changes by 1-3 weeks (nflverse's official depth chart is a team submission,
often stale for a few weeks after an in-season injury), which starved the
lever to 9 qualifying QB-weeks in 3 backtested seasons. The weekly injury
report (practice-status + game-status, published pre-kickoff — leak-free,
same precedent as ``projection_engine.apply_injury_adjustments``) typically
flags an incumbent starter's absence the same week it happens.

The v2 path (:func:`get_injury_based_replacements`) flags a team-week when
the team's own trailing-usage leader among its QBs (the incumbent starter,
:func:`compute_qb_team_trailing_usage`) is listed **Out/Doubtful/IR** on
that week's injury report, then floors his replacement — the depth chart's
current QB1 for that team if it already differs from the incumbent (the
depth chart caught up), else the team's next-highest-trailing-yards QB
(:func:`get_depth_chart_qb1_by_team`). :func:`apply_qb_starter_floor`
combines v1 (depth-chart QB1) and v2 (injury-flagged incumbent) with OR —
either path qualifying is sufficient — and both still require the
replacement's own trailing usage to be backup-level
(:data:`BACKUP_PASSING_YARDS_THRESHOLD`), matching v1's rationale: this is
a role-change floor, not a general QB1 floor. Because this module's
``apply_qb_starter_floor`` signature is called from fixed sites in
``scripts/generate_projections.py`` and ``scripts/backtest_projections.py``
that were not touched for v2, the injury Bronze data is loaded internally
(:func:`load_injury_reports`) rather than threaded through as a new
required parameter — an optional ``injuries_df`` override remains available
for tests and callers that already have it in memory.
"""

import glob
import os
from functools import lru_cache
from typing import Optional

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

#: Injury-report ``report_status`` values treated as "incumbent unavailable"
#: for the v2 detection path. Matches the status vocabulary
#: ``projection_engine.INJURY_MULTIPLIERS`` already treats as a hard zero.
#: In practice the nflverse weekly injury report only ever populates
#: ``report_status`` with "Out" or "Doubtful" (IR/PUP moves are a separate
#: transaction type, not a weekly report status) — "IR"/"Injured Reserve"
#: are kept here for forward-compatibility with the task's stated intent
#: and in case a future ingestion adds them.
INJURY_OUT_STATUSES = {"Out", "Doubtful", "IR", "Injured Reserve"}


def _default_bronze_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "data", "bronze")


@lru_cache(maxsize=8)
def load_injury_reports(season: int, bronze_dir: Optional[str] = None) -> pd.DataFrame:
    """Load the latest Bronze ``players/injuries`` parquet for ``season``.

    Mirrors the depth-chart-loading pattern already used by
    ``generate_projections.py``/``backtest_projections.py`` (latest
    timestamped file per season). Kept in-module — rather than threaded
    through as a new required parameter on :func:`apply_qb_starter_floor`
    — because both existing call sites' signatures are out of scope for
    this change. Cached per ``(season, bronze_dir)`` since the backtest
    loop calls this once per week.

    Returns:
        Empty DataFrame if no matching file is found.
    """
    bronze_dir = bronze_dir or _default_bronze_dir()
    pattern = os.path.join(bronze_dir, f"players/injuries/season={season}/*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def compute_qb_team_trailing_usage(
    weekly_df: pd.DataFrame, season: int, week: int
) -> pd.DataFrame:
    """Per-QB trailing passing yards/game plus each player's most recent
    team, for ranking a team's QB depth by usage.

    Same leak-free construction as :func:`compute_qb_trailing_passing_yards`
    (strictly ``week < week`` rows only) with ``recent_team`` (the team as
    of the most recent trailing game) attached, so callers can find each
    team's trailing-usage leader (the incumbent starter).

    Returns:
        DataFrame with columns ``player_id``, ``recent_team``,
        ``trailing_passing_yards``, ``trailing_games``. Empty (with those
        columns) if the input lacks the required columns or has no
        qualifying rows.
    """
    empty = pd.DataFrame(
        columns=["player_id", "recent_team", "trailing_passing_yards", "trailing_games"]
    )
    required = {"player_id", "season", "week", "position", "passing_yards", "recent_team"}
    if weekly_df is None or weekly_df.empty or not required.issubset(weekly_df.columns):
        return empty

    hist = weekly_df[
        (weekly_df["season"] == season)
        & (weekly_df["week"] < week)
        & (weekly_df["position"] == QB_STARTER_FLOOR_POSITION)
    ].sort_values("week")
    if hist.empty:
        return empty

    grouped = (
        hist.groupby("player_id")
        .agg(
            trailing_passing_yards=("passing_yards", "mean"),
            trailing_games=("passing_yards", "count"),
            recent_team=("recent_team", "last"),
        )
        .reset_index()
    )
    return grouped


def get_depth_chart_qb1_by_team(depth_chart_df: pd.DataFrame, week: int) -> dict:
    """Team (``club_code``) -> depth-chart QB1 ``gsis_id`` for ``week``.

    Per-team companion to :func:`get_depth_chart_qb1_ids` — used by the v2
    injury-based path to find the depth chart's current pick for a
    specific team (which may already reflect a caught-up role change) so
    it can prefer that over the fallback trailing-usage backup. Same
    leak-free construction (a snapshot for ``week`` is the team's plan
    going into ``week``, not derived from that week's result).
    """
    required = {"week", "position", "depth_team", "gsis_id", "club_code"}
    if depth_chart_df is None or depth_chart_df.empty:
        return {}
    if not required.issubset(depth_chart_df.columns):
        return {}

    df = depth_chart_df
    if "game_type" in df.columns:
        df = df[df["game_type"] == "REG"]
    qb1 = df[
        (df["week"] == week)
        & (df["position"] == QB_STARTER_FLOOR_POSITION)
        & (df["depth_team"].astype(str) == "1")
    ].dropna(subset=["gsis_id"])
    return dict(zip(qb1["club_code"].astype(str), qb1["gsis_id"].astype(str)))


def get_injury_based_replacements(
    depth_chart_df: pd.DataFrame,
    injuries_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    season: int,
    week: int,
) -> set:
    """Team-level replacement QB ids for teams whose trailing-usage
    incumbent is Out/Doubtful/IR on the (season, week) injury report.

    For each team with a QB flagged on the injury report
    (:data:`INJURY_OUT_STATUSES`): if that flagged player is also the
    team's trailing-usage leader (:func:`compute_qb_team_trailing_usage` —
    i.e. he's the incumbent starter, not e.g. an already-buried QB3), the
    replacement is:

      1. the depth chart's current QB1 for that team this week
         (:func:`get_depth_chart_qb1_by_team`), if it differs from the
         incumbent — the depth chart has already caught up; else
      2. the team's next-highest-trailing-passing-yards QB, excluding the
         incumbent.

    Leak-free: the injury slice is strictly ``(season, week)`` — same
    precedent as ``projection_engine.apply_injury_adjustments`` (weekly
    injury reports are published pre-kickoff). Trailing usage strictly
    excludes ``week`` by construction.

    Returns:
        Set of replacement ``player_id`` strings (gsis_id). Empty if
        ``injuries_df``/``weekly_df`` lack required columns or no
        team's flagged QB is that team's trailing-usage leader.
    """
    required_inj = {"season", "week", "position", "report_status", "gsis_id", "team"}
    if (
        injuries_df is None
        or injuries_df.empty
        or not required_inj.issubset(injuries_df.columns)
    ):
        return set()

    inj_week = injuries_df[
        (injuries_df["season"] == season)
        & (injuries_df["week"] == week)
        & (injuries_df["position"] == QB_STARTER_FLOOR_POSITION)
        & (injuries_df["report_status"].isin(INJURY_OUT_STATUSES))
    ]
    if inj_week.empty:
        return set()

    usage = compute_qb_team_trailing_usage(weekly_df, season, week)
    if usage.empty:
        return set()

    dc_by_team = get_depth_chart_qb1_by_team(depth_chart_df, week)

    injured_by_team = (
        inj_week.assign(gsis_id=lambda d: d["gsis_id"].astype(str))
        .groupby("team")["gsis_id"]
        .apply(set)
    )

    replacements = set()
    for team, injured_ids in injured_by_team.items():
        team_usage = usage[usage["recent_team"] == team].sort_values(
            "trailing_passing_yards", ascending=False
        )
        if team_usage.empty:
            continue
        incumbent_id = str(team_usage.iloc[0]["player_id"])
        if incumbent_id not in injured_ids:
            continue  # the flagged QB isn't this team's usage leader

        replacement_id = None
        dc_qb1 = dc_by_team.get(team)
        if dc_qb1 and dc_qb1 != incumbent_id:
            replacement_id = dc_qb1
        else:
            backups = team_usage[team_usage["player_id"].astype(str) != incumbent_id]
            if not backups.empty:
                replacement_id = str(backups.iloc[0]["player_id"])

        if replacement_id:
            replacements.add(replacement_id)

    return replacements


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
    injuries_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Raise QB projections to a starter-tier floor for newly-designated starters.

    A row qualifies when ``position == 'QB'``, ``week >= MIN_WEEK``, own
    trailing passing yards/game (:func:`compute_qb_trailing_passing_yards`)
    is backup-level (missing, or below :data:`BACKUP_PASSING_YARDS_THRESHOLD`),
    AND (v1 OR v2):

      - **v1 — depth-chart QB1** (:func:`get_depth_chart_qb1_ids`): listed
        as the team's depth-chart QB1 for ``week``.
      - **v2 — injury-flagged incumbent** (:func:`get_injury_based_replacements`,
        added 2026-08-09 — see module docstring): the team's trailing-usage
        incumbent starter is Out/Doubtful/IR on this week's injury report,
        and this row is the identified replacement.

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
        injuries_df: Bronze ``players/injuries`` rows for ``season``. When
            ``None`` (the default — both production call sites don't pass
            this), loaded internally via :func:`load_injury_reports` so v2
            works without any caller changes.

    Returns:
        ``proj_df`` with ``points_col`` updated for qualifying rows and
        three new provenance columns: ``qb_starter_floor_flag`` (bool),
        ``qb_starter_floor_value`` (float, NaN where not flagged), and
        ``qb_starter_floor_source`` (``"depth_chart"``, ``"injury"``,
        ``"both"``, or ``None`` where not flagged).
    """
    proj = proj_df.copy()
    proj["qb_starter_floor_flag"] = False
    proj["qb_starter_floor_value"] = float("nan")
    proj["qb_starter_floor_source"] = None

    if week < MIN_WEEK or proj.empty or "position" not in proj.columns:
        return proj

    is_qb = proj["position"] == QB_STARTER_FLOOR_POSITION
    proj_ids = proj["player_id"].astype(str)

    trailing_df = compute_qb_trailing_passing_yards(weekly_df, season, week)
    trailing_lookup = (
        trailing_df.drop_duplicates("player_id")
        .assign(player_id=lambda d: d["player_id"].astype(str))
        .set_index("player_id")["trailing_passing_yards"]
    )
    trailing = proj_ids.map(trailing_lookup)
    backup_level = trailing.isna() | (trailing < BACKUP_PASSING_YARDS_THRESHOLD)

    # v1 — depth-chart QB1.
    qb1_ids = get_depth_chart_qb1_ids(depth_chart_df, week)
    mask_v1 = is_qb & proj_ids.isin(qb1_ids) & backup_level

    # v2 — injury-flagged incumbent's replacement.
    if injuries_df is None:
        injuries_df = load_injury_reports(season)
    replacement_ids = get_injury_based_replacements(
        depth_chart_df, injuries_df, weekly_df, season, week
    )
    mask_v2 = is_qb & proj_ids.isin(replacement_ids) & backup_level

    mask = mask_v1 | mask_v2
    if not mask.any():
        return proj

    floor = compute_starter_tier_floor(scoring_format=scoring_format, haircut=haircut)
    proj.loc[mask, "qb_starter_floor_flag"] = True
    proj.loc[mask, "qb_starter_floor_value"] = floor
    proj.loc[mask_v1 & ~mask_v2, "qb_starter_floor_source"] = "depth_chart"
    proj.loc[mask_v2 & ~mask_v1, "qb_starter_floor_source"] = "injury"
    proj.loc[mask_v1 & mask_v2, "qb_starter_floor_source"] = "both"

    below_floor = mask & (proj[points_col] < floor)
    proj.loc[below_floor, points_col] = floor

    return proj
