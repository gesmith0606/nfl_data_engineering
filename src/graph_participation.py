"""PBP participation parser for WR matchup and OL lineup graph edges.

Parses semicolon-delimited GSIS ID strings from ``offense_players`` and
``defense_players`` columns in nfl-data-py PBP participation data.
Cross-references with rosters and depth charts to assign positions.

Exports:
    parse_participation_players: Explode participation into per-player rows.
    identify_cbs_on_field: Filter to defensive backs (CB/DB).
    identify_ol_on_field: Filter to offensive linemen with position labels.
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Positions we treat as "cornerback / defensive back" for WR matchup
CB_POSITIONS = {"CB", "DB"}

# Positions we treat as offensive linemen
OL_POSITIONS = {"T", "G", "C", "OT", "OG", "OL"}

# Canonical OL labels in left-to-right order
OL_LABELS = ["LT", "LG", "C", "RG", "RT"]


# ---------------------------------------------------------------------------
# Participation parsing
# ---------------------------------------------------------------------------


def parse_participation_players(
    participation_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Parse semicolon-delimited player IDs into structured rows.

    Each row in the output represents one player on one play, tagged with
    side (offense/defense) and roster position.

    Args:
        participation_df: DataFrame with game_id, play_id,
            offense_players, defense_players columns.
        rosters_df: DataFrame with player_id (GSIS ID), team, position.

    Returns:
        DataFrame with columns: game_id, play_id, player_gsis_id,
        side, position. Empty DataFrame if inputs are unusable.
    """
    if participation_df.empty:
        return pd.DataFrame(
            columns=["game_id", "play_id", "player_gsis_id", "side", "position"]
        )

    rows = []
    for side_col, side_label in [
        ("offense_players", "offense"),
        ("defense_players", "defense"),
    ]:
        if side_col not in participation_df.columns:
            continue

        sub = participation_df[["game_id", "play_id", side_col]].copy()
        sub = sub.dropna(subset=[side_col])
        if sub.empty:
            continue

        # Explode semicolon-delimited IDs
        sub = sub.rename(columns={side_col: "player_gsis_id"})
        sub["player_gsis_id"] = sub["player_gsis_id"].astype(str).str.split(";")
        sub = sub.explode("player_gsis_id", ignore_index=True)
        sub["player_gsis_id"] = sub["player_gsis_id"].str.strip()
        sub = sub[sub["player_gsis_id"].str.len() > 0]
        sub["side"] = side_label
        rows.append(sub)

    if not rows:
        return pd.DataFrame(
            columns=["game_id", "play_id", "player_gsis_id", "side", "position"]
        )

    result = pd.concat(rows, ignore_index=True)

    # Cross-reference with rosters for position
    if not rosters_df.empty:
        # Normalise roster ID column
        id_col = "player_id" if "player_id" in rosters_df.columns else "gsis_id"
        pos_map = (
            rosters_df[[id_col, "position"]]
            .drop_duplicates(subset=[id_col], keep="last")
            .rename(columns={id_col: "player_gsis_id", "position": "_roster_pos"})
        )
        result = result.merge(pos_map, on="player_gsis_id", how="left")
        result["position"] = result["_roster_pos"].fillna("UNK")
        result = result.drop(columns=["_roster_pos"])
    else:
        result["position"] = "UNK"

    return result[["game_id", "play_id", "player_gsis_id", "side", "position"]]


# ---------------------------------------------------------------------------
# CB identification
# ---------------------------------------------------------------------------


def identify_cbs_on_field(
    participation_parsed_df: pd.DataFrame,
) -> pd.DataFrame:
    """Filter parsed participation to defensive CBs/DBs.

    Args:
        participation_parsed_df: Output of parse_participation_players.

    Returns:
        Subset DataFrame with only CB/DB defensive players.
    """
    if participation_parsed_df.empty:
        return participation_parsed_df

    mask = (participation_parsed_df["side"] == "defense") & (
        participation_parsed_df["position"].isin(CB_POSITIONS)
    )
    return participation_parsed_df[mask].copy()


# ---------------------------------------------------------------------------
# OL identification
# ---------------------------------------------------------------------------


def identify_ol_on_field(
    participation_parsed_df: pd.DataFrame,
    depth_charts_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Filter parsed participation to offensive linemen with position labels.

    Cross-references depth charts to assign LT/LG/C/RG/RT labels and
    starter status. If depth chart data is unavailable, returns OL players
    with generic position.

    Args:
        participation_parsed_df: Output of parse_participation_players.
        depth_charts_df: Depth chart DataFrame with gsis_id, club_code,
            position, depth_team columns. Optional.

    Returns:
        DataFrame with columns: game_id, play_id, player_gsis_id, position,
        ol_label, is_starter. Empty DataFrame if no OL found.
    """
    if participation_parsed_df.empty:
        return pd.DataFrame(
            columns=[
                "game_id",
                "play_id",
                "player_gsis_id",
                "position",
                "ol_label",
                "is_starter",
            ]
        )

    mask = (participation_parsed_df["side"] == "offense") & (
        participation_parsed_df["position"].isin(OL_POSITIONS)
    )
    ol = participation_parsed_df[mask].copy()

    if ol.empty:
        return pd.DataFrame(
            columns=[
                "game_id",
                "play_id",
                "player_gsis_id",
                "position",
                "ol_label",
                "is_starter",
            ]
        )

    # Default labels before depth chart enrichment
    ol["ol_label"] = ol["position"]
    ol["is_starter"] = False

    if depth_charts_df is not None and not depth_charts_df.empty:
        dc = depth_charts_df.copy()
        # Normalise depth chart columns
        id_col = "gsis_id" if "gsis_id" in dc.columns else "player_id"
        team_col = "club_code" if "club_code" in dc.columns else "team"

        if id_col in dc.columns and "position" in dc.columns:
            dc = dc.rename(
                columns={id_col: "player_gsis_id", "position": "dc_position"}
            )
            if team_col != "player_gsis_id":
                dc = dc.rename(columns={team_col: "dc_team"}, errors="ignore")

            # depth_team == 1 means starter
            if "depth_team" in dc.columns:
                dc["_is_starter"] = dc["depth_team"] == 1
            else:
                dc["_is_starter"] = True

            # Keep only OL positions in depth chart
            dc = dc[dc["dc_position"].isin(OL_POSITIONS | set(OL_LABELS))]

            label_map = dc[
                ["player_gsis_id", "dc_position", "_is_starter"]
            ].drop_duplicates(subset=["player_gsis_id"], keep="last")

            ol = ol.merge(label_map, on="player_gsis_id", how="left")
            ol["ol_label"] = ol["dc_position"].fillna(ol["ol_label"])
            ol["is_starter"] = ol["_is_starter"].fillna(False).astype(bool)
            ol = ol.drop(columns=["dc_position", "_is_starter"], errors="ignore")

    return ol[
        ["game_id", "play_id", "player_gsis_id", "position", "ol_label", "is_starter"]
    ]
