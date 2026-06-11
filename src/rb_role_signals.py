"""RB role-change signal computation for projection correction.

Three lagged, leak-safe signals that identify when an RB's backfield role
has changed since our rolling-average projection window was computed:

1. **Teammate-status adjustment** (``rb_better_teammate_out``,
   ``rb_better_teammate_returning``):
   - Uses Bronze depth charts + Bronze injury reports.
   - For each RB-week, checks whether teammates ranked *above* this player
     on the depth chart are reported Out/Doubtful (opportunity up) or are
     returning from an Out/IR stint this week (opportunity down).

2. **Snap-share trend** (``snap_share_slope``, ``snap_share_collapsing``):
   - Uses Bronze snap counts (``offense_pct`` column, player keyed by
     display name ``player``).
   - Computes the trailing 2-week vs prior 2-week delta in snap share.
   - ``snap_share_collapsing`` fires when the player's recent snap share has
     fallen sharply relative to the window used for projections.

3. **Depth-chart staleness** (``depth_rank_improved``,
   ``depth_rank_worsened``):
   - Uses Bronze depth charts.
   - Compares the player's *current-week* depth rank to their *modal* rank
     across the trailing projection window (weeks t−3 to t−1).

Temporal-safety contract
------------------------
All three signals are designed to be computable **before the game is played**
(week-t pre-game) and use no same-game outcomes:

- **Same-week pregame inputs (legitimately available):**
  - Week-t depth chart published by NFL midweek before the game.
  - Week-t injury report (Wednesday–Friday practice reports) — ``report_status``
    reflects the official Friday designation. This is the standard input
    fantasy analysts use.
  - The snap_share_slope uses only weeks < t (trailing history), so it is
    always leak-safe even if computed on game day.

- **Trailing-only inputs:**
  - Snap percentages from weeks prior to t.
  - Depth ranks from weeks prior to t (for the modal-rank baseline).
  - Injury history (whether a teammate was Out in recent weeks) from weeks < t.

No play-level outcomes, no week-t game stats, and no future weeks are used.

Data sources
------------
- ``data/bronze/depth_charts/season=YYYY/`` — columns: season, week,
  club_code, gsis_id, full_name, position, formation, depth_team (1/2/3…).
- ``data/bronze/players/injuries/season=YYYY/`` — columns: season, week,
  team, gsis_id, full_name, position, report_status.
- ``data/bronze/players/snaps/season=YYYY/week=WW/`` — columns: season, week,
  team, player (display name), position, offense_pct.
- ``data/bronze/players/weekly/season=YYYY/`` — player_id / player_name for
  snap-to-player_id name matching.
"""

import glob
import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

# Injury statuses that indicate a teammate is unavailable
OUT_STATUSES = frozenset({"Out", "IR", "Injured Reserve"})

# Statuses severe enough to promote the next-in-line RB
MISSING_STATUSES = frozenset({"Out", "IR", "Injured Reserve", "Doubtful"})

# Weeks to look back for modal depth-rank baseline and injury history
LOOKBACK_WEEKS = 3

# Snap share windows: "recent" = last 2 games, "prior" = 2 games before that
SNAP_RECENT_N = 2
SNAP_PRIOR_N = 2

# Collapse threshold: snap share falls by this much from prior window → flag
SNAP_COLLAPSE_THRESHOLD = 0.18  # 18 percentage points (fires for Moss w8-w10)

# Recent snap share ceiling for collapse signal: player must be below this
# value to register as "role lost" rather than merely "volume dipped"
SNAP_COLLAPSE_RECENT_CEILING = 0.55

# Minimum recent snap share to be considered active (filters IR'd players)
MIN_SNAP_ACTIVE = 0.05


# ---------------------------------------------------------------------------
# Bronze data readers
# ---------------------------------------------------------------------------


