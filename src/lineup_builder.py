#!/usr/bin/env python3
"""
Starting Lineup Builder

Identifies likely starters for all 32 NFL teams by combining depth chart
data (official depth) with snap count data (actual usage).

Depth charts provide the "declared" starters (depth_team == 1), while snap
counts provide empirical confirmation.  When snap count data is unavailable
the module falls back to depth charts alone.
"""

import glob
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root (one level up from src/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Position groups
# ---------------------------------------------------------------------------
# Offensive skill positions relevant for fantasy / lineup display.
OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE", "K", "FB"}

# Defensive position groups we include when depth chart data is available.
DEFENSE_POSITIONS = {
    "CB",
    "LCB",
    "RCB",
    "NCB",
    "NB",
    "NKL",
    "DB",
    "NDB",
    "DE",
    "LDE",
    "RDE",
    "EDGE",
    "RUSH",
    "DT",
    "LDT",
    "RDT",
    "NT",
    "N",
    "DL",
    "LB",
    "ILB",
    "OLB",
    "MLB",
    "LILB",
    "RILB",
    "LOLB",
    "ROLB",
    "SLB",
    "WLB",
    "MIKE",
    "WILL",
    "SAM",
    "S",
    "SS",
    "FS",
}

# Map granular depth_position values to canonical groups for display.
_POS_GROUP_MAP: Dict[str, str] = {
    # Offense
    "QB": "QB",
    "RB": "RB",
    "HB": "RB",
    "FB": "FB",
    "WR": "WR",
    "PR": "WR",
    "KR": "WR",
    "KOR": "WR",
    "TE": "TE",
    "K": "K",
    "PK": "K",
    "KO": "K",
    # Defense
    "CB": "CB",
    "LCB": "CB",
    "RCB": "CB",
    "NCB": "CB",
    "NB": "CB",
    "NKL": "CB",
    "DB": "CB",
    "NDB": "CB",
    "NICKE": "CB",
    "DE": "DE",
    "LDE": "DE",
    "RDE": "DE",
    "EDGE": "DE",
    "RUSH": "DE",
    "DT": "DT",
    "LDT": "DT",
    "RDT": "DT",
    "NT": "DT",
    "N": "DT",
    "DL": "DT",
    "LB": "LB",
    "ILB": "LB",
    "OLB": "LB",
    "MLB": "LB",
    "LILB": "LB",
    "RILB": "LB",
    "LOLB": "LB",
    "ROLB": "LB",
    "SLB": "LB",
    "WLB": "LB",
    "MIKE": "LB",
    "WILL": "LB",
    "SAM": "LB",
    "OLB": "LB",
    "S": "S",
    "SS": "S",
    "FS": "S",
}

# Field-position layout labels for visual rendering.
FIELD_POSITION_MAP: Dict[str, str] = {
    "QB": "qb",
    "RB": "rb",
    "FB": "fb",
    "WR": "wr",
    "TE": "te",
    "K": "k",
    "DE": "edge",
    "DT": "dt",
    "LB": "lb",
    "CB": "cb",
    "S": "s",
}

# Offensive starter slots per position group.
OFFENSE_STARTER_SLOTS: Dict[str, int] = {
    "QB": 1,
    "RB": 2,
    "WR": 3,
    "TE": 1,
    "K": 1,
}

# Defensive starter slots per position group.
DEFENSE_STARTER_SLOTS: Dict[str, int] = {
    "DE": 2,
    "DT": 2,
    "LB": 3,
    "CB": 2,
    "S": 2,
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_depth_charts(season: int) -> pd.DataFrame:
    """Load Bronze depth chart data for the given season.

    Returns an empty DataFrame if no data is found.
    """
    dc_dir = _DATA_DIR / "bronze" / "depth_charts" / f"season={season}"
    parquets = sorted(dc_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if not parquets:
        logger.warning("No depth chart data for season=%d", season)
        return pd.DataFrame()
    df = pd.read_parquet(parquets[-1])
    logger.info(
        "Loaded depth charts: season=%d, rows=%d from %s",
        season,
        len(df),
        parquets[-1].name,
    )
    return df


def _load_snap_counts(season: int, week: int) -> pd.DataFrame:
    """Load Bronze snap count data for the given season/week.

    Returns an empty DataFrame if no data is found.
    """
    sc_dir = _DATA_DIR / "bronze" / "snap_counts" / f"season={season}" / f"week={week}"
    if not sc_dir.exists():
        # Try season-level directory (some ingestion layouts)
        sc_dir = _DATA_DIR / "bronze" / "snap_counts" / f"season={season}"
    parquets = sorted(sc_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if not parquets:
        logger.debug("No snap count data for season=%d week=%d", season, week)
        return pd.DataFrame()
    df = pd.read_parquet(parquets[-1])
    if "week" in df.columns:
        df = df[df["week"] == week]
    logger.info(
        "Loaded snap counts: season=%d week=%d, rows=%d",
        season,
        week,
        len(df),
    )
    return df


def _load_projections(season: int, week: int) -> pd.DataFrame:
    """Load Gold projections for the given season/week.

    Returns an empty DataFrame if unavailable.
    """
    proj_dir = _DATA_DIR / "gold" / "projections" / f"season={season}" / f"week={week}"
    if not proj_dir.exists():
        logger.debug("No projection data for season=%d week=%d", season, week)
        return pd.DataFrame()
    parquets = sorted(proj_dir.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if not parquets:
        return pd.DataFrame()
    df = pd.read_parquet(parquets[-1])
    logger.info("Loaded projections: season=%d week=%d, rows=%d", season, week, len(df))
    return df


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _resolve_position_group(depth_position: str, position: str) -> str:
    """Map a depth chart position to a canonical group.

    Falls back to the roster ``position`` column when depth_position
    is not recognized.
    """
    dp = str(depth_position).strip()
    if dp in _POS_GROUP_MAP:
        return _POS_GROUP_MAP[dp]
    pos = str(position).strip()
    if pos in _POS_GROUP_MAP:
        return _POS_GROUP_MAP[pos]
    return pos


def _assign_field_position(pos_group: str, rank_in_group: int) -> str:
    """Return a field-position label for visual layout.

    ``rank_in_group`` is 1-based (1 = first starter at that group).
    """
    base = FIELD_POSITION_MAP.get(pos_group, pos_group.lower())
    if pos_group == "WR":
        label_map = {1: "wr_left", 2: "wr_right", 3: "wr_slot"}
        return label_map.get(rank_in_group, f"wr_{rank_in_group}")
    if pos_group == "RB":
        if rank_in_group == 1:
            return "rb"
        return f"rb_{rank_in_group}"
    if pos_group == "DE":
        label_map = {1: "edge_left", 2: "edge_right"}
        return label_map.get(rank_in_group, f"edge_{rank_in_group}")
    if pos_group == "DT":
        label_map = {1: "dt_left", 2: "dt_right"}
        return label_map.get(rank_in_group, f"dt_{rank_in_group}")
    if pos_group == "CB":
        label_map = {1: "cb_left", 2: "cb_right"}
        return label_map.get(rank_in_group, f"cb_{rank_in_group}")
    if pos_group == "S":
        label_map = {1: "s_left", 2: "s_right"}
        return label_map.get(rank_in_group, f"s_{rank_in_group}")
    if pos_group == "LB":
        label_map = {1: "lb_left", 2: "lb_mid", 3: "lb_right"}
        return label_map.get(rank_in_group, f"lb_{rank_in_group}")
    return base


def _compute_starter_confidence(
    is_depth_starter: bool,
    snap_pct: Optional[float],
) -> float:
    """Return a 0-1 confidence score for starter designation.

    Heuristic:
      - depth_team=1 alone => 0.70
      - snap_pct >= 60% alone => 0.65
      - both => 0.85 + bonus up to 0.15 based on snap_pct
    """
    if is_depth_starter and snap_pct is not None and snap_pct >= 50:
        return min(1.0, 0.85 + (snap_pct - 50) / 333.0)
    if is_depth_starter:
        return 0.70
    if snap_pct is not None and snap_pct >= 60:
        return 0.65
    return 0.40


def get_team_starters(
    season: int,
    week: int,
    team: Optional[str] = None,
) -> pd.DataFrame:
    """Get starting lineup for all teams (or a specific team) for a given week.

    Combines depth charts (official depth) with snap counts (actual usage)
    to identify the most likely starters.

    Args:
        season: NFL season year.
        week: Week number (1-18 regular season).
        team: Optional 2/3 letter team abbreviation (e.g. ``"KC"``).

    Returns:
        DataFrame with columns:
            team, position, position_group, depth_position, player_name,
            player_id, depth_rank, snap_pct, is_starter, starter_confidence,
            field_position, side (offense / defense).
    """
    dc = _load_depth_charts(season)
    if dc.empty:
        logger.error("No depth chart data available for season=%d", season)
        return pd.DataFrame()

    # --- Filter to latest available week <= target week ---
    dc["week"] = pd.to_numeric(dc["week"], errors="coerce")
    dc = dc.dropna(subset=["week"])
    available_weeks = dc["week"].unique()
    valid_weeks = [w for w in available_weeks if w <= week]
    if not valid_weeks:
        logger.warning("No depth chart weeks <= %d for season=%d", week, season)
        return pd.DataFrame()

    # For each player, keep the row from the latest week they appear in.
    # This handles mid-season roster moves.
    dc = dc[dc["week"].isin(valid_weeks)]
    dc = dc.sort_values("week", ascending=False)
    dc = dc.drop_duplicates(subset=["club_code", "gsis_id", "position"], keep="first")

    if team:
        dc = dc[dc["club_code"] == team.upper()]
        if dc.empty:
            logger.warning("No depth chart data for team=%s", team)
            return pd.DataFrame()

    # --- Identify starters from depth chart (depth_team == '1') ---
    dc["is_depth_starter"] = dc["depth_team"].astype(str) == "1"

    # --- Load snap counts for context (optional) ---
    snap_df = _load_snap_counts(season, week)
    snap_lookup: Dict[Tuple[str, str], float] = {}
    if not snap_df.empty:
        snap_col = "offense_pct" if "offense_pct" in snap_df.columns else "snap_pct"
        if snap_col in snap_df.columns:
            team_col = "team" if "team" in snap_df.columns else "club_code"
            player_col = "player" if "player" in snap_df.columns else "full_name"
            for _, row in snap_df.iterrows():
                key = (str(row.get(team_col, "")).upper(), str(row.get(player_col, "")))
                try:
                    snap_lookup[key] = float(row[snap_col])
                except (ValueError, TypeError):
                    pass

    # --- Build result ---
    rows: List[Dict] = []
    dc["position_group"] = dc.apply(
        lambda r: _resolve_position_group(r["depth_position"], r["position"]),
        axis=1,
    )

    # Filter to offensive & defensive positions we care about
    offense_groups = set(OFFENSE_STARTER_SLOTS.keys()) | {"FB"}
    defense_groups = set(DEFENSE_STARTER_SLOTS.keys())
    all_groups = offense_groups | defense_groups
    dc = dc[dc["position_group"].isin(all_groups)]

    # Filter depth_team == 1 for starters; also keep depth_team 2 as backups
    # so we can rank within groups
    starters = dc[dc["is_depth_starter"]].copy()

    # For each team + position group, pick top N starters by depth chart
    for (club, pos_group), group_df in starters.groupby(
        ["club_code", "position_group"]
    ):
        side = "offense" if pos_group in offense_groups else "defense"
        slots_map = (
            OFFENSE_STARTER_SLOTS if side == "offense" else DEFENSE_STARTER_SLOTS
        )
        max_slots = slots_map.get(pos_group, 1)

        # Skip return specialists (PR/KR mapped to WR but with those depth_positions)
        group_df = group_df[~group_df["depth_position"].isin(["PR", "KR", "KOR"])]
        if group_df.empty:
            continue

        # Within this group, if we have snap data, sort by snap pct desc
        group_df = group_df.copy()
        group_df["_snap_pct"] = group_df.apply(
            lambda r: snap_lookup.get(
                (str(r["club_code"]).upper(), str(r["full_name"])), np.nan
            ),
            axis=1,
        )
        # Sort: prefer higher snap pct, then alphabetical for stability
        group_df = group_df.sort_values(
            ["_snap_pct", "full_name"], ascending=[False, True]
        )

        for rank, (_, row) in enumerate(group_df.head(max_slots).iterrows(), start=1):
            snap_pct_val = row["_snap_pct"] if not np.isnan(row["_snap_pct"]) else None
            confidence = _compute_starter_confidence(True, snap_pct_val)
            rows.append(
                {
                    "team": club,
                    "position": row["position"],
                    "position_group": pos_group,
                    "depth_position": row["depth_position"],
                    "player_name": row["full_name"],
                    "player_id": row.get("gsis_id", ""),
                    "depth_rank": rank,
                    "snap_pct": snap_pct_val,
                    "is_starter": True,
                    "starter_confidence": round(confidence, 2),
                    "field_position": _assign_field_position(pos_group, rank),
                    "side": side,
                }
            )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    # Sort by team, side (offense first), position group, rank
    side_order = {"offense": 0, "defense": 1}
    result["_side_ord"] = result["side"].map(side_order)
    pos_order = ["QB", "RB", "FB", "WR", "TE", "K", "DE", "DT", "LB", "CB", "S"]
    pos_rank = {p: i for i, p in enumerate(pos_order)}
    result["_pos_ord"] = result["position_group"].map(pos_rank).fillna(99)
    result = result.sort_values(["team", "_side_ord", "_pos_ord", "depth_rank"]).drop(
        columns=["_side_ord", "_pos_ord"]
    )
    result = result.reset_index(drop=True)

    return result


def get_team_lineup_with_projections(
    season: int,
    week: int,
    team: str,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Get starting lineup with fantasy projections for a specific team.

    Loads starters via :func:`get_team_starters` and joins Gold projections
    when available.

    Args:
        season: NFL season year.
        week: Week number.
        team: Team abbreviation (e.g. ``"KC"``).
        scoring_format: One of ``"ppr"``, ``"half_ppr"``, ``"standard"``.

    Returns:
        DataFrame with columns:
            team, position, position_group, field_position, player_name,
            player_id, projected_points, projected_floor, projected_ceiling,
            snap_pct, depth_rank, is_starter, starter_confidence, side.
    """
    starters = get_team_starters(season, week, team=team)
    if starters.empty:
        return starters

    proj = _load_projections(season, week)
    if proj.empty:
        starters["projected_points"] = np.nan
        starters["projected_floor"] = np.nan
        starters["projected_ceiling"] = np.nan
        return starters

    # Normalize join keys
    proj_team_col = "recent_team" if "recent_team" in proj.columns else "team"
    proj_name_col = "player_name" if "player_name" in proj.columns else "full_name"
    proj_id_col = "player_id" if "player_id" in proj.columns else None

    # Try joining on player_id first, fall back to name+team
    if proj_id_col and "player_id" in starters.columns:
        proj_subset = proj[
            [proj_id_col, "projected_points", "projected_floor", "projected_ceiling"]
        ].copy()
        proj_subset = proj_subset.rename(columns={proj_id_col: "player_id"})
        proj_subset = proj_subset.drop_duplicates(subset=["player_id"], keep="first")
        merged = starters.merge(proj_subset, on="player_id", how="left")
    else:
        proj_subset = proj[
            [
                proj_team_col,
                proj_name_col,
                "projected_points",
                "projected_floor",
                "projected_ceiling",
            ]
        ].copy()
        proj_subset = proj_subset.rename(
            columns={proj_team_col: "team", proj_name_col: "player_name"}
        )
        proj_subset = proj_subset.drop_duplicates(
            subset=["team", "player_name"], keep="first"
        )
        merged = starters.merge(proj_subset, on=["team", "player_name"], how="left")

    return merged
