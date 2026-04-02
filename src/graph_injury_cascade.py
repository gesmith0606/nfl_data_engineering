"""Injury cascade computation for target/carry redistribution.

Identifies significant injuries (starter-level players going Out/IR) and
measures how teammates absorb the vacated role by comparing target_share
and carry_share in the 3 weeks before vs 3 weeks after the injury event.

All computations use only historical data — no future leakage.

Exports:
    identify_significant_injuries: Find meaningful injury events.
    compute_redistribution: Measure role absorption per teammate.
    build_injury_cascade_graph: Orchestrate Neo4j ingestion of cascade edges.
"""

import glob
import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

# Thresholds for "significant" usage
TARGET_SHARE_THRESHOLD = 0.15
CARRY_SHARE_THRESHOLD = 0.20

# Minimum delta to count as role absorption
ABSORPTION_DELTA_THRESHOLD = 0.03

# Windows for before/after comparison
WINDOW_SIZE = 3


# ---------------------------------------------------------------------------
# Data readers
# ---------------------------------------------------------------------------


def _read_bronze_parquet(subdir: str, season: int) -> pd.DataFrame:
    """Read latest Bronze parquet for a subdirectory and season.

    Args:
        subdir: Path under data/bronze/ (e.g. 'players/injuries').
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if no files exist.
    """
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        # Check week-level partitioning
        pattern_w = os.path.join(
            BRONZE_DIR, subdir, f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            dfs = [pd.read_parquet(f) for f in files_w]
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------


def _compute_prior_usage(
    player_weekly: pd.DataFrame,
    player_id: str,
    team: str,
    season: int,
    week_injured: int,
) -> Dict[str, float]:
    """Compute average target_share and carry_share in prior WINDOW_SIZE weeks.

    Args:
        player_weekly: Full player weekly DataFrame.
        player_id: The gsis_id of the player.
        team: Team abbreviation.
        season: Season year.
        week_injured: Week the injury was reported.

    Returns:
        Dict with 'target_share' and 'carry_share' averages.
    """
    mask = (
        (player_weekly["player_id"] == player_id)
        & (player_weekly["recent_team"] == team)
        & (player_weekly["season"] == season)
        & (player_weekly["week"] >= week_injured - WINDOW_SIZE)
        & (player_weekly["week"] < week_injured)
    )
    subset = player_weekly.loc[mask]

    return {
        "target_share": (
            float(subset["target_share"].mean())
            if "target_share" in subset.columns and len(subset) > 0
            else 0.0
        ),
        "carry_share": (
            float(subset["carry_share"].mean())
            if "carry_share" in subset.columns and len(subset) > 0
            else 0.0
        ),
    }


def identify_significant_injuries(
    injuries_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
) -> List[Dict[str, object]]:
    """Find players with status Out/IR who had meaningful prior usage.

    A "significant" injury means the player had target_share > threshold
    or carry_share > threshold in the prior 3 weeks.

    Args:
        injuries_df: Bronze injuries DataFrame with gsis_id, team, season,
            week, report_status columns.
        player_weekly_df: Bronze player_weekly DataFrame.

    Returns:
        List of dicts with keys: player_id, team, season, week_injured,
        position, prior_target_share, prior_carry_share.
    """
    if injuries_df.empty or player_weekly_df.empty:
        return []

    # Ensure carry_share exists (it may not be in all player_weekly data)
    if "carry_share" not in player_weekly_df.columns:
        if "carries" in player_weekly_df.columns:
            # Approximate carry_share from carries / team total
            team_carries = player_weekly_df.groupby(["recent_team", "season", "week"])[
                "carries"
            ].transform("sum")
            player_weekly_df = player_weekly_df.copy()
            player_weekly_df["carry_share"] = np.where(
                team_carries > 0,
                player_weekly_df["carries"] / team_carries,
                0.0,
            )
        else:
            player_weekly_df = player_weekly_df.copy()
            player_weekly_df["carry_share"] = 0.0

    # Filter to Out/IR injuries
    out_statuses = {"Out", "IR", "Injured Reserve"}
    inj = injuries_df[injuries_df["report_status"].isin(out_statuses)].copy()

    if inj.empty:
        return []

    # Use gsis_id as player_id
    id_col = "gsis_id" if "gsis_id" in inj.columns else "player_id"
    significant = []

    # Deduplicate: one entry per player per team per season per week
    inj_dedup = inj.drop_duplicates(subset=[id_col, "team", "season", "week"])

    for _, row in inj_dedup.iterrows():
        player_id = str(row[id_col])
        team = str(row["team"])
        season = int(row["season"])
        week = int(row["week"])
        position = str(row.get("position", ""))

        usage = _compute_prior_usage(player_weekly_df, player_id, team, season, week)

        if (
            usage["target_share"] > TARGET_SHARE_THRESHOLD
            or usage["carry_share"] > CARRY_SHARE_THRESHOLD
        ):
            significant.append(
                {
                    "player_id": player_id,
                    "team": team,
                    "season": season,
                    "week_injured": week,
                    "position": position,
                    "prior_target_share": usage["target_share"],
                    "prior_carry_share": usage["carry_share"],
                }
            )

    logger.info(
        "Found %d significant injury events from %d total Out/IR reports",
        len(significant),
        len(inj_dedup),
    )
    return significant


def compute_redistribution(
    player_weekly_df: pd.DataFrame,
    injury_event: Dict[str, object],
) -> List[Dict[str, object]]:
    """Measure target/carry share redistribution after a significant injury.

    Compares each teammate's average share in WINDOW_SIZE weeks before vs
    WINDOW_SIZE weeks after the injury. Players with positive delta above
    threshold are considered absorbers.

    Args:
        player_weekly_df: Bronze player_weekly DataFrame.
        injury_event: Dict from identify_significant_injuries.

    Returns:
        List of redistribution dicts with absorber info and deltas.
    """
    team = str(injury_event["team"])
    season = int(injury_event["season"])
    week_injured = int(injury_event["week_injured"])
    injured_id = str(injury_event["player_id"])

    # Ensure carry_share exists
    if "carry_share" not in player_weekly_df.columns:
        if "carries" in player_weekly_df.columns:
            team_carries = player_weekly_df.groupby(["recent_team", "season", "week"])[
                "carries"
            ].transform("sum")
            player_weekly_df = player_weekly_df.copy()
            player_weekly_df["carry_share"] = np.where(
                team_carries > 0,
                player_weekly_df["carries"] / team_carries,
                0.0,
            )
        else:
            player_weekly_df = player_weekly_df.copy()
            player_weekly_df["carry_share"] = 0.0

    # Filter to teammates on the same team in the same season
    teammates = player_weekly_df[
        (player_weekly_df["recent_team"] == team)
        & (player_weekly_df["season"] == season)
        & (player_weekly_df["player_id"] != injured_id)
    ].copy()

    if teammates.empty:
        return []

    # Before window: [week_injured - WINDOW_SIZE, week_injured)
    before = teammates[
        (teammates["week"] >= week_injured - WINDOW_SIZE)
        & (teammates["week"] < week_injured)
    ]
    # After window: (week_injured, week_injured + WINDOW_SIZE]
    after = teammates[
        (teammates["week"] > week_injured)
        & (teammates["week"] <= week_injured + WINDOW_SIZE)
    ]

    if before.empty or after.empty:
        return []

    # Aggregate per-teammate before/after averages
    share_cols = ["target_share", "carry_share"]
    available_cols = [c for c in share_cols if c in teammates.columns]

    before_avg = before.groupby("player_id")[available_cols].mean()
    after_avg = after.groupby("player_id")[available_cols].mean()

    # Compute deltas for players appearing in both windows
    common_ids = before_avg.index.intersection(after_avg.index)
    if common_ids.empty:
        return []

    redistributions = []
    for pid in common_ids:
        entry = {
            "absorber_id": str(pid),
            "trigger_player_id": injured_id,
            "team": team,
            "season": season,
            "week_injured": week_injured,
        }

        ts_before = (
            float(before_avg.loc[pid, "target_share"])
            if "target_share" in available_cols
            else 0.0
        )
        ts_after = (
            float(after_avg.loc[pid, "target_share"])
            if "target_share" in available_cols
            else 0.0
        )
        cs_before = (
            float(before_avg.loc[pid, "carry_share"])
            if "carry_share" in available_cols
            else 0.0
        )
        cs_after = (
            float(after_avg.loc[pid, "carry_share"])
            if "carry_share" in available_cols
            else 0.0
        )

        ts_delta = ts_after - ts_before
        cs_delta = cs_after - cs_before

        # Only include if at least one delta exceeds threshold
        if (
            ts_delta > ABSORPTION_DELTA_THRESHOLD
            or cs_delta > ABSORPTION_DELTA_THRESHOLD
        ):
            entry.update(
                {
                    "target_share_before": ts_before,
                    "target_share_after": ts_after,
                    "target_share_delta": ts_delta,
                    "carry_share_before": cs_before,
                    "carry_share_after": cs_after,
                    "carry_share_delta": cs_delta,
                }
            )
            redistributions.append(entry)

    return redistributions


def build_injury_cascade_data(
    seasons: List[int],
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """Load Bronze data and compute injury cascades for given seasons.

    This is a pure data function (no Neo4j dependency) for testability.

    Args:
        seasons: List of season years to process.

    Returns:
        Tuple of (injury_events, redistribution_edges).
    """
    all_injuries = []
    all_redistributions = []

    for season in seasons:
        injuries_df = _read_bronze_parquet("players/injuries", season)
        player_weekly_df = _read_bronze_parquet("players/weekly", season)

        if injuries_df.empty or player_weekly_df.empty:
            logger.warning("Missing data for season %d, skipping", season)
            continue

        events = identify_significant_injuries(injuries_df, player_weekly_df)
        all_injuries.extend(events)

        for event in events:
            redist = compute_redistribution(player_weekly_df, event)
            all_redistributions.extend(redist)

    logger.info(
        "Computed %d injury events, %d redistribution edges across %d seasons",
        len(all_injuries),
        len(all_redistributions),
        len(seasons),
    )
    return all_injuries, all_redistributions


def build_injury_cascade_graph(
    gdb: "GraphDB",
    seasons: List[int],
) -> Tuple[int, int]:
    """Build injury cascade graph in Neo4j from Bronze data.

    Creates:
    - (:Player)-[:INJURED]->(:Game) edges from injury reports
    - (:Player)-[:ABSORBS_ROLE]->(:Player) edges from redistribution analysis

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of season years.

    Returns:
        Tuple of (n_injury_edges, n_absorption_edges).
    """
    if not gdb.is_connected:
        logger.warning("Neo4j not connected — skipping cascade graph build")
        return 0, 0

    injury_events, redistributions = build_injury_cascade_data(seasons)

    # Create INJURED edges
    n_injured = 0
    batch_size = 500
    for season in seasons:
        injuries_df = _read_bronze_parquet("players/injuries", season)
        if injuries_df.empty:
            continue

        id_col = "gsis_id" if "gsis_id" in injuries_df.columns else "player_id"
        out_inj = injuries_df[
            injuries_df["report_status"].isin({"Out", "IR", "Injured Reserve"})
        ]

        edges = []
        for _, row in out_inj.iterrows():
            # Construct game_id from season, week, team pattern
            season_val = int(row["season"])
            week_val = int(row["week"])
            gsis_id = str(row[id_col])
            edges.append(
                {
                    "gsis_id": gsis_id,
                    "season": season_val,
                    "week": week_val,
                    "status": str(row["report_status"]),
                    "injury": str(row.get("report_primary_injury", "")),
                }
            )

        for i in range(0, len(edges), batch_size):
            batch = edges[i : i + batch_size]
            gdb.run_write(
                "UNWIND $edges AS e "
                "MATCH (p:Player {gsis_id: e.gsis_id}) "
                "MATCH (g:Game) WHERE g.season = e.season AND g.week = e.week "
                "  AND (g.home_team IN [(p2)-[:PLAYS_FOR]->(t:Team) WHERE p2 = p | t.abbr] "
                "   OR g.away_team IN [(p2)-[:PLAYS_FOR]->(t:Team) WHERE p2 = p | t.abbr]) "
                "MERGE (p)-[r:INJURED]->(g) "
                "SET r.status = e.status, r.injury = e.injury",
                {"edges": batch},
            )
            n_injured += len(batch)

    # Create ABSORBS_ROLE edges
    n_absorb = 0
    for i in range(0, len(redistributions), batch_size):
        batch = redistributions[i : i + batch_size]
        # Convert numpy types to native Python for Neo4j driver
        clean_batch = []
        for entry in batch:
            clean_batch.append(
                {
                    k: (
                        float(v)
                        if isinstance(v, (np.floating, float))
                        else int(v) if isinstance(v, (np.integer,)) else str(v)
                    )
                    for k, v in entry.items()
                }
            )
        gdb.run_write(
            "UNWIND $edges AS e "
            "MATCH (absorber:Player {gsis_id: e.absorber_id}) "
            "MATCH (trigger:Player {gsis_id: e.trigger_player_id}) "
            "MERGE (absorber)-[r:ABSORBS_ROLE {season: toInteger(e.season), "
            "  week_injured: toInteger(e.week_injured)}]->(trigger) "
            "SET r.target_share_before = toFloat(e.target_share_before), "
            "    r.target_share_after = toFloat(e.target_share_after), "
            "    r.target_share_delta = toFloat(e.target_share_delta), "
            "    r.carry_share_before = toFloat(e.carry_share_before), "
            "    r.carry_share_after = toFloat(e.carry_share_after), "
            "    r.carry_share_delta = toFloat(e.carry_share_delta), "
            "    r.team = e.team",
            {"edges": clean_batch},
        )
        n_absorb += len(clean_batch)

    logger.info("Created %d INJURED edges, %d ABSORBS_ROLE edges", n_injured, n_absorb)
    return n_injured, n_absorb