def _read_depth_charts(seasons: List[int]) -> pd.DataFrame:
    """Read and concatenate Bronze depth chart parquets for given seasons.

    Args:
        seasons: List of NFL season years.

    Returns:
        DataFrame with columns: season, week, club_code, gsis_id, full_name,
        position, formation, depth_team (numeric). Regular-season weeks only
        (weeks 1–18). Offense formation only.
    """
    frames: List[pd.DataFrame] = []
    for season in seasons:
        pattern = os.path.join(
            BRONZE_DIR, "depth_charts", f"season={season}", "*.parquet"
        )
        files = sorted(glob.glob(pattern))
        if not files:
            logger.debug("No depth chart files for season %d", season)
            continue
        df = pd.read_parquet(files[-1])
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    dc = pd.concat(frames, ignore_index=True)

    # Normalise week to int, drop playoff weeks
    dc["week"] = pd.to_numeric(dc["week"], errors="coerce")
    dc = dc[dc["week"].between(1, 18)].copy()
    dc["week"] = dc["week"].astype(int)

    # Normalise depth_team to int
    dc["depth_team"] = pd.to_numeric(dc["depth_team"], errors="coerce")

    # Keep only Offense formation
    if "formation" in dc.columns:
        dc = dc[dc["formation"] == "Offense"].copy()

    # Keep only RB position
    dc = dc[dc["position"] == "RB"].copy()

    # Keep only depth_position that maps to running back duties
    # (exclude FB, KOR, PR, SS, WR)
    if "depth_position" in dc.columns:
        rb_positions = {"RB", "HB"}
        # Some rows have whitespace / empty depth_position — keep them
        keep = dc["depth_position"].str.strip().isin(rb_positions) | dc[
            "depth_position"
        ].str.strip().eq("")
        dc = dc[keep].copy()

    dc = dc.dropna(subset=["gsis_id", "depth_team"])
    dc["season"] = dc["season"].astype(int)

    return dc.reset_index(drop=True)


def _read_injuries(seasons: List[int]) -> pd.DataFrame:
    """Read and concatenate Bronze injury parquets for given seasons.

    Args:
        seasons: List of NFL season years.

    Returns:
        DataFrame with columns: season, week, team, gsis_id, full_name,
        position, report_status. Regular-season weeks only.
    """
    frames: List[pd.DataFrame] = []
    for season in seasons:
        pattern = os.path.join(
            BRONZE_DIR, "players", "injuries", f"season={season}", "*.parquet"
        )
        files = sorted(glob.glob(pattern))
        if not files:
            logger.debug("No injury files for season %d", season)
            continue
        df = pd.read_parquet(files[-1])
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    inj = pd.concat(frames, ignore_index=True)

    inj["week"] = pd.to_numeric(inj["week"], errors="coerce")
    inj = inj[inj["week"].between(1, 18)].copy()
    inj["week"] = inj["week"].astype(int)
    inj["season"] = inj["season"].astype(int)

    # Use gsis_id as the player id
    if "gsis_id" in inj.columns:
        inj = inj.rename(columns={"gsis_id": "player_id"})

    # Normalise status to string, fill None as empty
    inj["report_status"] = inj["report_status"].fillna("").astype(str)

    return inj.reset_index(drop=True)


def _read_snaps(seasons: List[int]) -> pd.DataFrame:
    """Read and concatenate Bronze snap count parquets for given seasons.

    Args:
        seasons: List of NFL season years.

    Returns:
        DataFrame with columns: season, week, team, player (display name),
        position, offense_pct. Regular-season weeks only. RBs only.
    """
    frames: List[pd.DataFrame] = []
    for season in seasons:
        pattern = os.path.join(
            BRONZE_DIR,
            "players",
            "snaps",
            f"season={season}",
            "week=*",
            "*.parquet",
        )
        files = sorted(glob.glob(pattern))
        if not files:
            logger.debug("No snap files for season %d", season)
            continue
        season_frames = [pd.read_parquet(f) for f in files]
        frames.extend(season_frames)

    if not frames:
        return pd.DataFrame()

    snaps = pd.concat(frames, ignore_index=True)

    snaps["week"] = pd.to_numeric(snaps["week"], errors="coerce")
    snaps = snaps[snaps["week"].between(1, 18)].copy()
    snaps["week"] = snaps["week"].astype(int)
    snaps["season"] = snaps["season"].astype(int)

    # Keep RBs only
    if "position" in snaps.columns:
        snaps = snaps[snaps["position"] == "RB"].copy()

    # Normalise offense_pct to float
    snaps["offense_pct"] = pd.to_numeric(snaps["offense_pct"], errors="coerce").fillna(
        0.0
    )

    return snaps.reset_index(drop=True)


