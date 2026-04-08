"""TE coverage mismatch and red zone edge construction for Neo4j graph.

Builds two edge types from PBP + participation + roster data:
    1. :TE_TARGETED_AGAINST — TE aggregate stats vs each opposing defense
       with LB/safety coverage breakdown.
    2. :RED_ZONE_ROLE — TE red zone target share and scoring.

All computations use only historical data and are idempotent via MERGE.

Exports:
    build_te_coverage_edges: TE → defense coverage breakdown edges.
    build_te_red_zone_edges: TE → team red zone role edges.
    build_te_advanced_matchup_features: Additional signal from PBP columns.
    ingest_te_matchup_graph: Write edges to Neo4j.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Positions treated as linebackers for TE coverage analysis
LB_POSITIONS = {"LB", "ILB", "OLB", "MLB"}

# Positions treated as safeties for TE coverage analysis
SAFETY_POSITIONS = {"S", "SS", "FS"}

# Positions treated as cornerbacks/DBs for TE coverage analysis
CB_POSITIONS = {"CB", "DB"}

# Seam route: middle-of-field target with air yards above this threshold
SEAM_ROUTE_AIR_YARDS_THRESHOLD = 10.0

# Heavy rush threshold: TE blocking proxy when pass rushers are 5+
# We use defenders_in_box >= 7 as a proxy since number_of_pass_rushers
# is not available in the nfl-data-py PBP schema.
HEAVY_RUSH_BOX_THRESHOLD = 7

# Red zone boundary (yards from end zone)
RED_ZONE_YARDLINE = 20


# ---------------------------------------------------------------------------
# Edge construction
# ---------------------------------------------------------------------------


def build_te_coverage_edges(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build TE-vs-defense coverage breakdown edges from PBP pass plays.

    For each pass play targeting a TE, counts how many LBs and safeties
    were on the field from participation data.  Aggregates by
    (TE, defteam, season, week).

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.
        rosters_df: Roster DataFrame with player_id and position columns.

    Returns:
        DataFrame with columns: receiver_player_id, defteam, season, week,
        targets, catches, yards, tds, epa, lb_on_field_count,
        safety_on_field_count, lb_coverage_rate.
        Empty DataFrame if no TE pass plays found.
    """
    if pbp_df.empty or rosters_df.empty:
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

    # Identify TE receivers from rosters
    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )
    if not te_ids:
        return pd.DataFrame()

    passes = passes[passes["receiver_player_id"].astype(str).isin(te_ids)].copy()
    if passes.empty:
        return pd.DataFrame()

    # Ensure required columns exist with defaults
    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("touchdown", 0),
        ("epa", 0.0),
    ]:
        if col not in passes.columns:
            passes[col] = default

    # Count LBs and safeties on field per play from participation data
    lb_counts = pd.DataFrame()
    safety_counts = pd.DataFrame()

    if not participation_parsed_df.empty:
        # LBs on defense
        lb_mask = (participation_parsed_df["side"] == "defense") & (
            participation_parsed_df["position"].isin(LB_POSITIONS)
        )
        if lb_mask.any():
            lb_counts = (
                participation_parsed_df[lb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(lb_count=("player_gsis_id", "count"))
            )

        # Safeties on defense
        safety_mask = (participation_parsed_df["side"] == "defense") & (
            participation_parsed_df["position"].isin(SAFETY_POSITIONS)
        )
        if safety_mask.any():
            safety_counts = (
                participation_parsed_df[safety_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(safety_count=("player_gsis_id", "count"))
            )

    # Merge coverage counts onto passes
    if not lb_counts.empty:
        passes = passes.merge(lb_counts, on=["game_id", "play_id"], how="left")
    if "lb_count" not in passes.columns:
        passes["lb_count"] = 0
    passes["lb_count"] = passes["lb_count"].fillna(0)

    if not safety_counts.empty:
        passes = passes.merge(safety_counts, on=["game_id", "play_id"], how="left")
    if "safety_count" not in passes.columns:
        passes["safety_count"] = 0
    passes["safety_count"] = passes["safety_count"].fillna(0)

    # Aggregate by (TE, defteam, season, week)
    group_keys = ["receiver_player_id", "defteam", "season", "week"]
    agg = passes.groupby(group_keys, as_index=False).agg(
        targets=("play_id", "count"),
        catches=("complete_pass", "sum"),
        yards=("yards_gained", "sum"),
        tds=("touchdown", "sum"),
        epa=("epa", "sum"),
        lb_on_field_count=("lb_count", "sum"),
        safety_on_field_count=("safety_count", "sum"),
    )

    # Compute LB coverage rate
    total_coverage = agg["lb_on_field_count"] + agg["safety_on_field_count"]
    total_coverage = total_coverage.replace(0, 1)  # avoid div/0
    agg["lb_coverage_rate"] = agg["lb_on_field_count"] / total_coverage

    logger.info(
        "Built %d TE_TARGETED_AGAINST edges from %d TE pass plays",
        len(agg),
        len(passes),
    )
    return agg


def build_te_red_zone_edges(
    pbp_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build TE red zone role edges from PBP pass plays.

    Filters to red zone pass plays (yardline_100 <= 20) and computes
    each TE's share of their team's red zone targets.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        rosters_df: Roster DataFrame with player_id and position columns.

    Returns:
        DataFrame with columns: receiver_player_id, posteam, season, week,
        red_zone_targets, total_team_rz_targets, red_zone_target_share,
        red_zone_catches, red_zone_tds.
        Empty DataFrame if no red zone TE plays found.
    """
    if pbp_df.empty or rosters_df.empty:
        return pd.DataFrame()

    # Ensure yardline_100 exists
    if "yardline_100" not in pbp_df.columns:
        return pd.DataFrame()

    # Filter to red zone pass plays with a target
    rz_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
        & (pbp_df["yardline_100"] <= 20)
    )
    rz_passes = pbp_df[rz_mask].copy()
    if rz_passes.empty:
        return pd.DataFrame()

    # Ensure required columns exist with defaults
    for col, default in [
        ("complete_pass", 0),
        ("touchdown", 0),
    ]:
        if col not in rz_passes.columns:
            rz_passes[col] = default

    # Identify TE receivers from rosters
    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )

    # Team-level red zone targets per (posteam, season, week)
    team_col = "posteam" if "posteam" in rz_passes.columns else "home_team"
    team_rz = rz_passes.groupby([team_col, "season", "week"], as_index=False).agg(
        total_team_rz_targets=("play_id", "count"),
    )

    # Filter to TE receivers only
    te_passes = rz_passes[rz_passes["receiver_player_id"].astype(str).isin(te_ids)]
    if te_passes.empty:
        return pd.DataFrame()

    # Aggregate by (TE, team, season, week)
    group_keys = ["receiver_player_id", team_col, "season", "week"]
    agg = te_passes.groupby(group_keys, as_index=False).agg(
        red_zone_targets=("play_id", "count"),
        red_zone_catches=("complete_pass", "sum"),
        red_zone_tds=("touchdown", "sum"),
    )

    # Join team totals
    agg = agg.merge(team_rz, on=[team_col, "season", "week"], how="left")
    agg["total_team_rz_targets"] = agg["total_team_rz_targets"].fillna(1)
    agg["red_zone_target_share"] = (
        agg["red_zone_targets"] / agg["total_team_rz_targets"]
    )

    # Rename team column to standard name
    if team_col != "posteam":
        agg = agg.rename(columns={team_col: "posteam"})

    logger.info(
        "Built %d RED_ZONE_ROLE edges from %d red zone TE passes",
        len(agg),
        len(te_passes),
    )
    return agg


def build_te_advanced_matchup_features(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build advanced TE matchup features from PBP columns (no external data).

    Derives five additional signals per (receiver_player_id, defteam, season, week):

    1. **te_matchup_cb_coverage_rate**: Share of defensive backs (CB/DB) on
       field when TE is targeted, relative to total coverage defenders (CB + LB
       + S). High rate implies the defense is using CBs to cover the TE — a
       favorable matchup indicator since CBs are typically smaller than TEs.

    2. **te_matchup_seam_route_rate**: Share of TE targets that qualify as seam
       routes — middle-of-field (pass_location == 'middle') with air_yards > 10.
       High seam rate signals the TE is being used as a downfield weapon.

    3. **te_matchup_seam_completion_rate**: Completion rate on seam route
       attempts only. Strong completion rate on seams indicates the TE is
       winning against linebackers / safeties in zone.

    4. **te_matchup_rz_personnel_lb_rate**: Among TE targets inside the red zone
       (yardline_100 <= 20), the average share of LBs on the defensive field.
       High rate = TE facing linebackers in the red zone (favorable).

    5. **te_matchup_blocking_proxy_rate**: Fraction of plays where the TE
       appears in the offense participation string AND the defense has a heavy
       box (defenders_in_box >= 7), suggesting the TE was used as a blocker.
       Provides context for route-running snap separation.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.
        rosters_df: Roster DataFrame with player_id and position columns.

    Returns:
        DataFrame with columns: receiver_player_id, defteam, season, week,
        and all ``te_matchup_*`` columns listed above.
        Returns empty DataFrame if no TE pass plays are found.
    """
    if pbp_df.empty or rosters_df.empty:
        return pd.DataFrame()

    # Identify TE player IDs
    id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
    te_ids = set(
        rosters_df.loc[rosters_df["position"] == "TE", id_col].astype(str).unique()
    )
    if not te_ids:
        return pd.DataFrame()

    # Filter to pass plays targeting TEs
    pass_mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
        & pbp_df["receiver_player_id"].astype(str).isin(te_ids)
    )
    te_passes = pbp_df[pass_mask].copy()
    if te_passes.empty:
        return pd.DataFrame()

    # Ensure needed columns exist
    for col, default in [
        ("complete_pass", 0),
        ("air_yards", np.nan),
        ("pass_location", ""),
        ("yardline_100", np.nan),
        ("defenders_in_box", np.nan),
        ("game_id", ""),
    ]:
        if col not in te_passes.columns:
            te_passes[col] = default

    te_passes["air_yards"] = pd.to_numeric(te_passes["air_yards"], errors="coerce")
    te_passes["defenders_in_box"] = pd.to_numeric(
        te_passes["defenders_in_box"], errors="coerce"
    )
    te_passes["yardline_100"] = pd.to_numeric(
        te_passes["yardline_100"], errors="coerce"
    )

    # Seam route flag: middle-of-field + air_yards > threshold
    te_passes["is_seam"] = (te_passes["pass_location"] == "middle") & (
        te_passes["air_yards"] > SEAM_ROUTE_AIR_YARDS_THRESHOLD
    )

    # Red zone flag
    te_passes["is_red_zone"] = te_passes["yardline_100"].le(RED_ZONE_YARDLINE)

    # Heavy box flag (blocking proxy)
    te_passes["is_heavy_box"] = te_passes["defenders_in_box"].ge(
        HEAVY_RUSH_BOX_THRESHOLD
    )

    group_keys = ["receiver_player_id", "defteam", "season", "week"]

    # -----------------------------------------------------------------------
    # Coverage type per play from participation data
    # -----------------------------------------------------------------------
    lb_counts = pd.DataFrame()
    safety_counts = pd.DataFrame()
    cb_counts = pd.DataFrame()

    if not participation_parsed_df.empty:
        def_mask = participation_parsed_df["side"] == "defense"

        lb_mask = def_mask & participation_parsed_df["position"].isin(LB_POSITIONS)
        if lb_mask.any():
            lb_counts = (
                participation_parsed_df[lb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(lb_count=("player_gsis_id", "count"))
            )

        safety_mask = def_mask & participation_parsed_df["position"].isin(
            SAFETY_POSITIONS
        )
        if safety_mask.any():
            safety_counts = (
                participation_parsed_df[safety_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(safety_count=("player_gsis_id", "count"))
            )

        cb_mask = def_mask & participation_parsed_df["position"].isin(CB_POSITIONS)
        if cb_mask.any():
            cb_counts = (
                participation_parsed_df[cb_mask]
                .groupby(["game_id", "play_id"], as_index=False)
                .agg(cb_count=("player_gsis_id", "count"))
            )

    # Merge coverage counts onto TE pass plays
    for counts_df, col_name in [
        (lb_counts, "lb_count"),
        (safety_counts, "safety_count"),
        (cb_counts, "cb_count"),
    ]:
        if not counts_df.empty:
            te_passes = te_passes.merge(
                counts_df, on=["game_id", "play_id"], how="left"
            )
        if col_name not in te_passes.columns:
            te_passes[col_name] = np.nan
        te_passes[col_name] = te_passes[col_name].fillna(0)

    # -----------------------------------------------------------------------
    # Per-TE aggregations
    # -----------------------------------------------------------------------
    agg = te_passes.groupby(group_keys, as_index=False).agg(
        _te_targets=("play_id", "count"),
        _seam_count=("is_seam", "sum"),
        _seam_completions=(
            "complete_pass",
            lambda s: s[te_passes.loc[s.index, "is_seam"]].sum(),
        ),
        _rz_targets=("is_red_zone", "sum"),
        _rz_lb_sum=(
            "lb_count",
            lambda s: s[te_passes.loc[s.index, "is_red_zone"]].sum(),
        ),
        _rz_total_def_sum=(
            "lb_count",  # placeholder; computed below from all coverage counts
            lambda s: (
                te_passes.loc[s.index, "lb_count"]
                + te_passes.loc[s.index, "safety_count"]
                + te_passes.loc[s.index, "cb_count"]
            )[te_passes.loc[s.index, "is_red_zone"]].sum(),
        ),
        _cb_sum=("cb_count", "sum"),
        _total_coverage_sum=(
            "lb_count",
            lambda s: (
                te_passes.loc[s.index, "lb_count"]
                + te_passes.loc[s.index, "safety_count"]
                + te_passes.loc[s.index, "cb_count"]
            ).sum(),
        ),
        _heavy_box_count=("is_heavy_box", "sum"),
    )

    # -----------------------------------------------------------------------
    # Derived rates
    # -----------------------------------------------------------------------
    agg["te_matchup_cb_coverage_rate"] = np.where(
        agg["_total_coverage_sum"] > 0,
        agg["_cb_sum"] / agg["_total_coverage_sum"],
        np.nan,
    )
    agg["te_matchup_seam_route_rate"] = np.where(
        agg["_te_targets"] > 0,
        agg["_seam_count"] / agg["_te_targets"],
        np.nan,
    )
    agg["te_matchup_seam_completion_rate"] = np.where(
        agg["_seam_count"] > 0,
        agg["_seam_completions"] / agg["_seam_count"],
        np.nan,
    )
    agg["te_matchup_rz_personnel_lb_rate"] = np.where(
        agg["_rz_total_def_sum"] > 0,
        agg["_rz_lb_sum"] / agg["_rz_total_def_sum"],
        np.nan,
    )

    # -----------------------------------------------------------------------
    # Blocking proxy: requires TE in offense participation + heavy box
    # Use PBP-level heavy_box flag already on te_passes; need all TE
    # offensive snaps (not just targeted ones) for denominator.
    # Since we only have targeted plays here, we use targeted plays as proxy:
    # rate of targeted plays occurring in a heavy box context.
    # -----------------------------------------------------------------------
    agg["te_matchup_blocking_proxy_rate"] = np.where(
        agg["_te_targets"] > 0,
        agg["_heavy_box_count"] / agg["_te_targets"],
        np.nan,
    )

    # Drop intermediate columns
    drop_cols = [c for c in agg.columns if c.startswith("_")]
    agg = agg.drop(columns=drop_cols)

    logger.info(
        "Built %d advanced TE matchup feature rows from %d TE pass plays",
        len(agg),
        len(te_passes),
    )
    return agg


# ---------------------------------------------------------------------------
# Neo4j ingestion
# ---------------------------------------------------------------------------


def ingest_te_matchup_graph(
    graph_db: "GraphDB",
    coverage_edges_df: pd.DataFrame,
    rz_edges_df: Optional[pd.DataFrame] = None,
    advanced_features_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write TE matchup edges to Neo4j.

    Creates :TE_TARGETED_AGAINST edges (TE -> Team) with coverage breakdown
    and optionally :RED_ZONE_ROLE edges (TE -> Team). Uses MERGE for
    idempotent re-runs.

    Args:
        graph_db: Connected GraphDB instance.
        coverage_edges_df: Output of build_te_coverage_edges.
        rz_edges_df: Output of build_te_red_zone_edges. Optional.
        advanced_features_df: Output of build_te_advanced_matchup_features.
            When provided, advanced features are merged onto coverage edges
            before writing to Neo4j.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping TE matchup ingestion")
        return 0

    total = 0

    # --- TE_TARGETED_AGAINST edges (merge advanced features if provided) ---
    if not coverage_edges_df.empty:
        merge_keys = ["receiver_player_id", "defteam", "season", "week"]
        edges_df = coverage_edges_df.copy()

        if advanced_features_df is not None and not advanced_features_df.empty:
            adv = advanced_features_df[
                [
                    c
                    for c in advanced_features_df.columns
                    if c in merge_keys or c.startswith("te_matchup_")
                ]
            ]
            edges_df = edges_df.merge(adv, on=merge_keys, how="left")

        records = edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (te:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (def:Team {abbr: e.defteam}) "
                "MERGE (te)-[r:TE_TARGETED_AGAINST {season: e.season, week: e.week}]->(def) "
                "SET r.targets = e.targets, "
                "    r.catches = e.catches, "
                "    r.yards = e.yards, "
                "    r.tds = e.tds, "
                "    r.epa = e.epa, "
                "    r.lb_on_field_count = e.lb_on_field_count, "
                "    r.safety_on_field_count = e.safety_on_field_count, "
                "    r.lb_coverage_rate = e.lb_coverage_rate, "
                "    r.te_matchup_cb_coverage_rate = e.te_matchup_cb_coverage_rate, "
                "    r.te_matchup_seam_route_rate = e.te_matchup_seam_route_rate, "
                "    r.te_matchup_seam_completion_rate = e.te_matchup_seam_completion_rate, "
                "    r.te_matchup_rz_personnel_lb_rate = e.te_matchup_rz_personnel_lb_rate, "
                "    r.te_matchup_blocking_proxy_rate = e.te_matchup_blocking_proxy_rate",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d TE_TARGETED_AGAINST edges", len(records))

    # --- RED_ZONE_ROLE edges ---
    if rz_edges_df is not None and not rz_edges_df.empty:
        records = rz_edges_df.to_dict("records")
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            graph_db.run_write(
                "UNWIND $edges AS e "
                "MATCH (te:Player {gsis_id: e.receiver_player_id}) "
                "MATCH (tm:Team {abbr: e.posteam}) "
                "MERGE (te)-[r:RED_ZONE_ROLE {season: e.season, week: e.week}]->(tm) "
                "SET r.red_zone_targets = e.red_zone_targets, "
                "    r.total_team_rz_targets = e.total_team_rz_targets, "
                "    r.red_zone_target_share = e.red_zone_target_share, "
                "    r.red_zone_catches = e.red_zone_catches, "
                "    r.red_zone_tds = e.red_zone_tds",
                {"edges": batch},
            )
        total += len(records)
        logger.info("Ingested %d RED_ZONE_ROLE edges", len(records))

    return total
