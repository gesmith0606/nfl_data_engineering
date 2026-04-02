"""OL lineup tracking and RB edge construction for Neo4j graph.

Builds two edge types from PBP participation data:
    1. :BLOCKS_FOR — OL snap-level contribution per team/week.
    2. :RUSHES_BEHIND — RB rushing stats with OL context.

Exports:
    build_ol_lineup_edges: OL per-team snap tracking with backup detection.
    build_rushes_behind_edges: RB rushing stats behind OL lineup.
    ingest_ol_graph: Write edges to Neo4j.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# OL lineup edges
# ---------------------------------------------------------------------------


def build_ol_lineup_edges(
    participation_parsed_df: pd.DataFrame,
    depth_charts_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build OL-per-team edges from parsed participation and depth charts.

    Identifies the 5 OL on each snap, cross-references depth charts for
    position labels and starter status, and detects backup insertions.

    Args:
        participation_parsed_df: Output of parse_participation_players.
        depth_charts_df: Depth chart DataFrame with gsis_id, club_code,
            position, depth_team columns. Optional.

    Returns:
        DataFrame with columns: ol_player_id, team, season, week,
        snap_count, is_backup_insertion, ol_label.
        Empty DataFrame if no OL found.
    """
    if participation_parsed_df.empty:
        return pd.DataFrame()

    from graph_participation import OL_POSITIONS

    # Filter to offensive linemen
    mask = (participation_parsed_df["side"] == "offense") & (
        participation_parsed_df["position"].isin(OL_POSITIONS)
    )
    ol = participation_parsed_df[mask].copy()
    if ol.empty:
        return pd.DataFrame()

    # We need season/week; derive from game_id if not present
    if "season" not in ol.columns or "week" not in ol.columns:
        # game_id format: "YYYY_WW_AWAY_HOME"
        if "game_id" in ol.columns:
            parts = ol["game_id"].str.split("_", expand=True)
            if parts.shape[1] >= 2:
                ol["season"] = pd.to_numeric(parts[0], errors="coerce")
                ol["week"] = pd.to_numeric(parts[1], errors="coerce")

    # Determine team from game_id + side (offense => posteam)
    # We need to derive team association; use depth chart or game context
    if "team" not in ol.columns:
        ol["team"] = "UNK"

    # Build starter map from depth charts
    starter_ids = set()
    label_map = {}
    if depth_charts_df is not None and not depth_charts_df.empty:
        dc = depth_charts_df.copy()
        id_col = "gsis_id" if "gsis_id" in dc.columns else "player_id"

        if id_col in dc.columns and "position" in dc.columns:
            ol_dc = dc[
                dc["position"].isin(OL_POSITIONS | {"LT", "LG", "C", "RG", "RT"})
            ]
            if "depth_team" in ol_dc.columns:
                starters = ol_dc[ol_dc["depth_team"] == 1]
                starter_ids = set(starters[id_col].astype(str).unique())
                for _, row in starters.iterrows():
                    label_map[str(row[id_col])] = str(row["position"])

    # Aggregate: one row per (OL player, team, season, week)
    group_cols = ["player_gsis_id", "team", "season", "week"]
    group_cols = [c for c in group_cols if c in ol.columns]
    if not group_cols or "player_gsis_id" not in group_cols:
        return pd.DataFrame()

    agg = ol.groupby(group_cols, as_index=False).agg(snap_count=("play_id", "count"))

    agg = agg.rename(columns={"player_gsis_id": "ol_player_id"})
    agg["is_backup_insertion"] = ~agg["ol_player_id"].isin(starter_ids)
    agg["ol_label"] = agg["ol_player_id"].map(label_map).fillna("OL")

    logger.info("Built %d OL lineup edges", len(agg))
    return agg


# ---------------------------------------------------------------------------
# Rushes behind edges
# ---------------------------------------------------------------------------