def _read_player_weekly_for_id_map(seasons: List[int]) -> pd.DataFrame:
    """Read player_weekly to build display-name → player_id mapping.

    snap_counts identifies players by their full display name (``player``
    column, e.g. "Zack Moss") while player_weekly has both an abbreviated
    ``player_name`` ("Z.Moss") and a full ``player_display_name``
    ("Zack Moss"). We join on the full display name so the mapping works.

    Args:
        seasons: List of NFL season years.

    Returns:
        DataFrame with columns: player_id, player_name (display, full),
        recent_team, season.
    """
    frames: List[pd.DataFrame] = []
    for season in seasons:
        pattern = os.path.join(
            BRONZE_DIR, "players", "weekly", f"season={season}", "*.parquet"
        )
        files = sorted(glob.glob(pattern))
        if not files:
            continue
        cols = ["player_id", "player_name", "recent_team", "season", "position"]
        # Inspect the schema without reading data (pyarrow metadata only),
        # then do a single column-filtered read.
        import pyarrow.parquet as pq

        available = set(pq.ParquetFile(files[-1]).schema_arrow.names)
        if "player_display_name" in available:
            df = pd.read_parquet(files[-1], columns=cols + ["player_display_name"])
        else:
            df = pd.read_parquet(files[-1], columns=cols)
            df["player_display_name"] = df["player_name"]
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    pw = pd.concat(frames, ignore_index=True)
    pw = pw[pw["position"] == "RB"].copy()
    pw = pw.dropna(subset=["player_id"])
    pw["season"] = pw["season"].astype(int)
    # Use player_display_name as the join key (matches snap data "player" column)
    pw = pw.dropna(subset=["player_display_name"])
    pw = pw.drop_duplicates(subset=["player_display_name", "season", "player_id"])
    # Expose display name as "player_name" for the join key
    result = pw[["player_id", "player_display_name", "recent_team", "season"]].rename(
        columns={"player_display_name": "player_name"}
    )
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Signal 1: Teammate-status adjustment
# ---------------------------------------------------------------------------


