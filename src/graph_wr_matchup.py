"""WR-vs-Defense edge construction for Neo4j graph.

Builds two edge types from PBP participation data:
    1. :TARGETED_AGAINST — WR aggregate stats vs each opposing defense.
    2. :ON_FIELD_WITH — WR-CB co-occurrence on pass plays.

All computations use only historical data and are idempotent via MERGE.

Exports:
    build_targeted_against_edges: WR → defense aggregate edges.
    build_on_field_with_edges: WR ↔ CB co-occurrence edges.
    ingest_wr_matchup_graph: Write edges to Neo4j.
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Edge construction
# ---------------------------------------------------------------------------


def build_targeted_against_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build WR-vs-defense aggregate edges from PBP pass plays.

    Groups pass plays by (receiver_player_id, defteam, season, week) and
    aggregates targets, catches, yards, TDs, EPA, air_yards, and
    pass_location distribution.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players
            (used only for validation; receiver comes from PBP).

    Returns:
        DataFrame with columns: receiver_player_id, defteam, season, week,
        targets, catches, yards, tds, epa, air_yards,
        pass_left_rate, pass_mid_rate, pass_right_rate.
        Empty DataFrame if no pass plays found.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    # Filter to pass plays with a target
    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask].copy()
    if passes.empty:
        return pd.DataFrame()

    # Ensure required columns exist with defaults
    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
        ("epa", 0.0),
        ("air_yards", 0.0),
        ("pass_location", ""),
    ]:
        if col not in passes.columns:
            passes[col] = default

    # Pass location one-hot for distribution
    passes["is_left"] = (passes["pass_location"] == "left").astype(int)
    passes["is_middle"] = (passes["pass_location"] == "middle").astype(int)
    passes["is_right"] = (passes["pass_location"] == "right").astype(int)

    group_keys = ["receiver_player_id", "defteam", "season", "week"]
    agg = passes.groupby(group_keys, as_index=False).agg(
        targets=("play_id", "count"),
        catches=("complete_pass", "sum"),
        yards=("yards_gained", "sum"),
        tds=("touchdown", "sum"),
        epa=("epa", "sum"),
        air_yards=("air_yards", "sum"),
        pass_left_count=("is_left", "sum"),
        pass_mid_count=("is_middle", "sum"),
        pass_right_count=("is_right", "sum"),
    )

    # Convert counts to rates
    total = agg["pass_left_count"] + agg["pass_mid_count"] + agg["pass_right_count"]
    total = total.replace(0, 1)  # avoid div/0
    agg["pass_left_rate"] = agg["pass_left_count"] / total
    agg["pass_mid_rate"] = agg["pass_mid_count"] / total
    agg["pass_right_rate"] = agg["pass_right_count"] / total
    agg = agg.drop(columns=["pass_left_count", "pass_mid_count", "pass_right_count"])

    logger.info(
        "Built %d TARGETED_AGAINST edges from %d pass plays",
        len(agg),
        len(passes),
    )
    return agg


def build_on_field_with_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build WR-CB co-occurrence edges from PBP pass plays.

    For each pass play, identifies the targeted WR and all CBs on the field,
    then aggregates co-occurrence counts by (WR, CB, season, week).

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        DataFrame with columns: wr_player_id, cb_player_id, season, week,
        snap_count, targets_during, yards_during.
        Empty DataFrame if no data.
    """
    if pbp_df.empty or participation_parsed_df.empty:
        return pd.DataFrame()

    # Filter PBP to pass plays with receiver
    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[pass_mask][
        ["game_id", "play_id", "receiver_player_id", "season", "week", "yards_gained"]
    ].copy()
    if passes.empty:
        return pd.DataFrame()

    passes["yards_gained"] = passes["yards_gained"].fillna(0)

    # Get CBs on field per play
    from graph_participation import CB_POSITIONS

    cb_mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(CB_POSITIONS)
    )
    cbs = participation_parsed_df[cb_mask][
        ["game_id", "play_id", "player_gsis_id"]
    ].rename(columns={"player_gsis_id": "cb_player_id"})

    if cbs.empty:
        return pd.DataFrame()

    # Join: one row per (pass play, CB on field)
    merged = passes.merge(cbs, on=["game_id", "play_id"], how="inner")
    merged = merged.rename(columns={"receiver_player_id": "wr_player_id"})

    if merged.empty:
        return pd.DataFrame()

    # Aggregate by (WR, CB, season, week)
    agg = merged.groupby(
        ["wr_player_id", "cb_player_id", "season", "week"], as_index=False
    ).agg(
        snap_count=("play_id", "count"),
        targets_during=("play_id", "count"),
        yards_during=("yards_gained", "sum"),
    )

    logger.info(
        "Built %d ON_FIELD_WITH edges from %d pass-play x CB rows",
        len(agg),
        len(merged),
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_wr_matchup_graph(
    graph_db: "GraphDB",
    targeted_edges_df: pd.DataFrame,
    cooccurrence_edges_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write WR matchup edges to Neo4j.

    Creates :TARGETED_AGAINST edges (WR -> Team) and optionally
    :ON_FIELD_WITH edges (WR <-> CB). Uses MERGE for idempotent re-runs.

    Args:
        graph_db: Connected GraphDB instance.
        targeted_edges_df: Output of build_targeted_against_edges.
        cooccurrence_edges_df: Output of build_on_field_with_edges. Optional.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping WR matchup ingestion")
        return 0

    total = 0

    # --- TARGETED_AGAINST edges ---
    if not targeted_edges_df.empty:
        records = targeted_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (wr:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (def:Team {abbr: e.defteam}) "
                "MERGE (wr)-[r:TARGETED_AGAINST {season: e.season, week: e.week}]->(def) "
                "SET r.targets = e.targets, "
                "    r.catches = e.catches, "
                "    r.yards = e.yards, "
                "    r.tds = e.tds, "
                "    r.epa = e.epa, "
                "    r.air_yards = e.air_yards, "
                "    r.pass_left_rate = e.pass_left_rate, "
                "    r.pass_mid_rate = e.pass_mid_rate, "
                "    r.pass_right_rate = e.pass_right_rate",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d TARGETED_AGAINST edges", len(records))

    # --- ON_FIELD_WITH edges ---
    if cooccurrence_edges_df is not None and not cooccurrence_edges_df.empty:
        records = cooccurrence_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (wr:Player {gsis_id: e.wr_player_id}) "
                "MATCH (cb:Player {gsis_id: e.cb_player_id}) "
                "MERGE (wr)-[r:ON_FIELD_WITH {season: e.season, week: e.week}]->(cb) "
                "SET r.snap_count = e.snap_count, "
                "    r.targets_during = e.targets_during, "
                "    r.yards_during = e.yards_during",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d ON_FIELD_WITH edges", len(records))

    return total