def build_rushes_behind_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build RB rushing edges linked to OL lineup context.

    Filters PBP to run plays, links to OL on field, and aggregates
    rushing stats per (rusher, team, season, week).

    Args:
        pbp_df: Play-by-play DataFrame.
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        DataFrame with columns: rb_player_id, team, season, week,
        carries, yards, epa, ypc, run_location_left_rate,
        run_location_mid_rate, run_location_right_rate, ol_starters_avg.
        Empty DataFrame if no rush plays.
    """
    if pbp_df.empty or participation_parsed_df.empty:
        return pd.DataFrame()

    # Filter to rush plays
    rush_mask = (
        (pbp_df["play_type"] == "run")
        & pbp_df["rusher_player_id"].notna()
        & (pbp_df["rusher_player_id"].astype(str).str.len() > 0)
    )
    rushes = pbp_df[rush_mask].copy()
    if rushes.empty:
        return pd.DataFrame()

    # Ensure needed columns with defaults
    for col, default in [
        ("yards_gained", 0),
        ("epa", 0.0),
        ("run_location", ""),
        ("run_gap", ""),
    ]:
        if col not in rushes.columns:
            rushes[col] = default

    rushes["yards_gained"] = rushes["yards_gained"].fillna(0)
    rushes["epa"] = rushes["epa"].fillna(0.0)

    # Location distribution
    rushes["is_left"] = (rushes["run_location"] == "left").astype(int)
    rushes["is_middle"] = (rushes["run_location"] == "middle").astype(int)
    rushes["is_right"] = (rushes["run_location"] == "right").astype(int)

    # Count OL starters on field per play (for context)
    from graph_participation import OL_POSITIONS

    ol_mask = (participation_parsed_df["side"] == "offense") & (
        participation_parsed_df["position"].isin(OL_POSITIONS)
    )
    ol_per_play = (
        participation_parsed_df[ol_mask]
        .groupby(["game_id", "play_id"], as_index=False)
        .agg(ol_count=("player_gsis_id", "count"))
    )

    rushes = rushes.merge(ol_per_play, on=["game_id", "play_id"], how="left")
    rushes["ol_count"] = rushes["ol_count"].fillna(5)

    # Aggregate by (rusher, posteam, season, week)
    team_col = "posteam" if "posteam" in rushes.columns else "home_team"
    group_keys = ["rusher_player_id", team_col, "season", "week"]
    group_keys = [c for c in group_keys if c in rushes.columns]
    if "rusher_player_id" not in group_keys:
        return pd.DataFrame()

    agg = rushes.groupby(group_keys, as_index=False).agg(
        carries=("play_id", "count"),
        yards=("yards_gained", "sum"),
        epa=("epa", "sum"),
        run_left_count=("is_left", "sum"),
        run_mid_count=("is_middle", "sum"),
        run_right_count=("is_right", "sum"),
        ol_starters_avg=("ol_count", "mean"),
    )

    agg = agg.rename(columns={"rusher_player_id": "rb_player_id", team_col: "team"})

    # YPC
    agg["ypc"] = np.where(agg["carries"] > 0, agg["yards"] / agg["carries"], 0.0)

    # Location rates
    total = agg["run_left_count"] + agg["run_mid_count"] + agg["run_right_count"]
    total = total.replace(0, 1)
    agg["run_location_left_rate"] = agg["run_left_count"] / total
    agg["run_location_mid_rate"] = agg["run_mid_count"] / total
    agg["run_location_right_rate"] = agg["run_right_count"] / total
    agg = agg.drop(columns=["run_left_count", "run_mid_count", "run_right_count"])

    logger.info(
        "Built %d RUSHES_BEHIND edges from %d rush plays", len(agg), len(rushes)
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_ol_graph(
    graph_db: "GraphDB",
    ol_edges_df: pd.DataFrame,
    rb_edges_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write OL and RB edges to Neo4j.

    Creates :BLOCKS_FOR edges (OL -> Team) and :RUSHES_BEHIND edges
    (RB -> Team). Uses MERGE for idempotent re-runs.

    Args:
        graph_db: Connected GraphDB instance.
        ol_edges_df: Output of build_ol_lineup_edges.
        rb_edges_df: Output of build_rushes_behind_edges. Optional.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping OL graph ingestion")
        return 0

    total = 0

    # --- BLOCKS_FOR edges ---
    if not ol_edges_df.empty:
        records = ol_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (ol:Player {gsis_id: e.ol_player_id}) "
                "MATCH (t:Team {abbr: e.team}) "
                "MERGE (ol)-[r:BLOCKS_FOR {season: e.season, week: e.week}]->(t) "
                "SET r.snap_count = e.snap_count, "
                "    r.is_backup_insertion = e.is_backup_insertion, "
                "    r.ol_label = e.ol_label",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d BLOCKS_FOR edges", len(records))

    # --- RUSHES_BEHIND edges ---
    if rb_edges_df is not None and not rb_edges_df.empty:
        records = rb_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (rb:Player {gsis_id: e.rb_player_id}) "
                "MATCH (t:Team {abbr: e.team}) "
                "MERGE (rb)-[r:RUSHES_BEHIND {season: e.season, week: e.week}]->(t) "
                "SET r.carries = e.carries, "
                "    r.yards = e.yards, "
                "    r.epa = e.epa, "
                "    r.ypc = e.ypc, "
                "    r.ol_starters_avg = e.ol_starters_avg",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d RUSHES_BEHIND edges", len(records))

    return total