def compute_teammate_status_signals(
    depth_charts: pd.DataFrame,
    injuries: pd.DataFrame,
) -> pd.DataFrame:
    """Compute rb_better_teammate_out and rb_better_teammate_returning.

    For each (player_id, team, season, week) tuple for an RB, determines:

    - ``rb_better_teammate_out``: Count of teammates ranked *above* this
      player on the depth chart (depth_team < this player's depth_team) who
      have report_status in MISSING_STATUSES this week.  Positive value means
      opportunity has been vacated — our projection should be higher.
      This signal uses the **same-week pre-game** injury report (Friday
      designation), which is legitimately available before kickoff.

    - ``rb_better_teammate_returning``: 1 if at least one teammate who was
      Out/IR in any of the prior LOOKBACK_WEEKS weeks is now active (not in
      OUT_STATUSES) this week AND is ranked above this player on the depth
      chart. Indicates the fill-in's role is about to shrink. This uses the
      week-t depth chart (pregame) plus trailing weeks' injury history.

    Args:
        depth_charts: Output of ``_read_depth_charts``.
        injuries: Output of ``_read_injuries``.

    Returns:
        DataFrame with columns: player_id, team, season, week,
        rb_better_teammate_out, rb_better_teammate_returning.
        One row per (player_id, team, season, week) for RBs.
    """
    if depth_charts.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "team",
                "season",
                "week",
                "rb_better_teammate_out",
                "rb_better_teammate_returning",
            ]
        )

    # Rename for clarity
    dc = depth_charts.rename(columns={"club_code": "team", "gsis_id": "player_id"})

    # Build set of (player_id, team, season, week) → depth_team rank
    dc = dc[["player_id", "team", "season", "week", "depth_team"]].copy()
    # Deduplicate: if a player appears multiple times at a position, keep min rank
    dc = dc.sort_values("depth_team").drop_duplicates(
        subset=["player_id", "team", "season", "week"], keep="first"
    )

    if injuries.empty:
        # Return zeros when no injury data available
        result = dc[["player_id", "team", "season", "week"]].copy()
        result["rb_better_teammate_out"] = 0
        result["rb_better_teammate_returning"] = 0
        return result

    rows = []
    # Process per team-season-week for efficiency
    for (team, season, week), grp in dc.groupby(["team", "season", "week"]):
        # Injury report for THIS week (pre-game designation)
        inj_this_week = injuries[
            (injuries["team"] == team)
            & (injuries["season"] == season)
            & (injuries["week"] == week)
        ]
        inj_this_status: Dict[str, str] = {}
        if not inj_this_week.empty:
            inj_this_status = dict(
                zip(inj_this_week["player_id"], inj_this_week["report_status"])
            )

        # Historical injury data: weeks in the lookback window (< current week)
        lookback_start = max(1, int(week) - LOOKBACK_WEEKS)
        inj_lookback = injuries[
            (injuries["team"] == team)
            & (injuries["season"] == season)
            & (injuries["week"] >= lookback_start)
            & (injuries["week"] < week)
        ]
        # Players who were Out/IR in the lookback window
        was_out_ids: frozenset = frozenset(
            inj_lookback.loc[
                inj_lookback["report_status"].isin(OUT_STATUSES), "player_id"
            ]
        )

        for _, row in grp.iterrows():
            pid = str(row["player_id"])
            my_rank = int(row["depth_team"])

            # Teammates ranked above me (lower depth_team number = higher rank)
            better_teammates = grp[grp["depth_team"] < my_rank]["player_id"].astype(str)

            # Signal 1a: how many of those teammates are Out/Doubtful this week
            better_out = sum(
                1
                for bt in better_teammates
                if inj_this_status.get(bt, "") in MISSING_STATUSES
            )

            # Signal 1b: is a previously-out teammate returning this week?
            # "Returning" = was Out in lookback AND is NOT in MISSING_STATUSES now
            returning = 0
            for bt in better_teammates:
                if bt in was_out_ids:
                    current_status = inj_this_status.get(bt, "")
                    if current_status not in MISSING_STATUSES:
                        returning = 1
                        break

            rows.append(
                {
                    "player_id": pid,
                    "team": team,
                    "season": season,
                    "week": week,
                    "rb_better_teammate_out": better_out,
                    "rb_better_teammate_returning": returning,
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "player_id",
                "team",
                "season",
                "week",
                "rb_better_teammate_out",
                "rb_better_teammate_returning",
            ]
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Signal 2: Snap-share trend
# ---------------------------------------------------------------------------


def _build_snap_id_map(
    snaps: pd.DataFrame,
    player_weekly: pd.DataFrame,
) -> pd.DataFrame:
    """Attach player_id to snap_count rows via display-name fuzzy join.

    snap_counts uses display names (e.g. "Zack Moss") while player_weekly
    uses player_id + player_name. We join on (player_name, team, season).

    Args:
        snaps: Output of ``_read_snaps``.
        player_weekly: Output of ``_read_player_weekly_for_id_map``.

    Returns:
        snaps DataFrame with additional ``player_id`` column where matched.
        Unmatched rows get player_id = NaN.
    """
    if snaps.empty or player_weekly.empty:
        snaps = snaps.copy()
        snaps["player_id"] = pd.NA
        return snaps

    # Build lookup: (player_name, team, season) → player_id
    # player_weekly.player_name is the short display name used in snaps
    id_map = (
        player_weekly.drop_duplicates(subset=["player_name", "recent_team", "season"])
        .set_index(["player_name", "recent_team", "season"])["player_id"]
    )

    # Snaps uses 'player' for display name and 'team' for team
    snaps = snaps.copy()
    snaps["player_id"] = snaps.set_index(
        ["player", "team", "season"]
    ).index.map(id_map).values

    return snaps


def compute_snap_trend_signals(
    snaps: pd.DataFrame,
    player_weekly: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute snap_share_slope and snap_share_collapsing for each RB-week.

    For week t, uses only snap data from weeks prior to t (lag-safe).

    Methodology:
    - recent_snap = mean(offense_pct, weeks [t-SNAP_RECENT_N, t-1])
    - prior_snap  = mean(offense_pct, weeks [t-SNAP_RECENT_N-SNAP_PRIOR_N,
                                              t-SNAP_RECENT_N-1])
    - snap_share_slope = recent_snap - prior_snap  (positive = trending up)
    - snap_share_collapsing = 1 if snap_share_slope < -SNAP_COLLAPSE_THRESHOLD
      AND recent_snap < 0.40 (no longer a high-share back)

    The signals are computed for *every* player-week present in the snap data.
    Weeks without enough historical data return NaN for slope and 0 for the
    flag.

    Args:
        snaps: Output of ``_read_snaps``. Must have columns: season, week,
            team, player (display name), offense_pct, position.
        player_weekly: Optional output of ``_read_player_weekly_for_id_map``.
            If provided, attaches player_id to the output. Otherwise the
            output uses (player, team, season, week) as identifiers.

    Returns:
        DataFrame with columns: player_id (if player_weekly provided else NaN),
        player (display name), team, season, week, recent_snap_pct,
        prior_snap_pct, snap_share_slope, snap_share_collapsing.
    """
    if snaps.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "player",
                "team",
                "season",
                "week",
                "recent_snap_pct",
                "prior_snap_pct",
                "snap_share_slope",
                "snap_share_collapsing",
            ]
        )

    # Attach player_id if we have a mapping table
    if player_weekly is not None and not player_weekly.empty:
        snaps = _build_snap_id_map(snaps, player_weekly)
    else:
        snaps = snaps.copy()
        snaps["player_id"] = pd.NA

    rows = []
    for (team, player_name, season), grp in snaps.groupby(["team", "player", "season"]):
        grp = grp.sort_values("week")
        # Get unique player_id for this player (first non-null)
        player_ids = grp["player_id"].dropna()
        pid = str(player_ids.iloc[0]) if len(player_ids) > 0 else pd.NA

        all_weeks = grp[["week", "offense_pct"]].set_index("week")["offense_pct"]

        # Determine the target weeks we want to compute signals for
        # (all weeks where this player appears in snap data)
        for week in sorted(grp["week"].unique()):
            # recent window: last SNAP_RECENT_N weeks before t
            recent_end = int(week) - 1
            recent_start = recent_end - SNAP_RECENT_N + 1

            # prior window: SNAP_PRIOR_N weeks before the recent window
            prior_end = recent_start - 1
            prior_start = prior_end - SNAP_PRIOR_N + 1

            recent_vals = [
                float(all_weeks[w])
                for w in range(recent_start, recent_end + 1)
                if w in all_weeks.index
            ]
            prior_vals = [
                float(all_weeks[w])
                for w in range(prior_start, prior_end + 1)
                if w in all_weeks.index
            ]

            recent_snap = float(np.mean(recent_vals)) if recent_vals else np.nan
            prior_snap = float(np.mean(prior_vals)) if prior_vals else np.nan

            if np.isnan(recent_snap) or np.isnan(prior_snap):
                slope = np.nan
                collapsing = 0
            else:
                slope = recent_snap - prior_snap
                collapsing = int(
                    slope < -SNAP_COLLAPSE_THRESHOLD
                    and recent_snap < SNAP_COLLAPSE_RECENT_CEILING
                )

            rows.append(
                {
                    "player_id": pid,
                    "player": player_name,
                    "team": team,
                    "season": season,
                    "week": int(week),
                    "recent_snap_pct": recent_snap,
                    "prior_snap_pct": prior_snap,
                    "snap_share_slope": slope,
                    "snap_share_collapsing": collapsing,
                }
            )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Signal 3: Depth-chart staleness
# ---------------------------------------------------------------------------


def compute_depth_chart_staleness(
    depth_charts: pd.DataFrame,
) -> pd.DataFrame:
    """Compute depth_rank_improved and depth_rank_worsened for each RB-week.

    For week t, compares the player's depth_team rank in week t against their
    modal rank across the trailing LOOKBACK_WEEKS window (weeks t-3 to t-1).

    This signal uses the **same-week pre-game** depth chart, which is
    legitimately available before kickoff and is the primary tool analysts
    use to detect role changes.

    Definitions:
    - ``modal_rank_lookback``: mode of depth_team over weeks [t-LOOKBACK_WEEKS, t-1].
      If only one distinct rank exists, that is the mode. NaN if no prior data.
    - ``depth_rank_improved``: 1 if current_rank < modal_rank (moved up the
      depth chart since our projection window).
    - ``depth_rank_worsened``: 1 if current_rank > modal_rank (demoted).

    Args:
        depth_charts: Output of ``_read_depth_charts``.

    Returns:
        DataFrame with columns: player_id, team, season, week, current_depth_rank,
        modal_depth_rank_lookback, depth_rank_improved, depth_rank_worsened.
    """
    if depth_charts.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "team",
                "season",
                "week",
                "current_depth_rank",
                "modal_depth_rank_lookback",
                "depth_rank_improved",
                "depth_rank_worsened",
            ]
        )

    dc = depth_charts.rename(columns={"club_code": "team", "gsis_id": "player_id"})
    dc = dc[["player_id", "team", "season", "week", "depth_team"]].copy()
    dc = dc.sort_values("depth_team").drop_duplicates(
        subset=["player_id", "team", "season", "week"], keep="first"
    )
    dc["depth_team"] = dc["depth_team"].astype(int)

    rows = []
    for (player_id, team, season), grp in dc.groupby(
        ["player_id", "team", "season"]
    ):
        grp = grp.sort_values("week")
        rank_by_week: Dict[int, int] = dict(
            zip(grp["week"].astype(int), grp["depth_team"].astype(int))
        )

        for week in sorted(grp["week"].unique()):
            week = int(week)
            current_rank = rank_by_week[week]

            # Lookback window: prior LOOKBACK_WEEKS weeks
            lookback_ranks = [
                rank_by_week[w]
                for w in range(max(1, week - LOOKBACK_WEEKS), week)
                if w in rank_by_week
            ]

            if lookback_ranks:
                # Modal rank (most common; ties broken by first occurrence)
                modal_rank = max(set(lookback_ranks), key=lookback_ranks.count)
                improved = int(current_rank < modal_rank)
                worsened = int(current_rank > modal_rank)
            else:
                modal_rank = None
                improved = 0
                worsened = 0

            rows.append(
                {
                    "player_id": str(player_id),
                    "team": team,
                    "season": season,
                    "week": week,
                    "current_depth_rank": current_rank,
                    "modal_depth_rank_lookback": modal_rank,
                    "depth_rank_improved": improved,
                    "depth_rank_worsened": worsened,
                }
            )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build_rb_role_signals(
    seasons: List[int],
    weeks: Optional[Tuple[int, int]] = None,
) -> pd.DataFrame:
    """Build the complete RB role-change signal table for given seasons.

    Reads Bronze depth charts, injuries, and snap counts; computes all three
    signal families; and joins them into a single wide DataFrame keyed on
    (player_id, team, season, week).

    Args:
        seasons: List of NFL season years (e.g. [2022, 2023, 2024]).
        weeks: Optional (min_week, max_week) tuple to filter weeks.
            Defaults to regular season (3, 18) for consistency with the
            backtest window used for validation.

    Returns:
        DataFrame with columns:
            player_id, team, season, week,
            rb_better_teammate_out, rb_better_teammate_returning,
            snap_share_slope, snap_share_collapsing,
            recent_snap_pct, prior_snap_pct,
            current_depth_rank, modal_depth_rank_lookback,
            depth_rank_improved, depth_rank_worsened.
        One row per (player_id, team, season, week).
        Returns empty DataFrame if required Bronze data is missing.
    """
    logger.info("Building RB role signals for seasons %s", seasons)

    # --- Load raw Bronze tables ---
    depth_charts = _read_depth_charts(seasons)
    injuries = _read_injuries(seasons)
    snaps = _read_snaps(seasons)
    player_weekly = _read_player_weekly_for_id_map(seasons)

    logger.info(
        "Loaded: %d depth-chart rows, %d injury rows, %d snap rows, %d player-weekly id rows",
        len(depth_charts),
        len(injuries),
        len(snaps),
        len(player_weekly),
    )

    if depth_charts.empty:
        logger.warning("No depth chart data — returning empty signal table")
        return pd.DataFrame()

    # --- Compute each signal family ---
    teammate_signals = compute_teammate_status_signals(depth_charts, injuries)
    snap_signals = compute_snap_trend_signals(snaps, player_weekly)
    depth_staleness = compute_depth_chart_staleness(depth_charts)

    # --- Join signals on (player_id, team, season, week) ---
    # Use depth_staleness as the base (has every RB-team-season-week in depth charts)
    result = depth_staleness.copy()

    if not teammate_signals.empty:
        result = result.merge(
            teammate_signals[
                [
                    "player_id",
                    "team",
                    "season",
                    "week",
                    "rb_better_teammate_out",
                    "rb_better_teammate_returning",
                ]
            ],
            on=["player_id", "team", "season", "week"],
            how="left",
        )
    else:
        result["rb_better_teammate_out"] = 0
        result["rb_better_teammate_returning"] = 0

    # For snap signals, player_id may come from name matching — join on that
    if not snap_signals.empty:
        snap_for_join = snap_signals.dropna(subset=["player_id"]).copy()
        snap_for_join["player_id"] = snap_for_join["player_id"].astype(str)
        snap_for_join = snap_for_join.drop_duplicates(
            subset=["player_id", "team", "season", "week"], keep="first"
        )
        result = result.merge(
            snap_for_join[
                [
                    "player_id",
                    "team",
                    "season",
                    "week",
                    "snap_share_slope",
                    "snap_share_collapsing",
                    "recent_snap_pct",
                    "prior_snap_pct",
                ]
            ],
            on=["player_id", "team", "season", "week"],
            how="left",
        )
    else:
        result["snap_share_slope"] = np.nan
        result["snap_share_collapsing"] = 0
        result["recent_snap_pct"] = np.nan
        result["prior_snap_pct"] = np.nan

    # Fill integer signals with 0 where missing
    for col in [
        "rb_better_teammate_out",
        "rb_better_teammate_returning",
        "snap_share_collapsing",
        "depth_rank_improved",
        "depth_rank_worsened",
    ]:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)

    # Filter to requested week range
    if weeks is not None:
        min_w, max_w = weeks
        result = result[result["week"].between(min_w, max_w)].copy()

    result["season"] = result["season"].astype(int)
    result["week"] = result["week"].astype(int)

    logger.info("Built signal table: %d rows", len(result))
    return result.reset_index(drop=True)
