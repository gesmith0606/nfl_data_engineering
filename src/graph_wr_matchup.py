"""WR-vs-Defense edge construction for Neo4j graph.

Builds two edge types from PBP participation data:
    1. :TARGETED_AGAINST — WR aggregate stats vs each opposing defense.
    2. :ON_FIELD_WITH — WR-CB co-occurrence on pass plays.

All computations use only historical data and are idempotent via MERGE.

Exports:
    build_targeted_against_edges: WR → defense aggregate edges.
    build_on_field_with_edges: WR ↔ CB co-occurrence edges.
    build_wr_advanced_matchup_features: Additional signal from PBP columns.
    ingest_wr_matchup_graph: Write edges to Neo4j.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BATCH_SIZE = 500

# Air yards threshold below which pass is considered short (press coverage proxy)
SHORT_AIR_YARDS_THRESHOLD = 5.0

# defenders_in_box thresholds for coverage shell inference.
# Fewer defenders in the box implies more DBs in coverage.
LIGHT_BOX_THRESHOLD = 6  # <= 6 in box → likely Cover-2 / 2-high look
HEAVY_BOX_THRESHOLD = 7  # >= 7 in box → likely Cover-1 / man look


# ---------------------------------------------------------------------------
# Edge construction
# ---------------------------------------------------------------------------


def build_wr_advanced_matchup_features(
    pbp_df: pd.DataFrame,
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build advanced WR matchup features from PBP columns (no external data).

    Derives six additional signals per (receiver_player_id, defteam, season, week):

    1. **wr_matchup_target_concentration**: Share of team pass targets going to
       this WR against each defense. High concentration implies the WR is winning
       the matchup or being force-fed.

    2. **wr_matchup_air_yards_per_target**: Average air_yards per target vs each
       defense. High air yards suggest the WR is running deep routes and beating
       coverage downfield.

    3. **wr_matchup_completed_air_yards_per_target**: Average completed_air_yards
       (air_yards on completions only) per target. A high ratio relative to air
       yards implies the WR is finishing the route vs. press.

    4. **wr_matchup_yac_per_catch**: Average yards_after_catch on completions.
       High YAC indicates separation — the WR is getting open with room to run.

    5. **wr_matchup_light_box_epa**: Average EPA on plays where defenders_in_box
       <= 6 (light box / likely 2-high coverage shell). Measures WR effectiveness
       vs. zone.

    6. **wr_matchup_heavy_box_epa**: Average EPA on plays where defenders_in_box
       >= 7 (heavy box / likely man-coverage look). Measures WR effectiveness vs.
       man.

    7. **wr_matchup_short_pass_completion_rate**: Completion rate on passes with
       air_yards < 5. Low rate indicates the WR is facing press coverage and
       losing; high rate indicates winning against press.

    8. **wr_matchup_middle_target_rate**: Share of targets coming from the middle
       of the field (pass_location == 'middle'). Used as a slot alignment proxy.

    9. **wr_matchup_middle_epa**: EPA on middle-of-field targets only. Complements
       middle_target_rate for slot-receiver performance assessment.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        participation_parsed_df: Output of parse_participation_players.
            Used to count DBs on field (currently reserved for future expansion;
            the defenders_in_box column on PBP is used for coverage shell).

    Returns:
        DataFrame with columns: receiver_player_id, defteam, season, week,
        and all ``wr_matchup_*`` columns listed above.
        Returns empty DataFrame if no pass plays are found.
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

    # Ensure required columns exist with sensible defaults
    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("epa", 0.0),
        ("air_yards", np.nan),
        ("yards_after_catch", np.nan),
        ("pass_location", ""),
        ("defenders_in_box", np.nan),
    ]:
        if col not in passes.columns:
            passes[col] = default

    passes["air_yards"] = pd.to_numeric(passes["air_yards"], errors="coerce")
    passes["yards_after_catch"] = pd.to_numeric(
        passes["yards_after_catch"], errors="coerce"
    )
    passes["defenders_in_box"] = pd.to_numeric(
        passes["defenders_in_box"], errors="coerce"
    )

    # Completed air yards = air_yards * complete_pass (zero on incompletions)
    passes["completed_air_yards"] = passes["air_yards"] * passes["complete_pass"]

    # Coverage shell indicator columns
    passes["is_light_box"] = passes["defenders_in_box"].le(LIGHT_BOX_THRESHOLD)
    passes["is_heavy_box"] = passes["defenders_in_box"].ge(HEAVY_BOX_THRESHOLD)

    # Short pass flag (press coverage proxy)
    passes["is_short_pass"] = passes["air_yards"].lt(SHORT_AIR_YARDS_THRESHOLD)

    # Middle field flag (slot alignment proxy)
    passes["is_middle"] = passes["pass_location"] == "middle"

    group_keys = ["receiver_player_id", "defteam", "season", "week"]

    # -----------------------------------------------------------------------
    # Team-level target counts for concentration calculation
    # -----------------------------------------------------------------------
    team_targets = passes.groupby(
        ["posteam", "defteam", "season", "week"], as_index=False
    ).agg(team_targets=("play_id", "count"))

    # -----------------------------------------------------------------------
    # Per-WR aggregations
    # -----------------------------------------------------------------------
    agg = passes.groupby(group_keys, as_index=False).agg(
        _wr_targets=("play_id", "count"),
        _catches=("complete_pass", "sum"),
        _air_yards_sum=("air_yards", "sum"),
        _completed_air_yards_sum=("completed_air_yards", "sum"),
        _yac_sum=("yards_after_catch", "sum"),
        _yac_count=("yards_after_catch", "count"),
        _light_box_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_light_box"]].sum(),
        ),
        _light_box_count=("is_light_box", "sum"),
        _heavy_box_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_heavy_box"]].sum(),
        ),
        _heavy_box_count=("is_heavy_box", "sum"),
        _short_pass_completions=(
            "complete_pass",
            lambda s: s[passes.loc[s.index, "is_short_pass"]].sum(),
        ),
        _short_pass_count=("is_short_pass", "sum"),
        _middle_count=("is_middle", "sum"),
        _middle_epa_sum=(
            "epa",
            lambda s: s[passes.loc[s.index, "is_middle"]].sum(),
        ),
    )

    # -----------------------------------------------------------------------
    # Derived rates — all guarded against division by zero
    # -----------------------------------------------------------------------
    agg["wr_matchup_air_yards_per_target"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_air_yards_sum"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_completed_air_yards_per_target"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_completed_air_yards_sum"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_yac_per_catch"] = np.where(
        agg["_catches"] > 0,
        agg["_yac_sum"] / agg["_catches"],
        np.nan,
    )
    agg["wr_matchup_light_box_epa"] = np.where(
        agg["_light_box_count"] > 0,
        agg["_light_box_epa_sum"] / agg["_light_box_count"],
        np.nan,
    )
    agg["wr_matchup_heavy_box_epa"] = np.where(
        agg["_heavy_box_count"] > 0,
        agg["_heavy_box_epa_sum"] / agg["_heavy_box_count"],
        np.nan,
    )
    agg["wr_matchup_short_pass_completion_rate"] = np.where(
        agg["_short_pass_count"] > 0,
        agg["_short_pass_completions"] / agg["_short_pass_count"],
        np.nan,
    )
    agg["wr_matchup_middle_target_rate"] = np.where(
        agg["_wr_targets"] > 0,
        agg["_middle_count"] / agg["_wr_targets"],
        np.nan,
    )
    agg["wr_matchup_middle_epa"] = np.where(
        agg["_middle_count"] > 0,
        agg["_middle_epa_sum"] / agg["_middle_count"],
        np.nan,
    )

    # -----------------------------------------------------------------------
    # Target concentration: need posteam for the WR — join via PBP directly
    # -----------------------------------------------------------------------
    wr_posteam = passes[group_keys + ["posteam"]].drop_duplicates(
        subset=group_keys, keep="last"
    )
    agg = agg.merge(wr_posteam, on=group_keys, how="left")
    agg = agg.merge(
        team_targets, on=["posteam", "defteam", "season", "week"], how="left"
    )
    agg["wr_matchup_target_concentration"] = np.where(
        agg["team_targets"].gt(0),
        agg["_wr_targets"] / agg["team_targets"],
        np.nan,
    )

    # Drop intermediate columns
    drop_cols = [
        c for c in agg.columns if c.startswith("_") or c in ("posteam", "team_targets")
    ]
    agg = agg.drop(columns=drop_cols)

    logger.info(
        "Built %d advanced WR matchup feature rows from %d pass plays",
        len(agg),
        len(passes),
    )
    return agg


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
    advanced_features_df: Optional[pd.DataFrame] = None,
) -> int:
    """Write WR matchup edges to Neo4j.

    Creates :TARGETED_AGAINST edges (WR -> Team) and optionally
    :ON_FIELD_WITH edges (WR <-> CB) and :WR_ADVANCED_MATCHUP edges.
    Uses MERGE for idempotent re-runs.

    Args:
        graph_db: Connected GraphDB instance.
        targeted_edges_df: Output of build_targeted_against_edges.
        cooccurrence_edges_df: Output of build_on_field_with_edges. Optional.
        advanced_features_df: Output of build_wr_advanced_matchup_features.
            Optional. Merged onto TARGETED_AGAINST edges when provided.

    Returns:
        Total number of edges written.
    """
    if not graph_db.is_connected:
        logger.warning("Neo4j not connected -- skipping WR matchup ingestion")
        return 0

    total = 0

    # --- TARGETED_AGAINST edges (merge advanced features if provided) ---
    if not targeted_edges_df.empty:
        merge_keys = ["receiver_player_id", "defteam", "season", "week"]
        edges_df = targeted_edges_df.copy()

        if advanced_features_df is not None and not advanced_features_df.empty:
            adv = advanced_features_df[
                [
                    c
                    for c in advanced_features_df.columns
                    if c in merge_keys or c.startswith("wr_matchup_")
                ]
            ]
            edges_df = edges_df.merge(adv, on=merge_keys, how="left")

        records = edges_df.to_dict("records")
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
                "    r.pass_right_rate = e.pass_right_rate, "
                "    r.wr_matchup_target_concentration = e.wr_matchup_target_concentration, "
                "    r.wr_matchup_air_yards_per_target = e.wr_matchup_air_yards_per_target, "
                "    r.wr_matchup_completed_air_yards_per_target = e.wr_matchup_completed_air_yards_per_target, "
                "    r.wr_matchup_yac_per_catch = e.wr_matchup_yac_per_catch, "
                "    r.wr_matchup_light_box_epa = e.wr_matchup_light_box_epa, "
                "    r.wr_matchup_heavy_box_epa = e.wr_matchup_heavy_box_epa, "
                "    r.wr_matchup_short_pass_completion_rate = e.wr_matchup_short_pass_completion_rate, "
                "    r.wr_matchup_middle_target_rate = e.wr_matchup_middle_target_rate, "
                "    r.wr_matchup_middle_epa = e.wr_matchup_middle_epa",
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
