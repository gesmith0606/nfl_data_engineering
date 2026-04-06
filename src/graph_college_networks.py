"""College-to-NFL graph features: teammate networks, coaching trees, prospect comps.

Builds three categories of college-derived features from Bronze data:
1. College teammate detection — find NFL players who shared a college program.
2. Coaching scheme familiarity — score how well a player's college scheme matches
   their current NFL team's offensive scheme.
3. Draft class prospect comparisons — connect players to historically similar
   prospects and derive ceiling/floor/bust-rate features.

All rolling/aggregate features use strict temporal lag (shift(1)) to prevent
data leakage. Pure-pandas implementation — no Neo4j required.

Exports:
    build_college_teammate_edges: Detect college teammate pairs among NFL players.
    compute_college_teammate_features: Per-player-week teammate features.
    build_coaching_scheme_edges: Map players to college/NFL scheme families.
    compute_coaching_scheme_features: Scheme familiarity scores.
    build_prospect_comparison_graph: Similarity graph from draft/combine data.
    compute_prospect_comp_features: Ceiling/floor/bust-rate from historical comps.
    COLLEGE_NETWORK_FEATURE_COLUMNS: All output feature column names.
"""

import glob
import logging
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")

# --- Output feature columns ---------------------------------------------------

COLLEGE_TEAMMATE_FEATURE_COLUMNS: List[str] = [
    "college_teammates_on_roster",
    "college_teammate_starter",
    "college_qb_familiarity",
]

COACHING_SCHEME_FEATURE_COLUMNS: List[str] = [
    "scheme_familiarity_college",
    "coaching_scheme_change",
]

PROSPECT_COMP_FEATURE_COLUMNS: List[str] = [
    "prospect_comp_ceiling",
    "prospect_comp_floor",
    "prospect_comp_median",
    "prospect_comp_bust_rate",
    "years_to_breakout_comp",
]

COLLEGE_NETWORK_FEATURE_COLUMNS: List[str] = (
    COLLEGE_TEAMMATE_FEATURE_COLUMNS
    + COACHING_SCHEME_FEATURE_COLUMNS
    + PROSPECT_COMP_FEATURE_COLUMNS
)

# --- College scheme family lookup ----------------------------------------------

# Maps college programs to offensive scheme families.
# Only the most well-known programs are listed; unlisted programs get "unknown".
_COLLEGE_SCHEME_MAP: Dict[str, str] = {
    # Air Raid
    "Texas Tech": "air_raid",
    "Washington State": "air_raid",
    "Washington St.": "air_raid",
    "USC": "air_raid",
    "Oklahoma": "air_raid",
    "Mississippi": "air_raid",
    "Ole Miss": "air_raid",
    "Houston": "air_raid",
    "Hawaii": "air_raid",
    "Western Kentucky": "air_raid",
    # Spread RPO
    "Ohio State": "spread_rpo",
    "Ohio St.": "spread_rpo",
    "Alabama": "spread_rpo",
    "Clemson": "spread_rpo",
    "Oregon": "spread_rpo",
    "LSU": "spread_rpo",
    "Georgia": "spread_rpo",
    "Penn State": "spread_rpo",
    "Penn St.": "spread_rpo",
    "Michigan State": "spread_rpo",
    "Michigan St.": "spread_rpo",
    "Texas": "spread_rpo",
    "Florida": "spread_rpo",
    "Auburn": "spread_rpo",
    "Tennessee": "spread_rpo",
    "Oklahoma State": "spread_rpo",
    "Oklahoma St.": "spread_rpo",
    # Pro-Style
    "Stanford": "pro_style",
    "Michigan": "pro_style",
    "Notre Dame": "pro_style",
    "Wisconsin": "pro_style",
    "Iowa": "pro_style",
    "Minnesota": "pro_style",
    "Arkansas": "pro_style",
    "Virginia": "pro_style",
    "Duke": "pro_style",
    "Northwestern": "pro_style",
    "Pittsburgh": "pro_style",
    # West Coast
    "BYU": "west_coast",
    "Brigham Young": "west_coast",
    "Cal": "west_coast",
    "California": "west_coast",
    "San Jose State": "west_coast",
    "San Jose St.": "west_coast",
    # Option / Triple
    "Navy": "option",
    "Army": "option",
    "Air Force": "option",
    "Georgia Southern": "option",
    "Georgia Tech": "option",
}

# NFL team scheme families — simplified mapping. In production these come from
# graph_scheme.py run scheme classification, but we hardcode defaults here to
# avoid circular dependencies and ensure fallback availability.
_NFL_SCHEME_MAP: Dict[str, str] = {
    # Spread RPO heavy
    "KC": "spread_rpo",
    "BUF": "spread_rpo",
    "MIA": "spread_rpo",
    "PHI": "spread_rpo",
    "SF": "spread_rpo",
    "CIN": "spread_rpo",
    "LAC": "spread_rpo",
    "DET": "spread_rpo",
    "HOU": "spread_rpo",
    "BAL": "spread_rpo",
    # Air Raid influenced
    "ARI": "air_raid",
    "LAR": "air_raid",
    "TB": "air_raid",
    "ATL": "air_raid",
    # Pro-Style / West Coast
    "GB": "west_coast",
    "MIN": "west_coast",
    "NYG": "pro_style",
    "WAS": "pro_style",
    "DAL": "pro_style",
    "NO": "pro_style",
    "IND": "pro_style",
    "TEN": "pro_style",
    "PIT": "pro_style",
    "DEN": "pro_style",
    "NE": "pro_style",
    "NYJ": "pro_style",
    "CHI": "pro_style",
    "CLE": "pro_style",
    "JAX": "pro_style",
    "SEA": "pro_style",
    "CAR": "pro_style",
    "LV": "pro_style",
}

# Scheme adjacency for familiarity scoring
_SCHEME_ADJACENCY: Dict[str, List[str]] = {
    "air_raid": ["spread_rpo", "west_coast"],
    "spread_rpo": ["air_raid", "west_coast"],
    "pro_style": ["west_coast"],
    "west_coast": ["pro_style", "air_raid", "spread_rpo"],
    "option": [],
    "unknown": [],
}

# Combine measurables and their normalization ranges (min, max)
_COMBINE_MEASURABLE_RANGES: Dict[str, tuple] = {
    "wt": (150.0, 350.0),
    "forty": (4.2, 5.5),
    "vertical": (20.0, 46.0),
    "broad_jump": (90.0, 140.0),
}

# Max number of historical comps per player
_MAX_COMPS = 5

# Fantasy PPG threshold for "bust" classification
_BUST_PPG_THRESHOLD = 5.0

# Overlap window: players at the same college within N years = teammates
_COLLEGE_OVERLAP_WINDOW = 4


# ---------------------------------------------------------------------------
# Bronze readers
# ---------------------------------------------------------------------------


def _read_bronze_draft_picks(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Read Bronze draft picks data.

    Args:
        seasons: List of seasons to load. None loads all available.

    Returns:
        DataFrame with draft pick data, or empty DataFrame if not found.
    """
    if seasons is None:
        pattern = os.path.join(BRONZE_DIR, "draft_picks", "season=*", "*.parquet")
        files = sorted(glob.glob(pattern))
    else:
        files = []
        for s in seasons:
            pat = os.path.join(BRONZE_DIR, "draft_picks", f"season={s}", "*.parquet")
            files.extend(sorted(glob.glob(pat)))

    if not files:
        return pd.DataFrame()

    dfs = [pd.read_parquet(f) for f in files]
    return pd.concat(dfs, ignore_index=True)


def _read_bronze_combine(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Read Bronze combine data.

    Args:
        seasons: List of seasons to load. None loads all available.

    Returns:
        DataFrame with combine data, or empty DataFrame if not found.
    """
    if seasons is None:
        pattern = os.path.join(BRONZE_DIR, "combine", "season=*", "*.parquet")
        files = sorted(glob.glob(pattern))
    else:
        files = []
        for s in seasons:
            pat = os.path.join(BRONZE_DIR, "combine", f"season={s}", "*.parquet")
            files.extend(sorted(glob.glob(pat)))

    if not files:
        return pd.DataFrame()

    dfs = [pd.read_parquet(f) for f in files]
    return pd.concat(dfs, ignore_index=True)


def _read_bronze_rosters(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Read Bronze rosters data, checking multiple directory layouts.

    Rosters may be at:
      - data/bronze/rosters/season=YYYY/*.parquet
      - data/bronze/rosters/season=YYYY/week=WW/*.parquet
      - data/bronze/players/rosters/season=YYYY/*.parquet

    Args:
        seasons: List of seasons to load. None loads all available.

    Returns:
        DataFrame with roster data, or empty DataFrame if not found.
    """
    search_roots = [
        os.path.join(BRONZE_DIR, "rosters"),
        os.path.join(BRONZE_DIR, "players", "rosters"),
    ]

    files: List[str] = []
    for root in search_roots:
        if seasons is None:
            for pattern in [
                os.path.join(root, "season=*", "*.parquet"),
                os.path.join(root, "season=*", "week=*", "*.parquet"),
            ]:
                files.extend(sorted(glob.glob(pattern)))
        else:
            for s in seasons:
                for pattern in [
                    os.path.join(root, f"season={s}", "*.parquet"),
                    os.path.join(root, f"season={s}", "week=*", "*.parquet"),
                ]:
                    files.extend(sorted(glob.glob(pattern)))

    if not files:
        return pd.DataFrame()

    dfs = [pd.read_parquet(f) for f in files]
    df = pd.concat(dfs, ignore_index=True)

    # Normalize college column name
    if "college_name" in df.columns and "college" not in df.columns:
        df = df.rename(columns={"college_name": "college"})

    return df


# ---------------------------------------------------------------------------
# 1. College Teammate Detection
# ---------------------------------------------------------------------------


def build_college_teammate_edges(
    rosters_df: pd.DataFrame,
    draft_picks_df: pd.DataFrame,
) -> pd.DataFrame:
    """Find NFL players who attended the same college at overlapping times.

    Combines roster and draft pick data to build a player-college mapping,
    then finds pairs of players who attended the same college within
    ``_COLLEGE_OVERLAP_WINDOW`` years of each other.

    Args:
        rosters_df: Roster DataFrame, may contain ``college`` or ``college_name``,
            ``player_id`` or ``gsis_id``, and ``season`` columns.
        draft_picks_df: Draft picks DataFrame with ``college``, ``gsis_id``,
            ``season``, and ``position`` columns.

    Returns:
        DataFrame with columns: player_id_a, player_id_b, college, years_overlap.
        Empty DataFrame if insufficient data.
    """
    # Build player -> college mapping from draft picks (most reliable source)
    player_college = _build_player_college_map(rosters_df, draft_picks_df)
    if player_college.empty:
        return pd.DataFrame(
            columns=["player_id_a", "player_id_b", "college", "years_overlap"]
        )

    # Group by college, find pairs within overlap window
    edges = []
    for college, group in player_college.groupby("college"):
        if len(group) < 2:
            continue
        players = group[["player_id", "draft_year"]].values
        for i in range(len(players)):
            for j in range(i + 1, len(players)):
                pid_a, year_a = players[i]
                pid_b, year_b = players[j]
                year_diff = abs(int(year_a) - int(year_b))
                if year_diff <= _COLLEGE_OVERLAP_WINDOW:
                    overlap = max(1, _COLLEGE_OVERLAP_WINDOW - year_diff + 1)
                    edges.append(
                        {
                            "player_id_a": pid_a,
                            "player_id_b": pid_b,
                            "college": college,
                            "years_overlap": overlap,
                        }
                    )

    if not edges:
        return pd.DataFrame(
            columns=["player_id_a", "player_id_b", "college", "years_overlap"]
        )

    return pd.DataFrame(edges)


def _build_player_college_map(
    rosters_df: pd.DataFrame,
    draft_picks_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a unified player_id -> college -> draft_year mapping.

    Prefers draft_picks for college info (more complete), falls back to rosters.

    Args:
        rosters_df: Roster DataFrame.
        draft_picks_df: Draft picks DataFrame.

    Returns:
        DataFrame with columns: player_id, college, draft_year, position.
    """
    records = []

    # From draft_picks: gsis_id -> college, season = draft year
    if not draft_picks_df.empty:
        dp = draft_picks_df.copy()
        # Normalize column names
        if "college_name" in dp.columns and "college" not in dp.columns:
            dp = dp.rename(columns={"college_name": "college"})

        id_col = "gsis_id" if "gsis_id" in dp.columns else None
        if id_col and "college" in dp.columns and "season" in dp.columns:
            valid = dp[[id_col, "college", "season"]].dropna(subset=[id_col, "college"])
            pos_col = "position" if "position" in dp.columns else None
            for _, row in valid.iterrows():
                rec = {
                    "player_id": row[id_col],
                    "college": row["college"],
                    "draft_year": int(row["season"]),
                }
                if pos_col and pd.notna(row.get(pos_col)):
                    rec["position"] = row[pos_col]
                records.append(rec)

    # From rosters: fill in players not in draft picks
    if not rosters_df.empty:
        ros = rosters_df.copy()
        if "college_name" in ros.columns and "college" not in ros.columns:
            ros = ros.rename(columns={"college_name": "college"})

        id_col = None
        for candidate in ["player_id", "gsis_id"]:
            if candidate in ros.columns:
                id_col = candidate
                break

        if id_col and "college" in ros.columns:
            # Use entry_year or season as proxy for draft year
            year_col = None
            for candidate in ["entry_year", "rookie_year", "season"]:
                if candidate in ros.columns:
                    year_col = candidate
                    break

            if year_col:
                valid = ros[[id_col, "college", year_col]].dropna(
                    subset=[id_col, "college"]
                )
                pos_col = "position" if "position" in ros.columns else None
                for _, row in valid.iterrows():
                    rec = {
                        "player_id": row[id_col],
                        "college": row["college"],
                        "draft_year": int(row[year_col]),
                    }
                    if pos_col and pd.notna(row.get(pos_col)):
                        rec["position"] = row[pos_col]
                    records.append(rec)

    if not records:
        return pd.DataFrame(columns=["player_id", "college", "draft_year", "position"])

    result = pd.DataFrame(records)
    # Deduplicate: keep first occurrence per player_id
    result = result.drop_duplicates(subset=["player_id"], keep="first")
    # Drop rows with empty college
    result = result[result["college"].astype(str).str.strip().str.len() > 0]
    return result.reset_index(drop=True)


def compute_college_teammate_features(
    teammate_edges_df: pd.DataFrame,
    player_college_map: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Compute per-player-week college teammate features.

    For each player in a given week, counts how many former college teammates
    are on the same NFL roster and checks QB familiarity from college.

    All features use temporal lag — based on roster state as of the prior week.

    Args:
        teammate_edges_df: Output of ``build_college_teammate_edges()``.
        player_college_map: Output of ``_build_player_college_map()``.
        player_weekly_df: Player-week DataFrame with player_id, season, week,
            recent_team, position.
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with columns: player_id, season, week, and
        COLLEGE_TEAMMATE_FEATURE_COLUMNS.
    """
    out_cols = ["player_id", "season", "week"] + COLLEGE_TEAMMATE_FEATURE_COLUMNS

    if teammate_edges_df.empty or player_weekly_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Get roster for the prior week (temporal safety)
    prior_week = week - 1
    if prior_week < 1:
        # Week 1: use previous season's last week or return NaN
        pw_df = player_weekly_df[(player_weekly_df["season"] == season - 1)]
        if not pw_df.empty:
            prior_week = pw_df["week"].max()
            pw_df = pw_df[pw_df["week"] == prior_week]
        else:
            # No prior data -- return empty features
            return pd.DataFrame(columns=out_cols)
    else:
        pw_df = player_weekly_df[
            (player_weekly_df["season"] == season)
            & (player_weekly_df["week"] == prior_week)
        ]

    if pw_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Current week players (for output rows)
    current_df = player_weekly_df[
        (player_weekly_df["season"] == season) & (player_weekly_df["week"] == week)
    ]
    if current_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Build roster lookup: player_id -> team (from prior week)
    team_col = "recent_team" if "recent_team" in pw_df.columns else "team"
    if team_col not in pw_df.columns:
        return pd.DataFrame(columns=out_cols)

    roster_lookup = dict(zip(pw_df["player_id"], pw_df[team_col]))

    # Build teammate lookup: player_id -> set of college teammate player_ids
    teammate_map: Dict[str, set] = {}
    for _, row in teammate_edges_df.iterrows():
        a, b = row["player_id_a"], row["player_id_b"]
        teammate_map.setdefault(a, set()).add(b)
        teammate_map.setdefault(b, set()).add(a)

    # Build position lookup from prior week
    pos_col = "position" if "position" in pw_df.columns else None
    pos_lookup: Dict[str, str] = {}
    if pos_col:
        pos_lookup = dict(zip(pw_df["player_id"], pw_df[pos_col]))

    # QB lookup per team (from prior week)
    qb_team: Dict[str, str] = {}  # team -> qb_player_id
    if pos_lookup:
        for pid, pos in pos_lookup.items():
            if pos == "QB" and pid in roster_lookup:
                team = roster_lookup[pid]
                qb_team[team] = pid

    # College map: player_id -> college
    college_lookup: Dict[str, str] = {}
    if not player_college_map.empty:
        college_lookup = dict(
            zip(player_college_map["player_id"], player_college_map["college"])
        )

    rows = []
    curr_team_col = "recent_team" if "recent_team" in current_df.columns else "team"
    for _, player_row in current_df.iterrows():
        pid = player_row["player_id"]
        team = player_row.get(curr_team_col)
        position = player_row.get("position", "")

        teammates_on_roster = 0
        teammate_is_starter = False
        qb_familiarity = False

        if pid in teammate_map and team:
            college_teammates = teammate_map[pid]
            # Count teammates on same NFL team (prior week roster)
            for ct_pid in college_teammates:
                ct_team = roster_lookup.get(ct_pid)
                if ct_team == team:
                    teammates_on_roster += 1
                    # Check if any teammate is a starter (proxy: appeared in data)
                    teammate_is_starter = True

            # QB familiarity: for WR/TE, check if team's QB was a college teammate
            if position in ("WR", "TE"):
                team_qb = qb_team.get(team)
                if team_qb and team_qb in college_teammates:
                    qb_familiarity = True

        rows.append(
            {
                "player_id": pid,
                "season": season,
                "week": week,
                "college_teammates_on_roster": teammates_on_roster,
                "college_teammate_starter": teammate_is_starter,
                "college_qb_familiarity": qb_familiarity,
            }
        )

    if not rows:
        return pd.DataFrame(columns=out_cols)

    result = pd.DataFrame(rows)
    # Convert booleans to int for model compatibility
    result["college_teammate_starter"] = result["college_teammate_starter"].astype(int)
    result["college_qb_familiarity"] = result["college_qb_familiarity"].astype(int)
    return result[out_cols]


# ---------------------------------------------------------------------------
# 2. Coaching Scheme Familiarity
# ---------------------------------------------------------------------------


def build_coaching_scheme_edges(
    player_college_map: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """Map each player's college scheme to their NFL team's scheme family.

    Args:
        player_college_map: Output of ``_build_player_college_map()``.
        player_weekly_df: Player-week DataFrame with player_id, recent_team,
            season, week.

    Returns:
        DataFrame with columns: player_id, season, week, college,
        college_scheme, nfl_team, nfl_scheme, scheme_match.
    """
    out_cols = [
        "player_id",
        "season",
        "week",
        "college",
        "college_scheme",
        "nfl_team",
        "nfl_scheme",
        "scheme_match",
    ]

    if player_college_map.empty or player_weekly_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Build college lookup
    college_lookup = dict(
        zip(player_college_map["player_id"], player_college_map["college"])
    )

    team_col = "recent_team" if "recent_team" in player_weekly_df.columns else "team"
    if team_col not in player_weekly_df.columns:
        return pd.DataFrame(columns=out_cols)

    rows = []
    for _, row in player_weekly_df.iterrows():
        pid = row["player_id"]
        college = college_lookup.get(pid, "")
        if not college:
            continue

        college_scheme = _COLLEGE_SCHEME_MAP.get(college, "unknown")
        nfl_team = row.get(team_col, "")
        nfl_scheme = _NFL_SCHEME_MAP.get(nfl_team, "unknown")

        # Compute scheme match score
        if college_scheme == nfl_scheme and college_scheme != "unknown":
            match_score = 1.0
        elif nfl_scheme in _SCHEME_ADJACENCY.get(college_scheme, []):
            match_score = 0.7
        elif college_scheme == "unknown" or nfl_scheme == "unknown":
            match_score = 0.5  # Unknown = neutral
        else:
            match_score = 0.4

        rows.append(
            {
                "player_id": pid,
                "season": row["season"],
                "week": row["week"],
                "college": college,
                "college_scheme": college_scheme,
                "nfl_team": nfl_team,
                "nfl_scheme": nfl_scheme,
                "scheme_match": match_score,
            }
        )

    if not rows:
        return pd.DataFrame(columns=out_cols)

    return pd.DataFrame(rows)[out_cols]


def compute_coaching_scheme_features(
    scheme_edges_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Compute per-player-week coaching scheme familiarity features.

    Features (temporal lag — uses prior week's data):
    - scheme_familiarity_college: How similar the player's college scheme is to
      their current NFL team's scheme (1.0 = same, 0.7 = adjacent, 0.4 = different).
    - coaching_scheme_change: Whether the player changed teams between seasons,
      implying a scheme change (0 or 1).

    Args:
        scheme_edges_df: Output of ``build_coaching_scheme_edges()``.
        player_weekly_df: Player-week DataFrame.
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with columns: player_id, season, week, and
        COACHING_SCHEME_FEATURE_COLUMNS.
    """
    out_cols = ["player_id", "season", "week"] + COACHING_SCHEME_FEATURE_COLUMNS

    if scheme_edges_df.empty or player_weekly_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Get scheme data for the prior week (temporal safety)
    prior_week = week - 1
    if prior_week < 1:
        prior_data = scheme_edges_df[scheme_edges_df["season"] == season - 1]
        if not prior_data.empty:
            prior_week = prior_data["week"].max()
            prior_data = prior_data[prior_data["week"] == prior_week]
    else:
        prior_data = scheme_edges_df[
            (scheme_edges_df["season"] == season)
            & (scheme_edges_df["week"] == prior_week)
        ]

    # Current week players for output
    current_df = player_weekly_df[
        (player_weekly_df["season"] == season) & (player_weekly_df["week"] == week)
    ]
    if current_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Build familiarity lookup from prior week
    familiarity_lookup: Dict[str, float] = {}
    team_lookup_prior: Dict[str, str] = {}
    if not prior_data.empty:
        for _, row in prior_data.iterrows():
            familiarity_lookup[row["player_id"]] = row["scheme_match"]
            team_lookup_prior[row["player_id"]] = row.get("nfl_team", "")

    # Detect scheme change: did player switch teams this season vs last?
    prev_season_data = scheme_edges_df[scheme_edges_df["season"] == season - 1]
    prev_team_lookup: Dict[str, str] = {}
    if not prev_season_data.empty:
        for pid, grp in prev_season_data.groupby("player_id"):
            prev_team_lookup[pid] = grp.iloc[-1].get("nfl_team", "")

    rows = []
    team_col = "recent_team" if "recent_team" in current_df.columns else "team"
    for _, row in current_df.iterrows():
        pid = row["player_id"]
        familiarity = familiarity_lookup.get(pid, np.nan)
        current_team = row.get(team_col, "")
        prev_team = prev_team_lookup.get(pid, "")

        # Scheme change = different team this season vs last
        if prev_team and current_team:
            scheme_change = 1 if current_team != prev_team else 0
        else:
            scheme_change = 0  # Unknown = assume no change

        rows.append(
            {
                "player_id": pid,
                "season": season,
                "week": week,
                "scheme_familiarity_college": familiarity,
                "coaching_scheme_change": scheme_change,
            }
        )

    if not rows:
        return pd.DataFrame(columns=out_cols)

    return pd.DataFrame(rows)[out_cols]


# ---------------------------------------------------------------------------
# 3. Draft Class Prospect Comparison
# ---------------------------------------------------------------------------


def _parse_height_inches(ht_str: object) -> float:
    """Convert height string like '6-2' to inches (74.0).

    Args:
        ht_str: Height string in feet-inches format.

    Returns:
        Height in inches, or NaN if unparseable.
    """
    if pd.isna(ht_str):
        return np.nan
    s = str(ht_str).strip()
    if "-" in s:
        parts = s.split("-")
        try:
            return float(parts[0]) * 12 + float(parts[1])
        except (ValueError, IndexError):
            return np.nan
    try:
        val = float(s)
        # If already in inches (> 48), return as-is
        return val if val > 48 else np.nan
    except ValueError:
        return np.nan


def _normalize(values: pd.Series, vmin: float, vmax: float) -> pd.Series:
    """Min-max normalize a series to [0, 1].

    Args:
        values: Input series.
        vmin: Minimum value for normalization range.
        vmax: Maximum value for normalization range.

    Returns:
        Normalized series clipped to [0, 1].
    """
    span = vmax - vmin
    if span == 0:
        return pd.Series(0.5, index=values.index)
    return ((values - vmin) / span).clip(0, 1)


def build_prospect_comparison_graph(
    draft_picks_df: pd.DataFrame,
    combine_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build similarity graph connecting players to historical prospect comps.

    For each drafted player, compute weighted euclidean distance to all prior
    drafted players at the same position using draft capital and combine
    measurables. Return the top ``_MAX_COMPS`` most similar historical players.

    Similarity components (weighted):
    - Draft position (round + overall pick): weight 0.3
    - Combine measurables (weight, 40-yard, vertical, broad jump): weight 0.5
    - Same conference bonus: weight 0.2

    Args:
        draft_picks_df: Draft picks DataFrame with position, college, season,
            round, pick, gsis_id.
        combine_df: Combine DataFrame with pfr_id, pos, wt, forty, vertical,
            broad_jump, school.
        player_weekly_df: Player-week data for computing NFL outcomes.

    Returns:
        DataFrame with columns: player_id, comp_player_id, similarity_score,
        comp_nfl_ppg, comp_best_season_ppg, comp_seasons_played.
    """
    out_cols = [
        "player_id",
        "comp_player_id",
        "similarity_score",
        "comp_nfl_ppg",
        "comp_best_season_ppg",
        "comp_seasons_played",
    ]

    if draft_picks_df.empty:
        return pd.DataFrame(columns=out_cols)

    dp = draft_picks_df.copy()

    # Standardize ID column
    id_col = "gsis_id" if "gsis_id" in dp.columns else None
    if id_col is None:
        return pd.DataFrame(columns=out_cols)

    dp = dp.dropna(subset=[id_col, "position", "season"])
    if dp.empty:
        return pd.DataFrame(columns=out_cols)

    # Normalize pick/round
    if "pick" in dp.columns:
        dp["pick_norm"] = _normalize(dp["pick"].astype(float), 1, 260)
    else:
        dp["pick_norm"] = 0.5

    if "round" in dp.columns:
        dp["round_norm"] = _normalize(dp["round"].astype(float), 1, 7)
    else:
        dp["round_norm"] = 0.5

    # Join combine data if available
    if not combine_df.empty and "pfr_id" in combine_df.columns:
        comb = combine_df.copy()
        # Parse height to inches
        if "ht" in comb.columns:
            comb["ht_inches"] = comb["ht"].apply(_parse_height_inches)

        # Normalize measurables
        for col, (vmin, vmax) in _COMBINE_MEASURABLE_RANGES.items():
            if col in comb.columns:
                comb[f"{col}_norm"] = _normalize(comb[col].astype(float), vmin, vmax)
            else:
                comb[f"{col}_norm"] = np.nan

        # Join on pfr_id
        if "pfr_player_id" in dp.columns:
            dp = dp.merge(
                comb[
                    ["pfr_id"]
                    + [
                        f"{c}_norm"
                        for c in _COMBINE_MEASURABLE_RANGES
                        if f"{c}_norm" in comb.columns
                    ]
                    + (["school"] if "school" in comb.columns else [])
                ],
                left_on="pfr_player_id",
                right_on="pfr_id",
                how="left",
                suffixes=("", "__comb"),
            )
            dp = dp.drop(columns=["pfr_id"], errors="ignore")
    else:
        for col in _COMBINE_MEASURABLE_RANGES:
            dp[f"{col}_norm"] = np.nan

    # Compute NFL outcomes per player if weekly data is available
    ppg_lookup: Dict[str, Dict[str, float]] = {}
    if not player_weekly_df.empty and "fantasy_points" in player_weekly_df.columns:
        grouped = player_weekly_df.groupby("player_id")
        for pid, grp in grouped:
            season_ppg = grp.groupby("season")["fantasy_points"].mean()
            ppg_lookup[pid] = {
                "ppg": grp["fantasy_points"].mean(),
                "best_season_ppg": season_ppg.max() if len(season_ppg) > 0 else 0.0,
                "seasons_played": int(grp["season"].nunique()),
            }

    # Build comparison graph by position
    results = []
    position_groups = dp.groupby("position")
    for pos, pos_group in position_groups:
        pos_group = pos_group.sort_values("season").reset_index(drop=True)
        if len(pos_group) < 2:
            continue

        for i in range(len(pos_group)):
            player = pos_group.iloc[i]
            pid = player[id_col]
            player_year = int(player["season"])

            # Only compare to players drafted BEFORE this player (temporal safety)
            historical = pos_group[pos_group["season"] < player_year]
            if historical.empty:
                continue

            # Compute similarity scores
            sims = []
            for j, hist in historical.iterrows():
                sim = _compute_prospect_similarity(player, hist)
                hist_pid = hist[id_col]
                nfl_outcome = ppg_lookup.get(hist_pid, {})
                sims.append(
                    {
                        "player_id": pid,
                        "comp_player_id": hist_pid,
                        "similarity_score": sim,
                        "comp_nfl_ppg": nfl_outcome.get("ppg", np.nan),
                        "comp_best_season_ppg": nfl_outcome.get(
                            "best_season_ppg", np.nan
                        ),
                        "comp_seasons_played": nfl_outcome.get("seasons_played", 0),
                    }
                )

            # Keep top N most similar
            sims.sort(key=lambda x: x["similarity_score"], reverse=True)
            results.extend(sims[:_MAX_COMPS])

    if not results:
        return pd.DataFrame(columns=out_cols)

    return pd.DataFrame(results)[out_cols]


def _compute_prospect_similarity(player: pd.Series, comp: pd.Series) -> float:
    """Compute similarity score between two prospects.

    Higher score = more similar. Range approximately [0, 1].

    Components:
    - Draft capital similarity (round + pick): weight 0.3
    - Combine measurables similarity: weight 0.5
    - Conference bonus: weight 0.2

    Args:
        player: Series for the player being compared.
        comp: Series for the historical comparison.

    Returns:
        Similarity score in [0, 1].
    """
    # Draft capital similarity (inverted distance)
    pick_diff = abs(
        float(player.get("pick_norm", 0.5)) - float(comp.get("pick_norm", 0.5))
    )
    round_diff = abs(
        float(player.get("round_norm", 0.5)) - float(comp.get("round_norm", 0.5))
    )
    draft_sim = 1.0 - (pick_diff * 0.6 + round_diff * 0.4)

    # Combine measurables similarity
    measurable_diffs = []
    for col in _COMBINE_MEASURABLE_RANGES:
        norm_col = f"{col}_norm"
        p_val = player.get(norm_col)
        c_val = comp.get(norm_col)
        if pd.notna(p_val) and pd.notna(c_val):
            measurable_diffs.append(abs(float(p_val) - float(c_val)))

    if measurable_diffs:
        combine_sim = 1.0 - (sum(measurable_diffs) / len(measurable_diffs))
    else:
        combine_sim = 0.5  # No measurables = neutral

    # Conference bonus
    player_college = str(player.get("college", "")).strip()
    comp_college = str(comp.get("college", "")).strip()
    if player_college and comp_college and player_college == comp_college:
        conf_bonus = 1.0
    elif player_college and comp_college:
        # Same conference check via scheme family as proxy
        p_scheme = _COLLEGE_SCHEME_MAP.get(player_college, "unknown")
        c_scheme = _COLLEGE_SCHEME_MAP.get(comp_college, "unknown")
        conf_bonus = 0.7 if p_scheme == c_scheme and p_scheme != "unknown" else 0.3
    else:
        conf_bonus = 0.3

    # Weighted combination
    similarity = draft_sim * 0.3 + combine_sim * 0.5 + conf_bonus * 0.2
    return float(np.clip(similarity, 0.0, 1.0))


def compute_prospect_comp_features(
    comparison_df: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Compute per-player prospect comparison features.

    Aggregates each player's historical comps into ceiling, floor, median,
    bust rate, and years-to-breakout features.

    These features are season-level (not week-level) since draft comps don't
    change week to week.

    Args:
        comparison_df: Output of ``build_prospect_comparison_graph()``.
        season: NFL season year (used for output column).

    Returns:
        DataFrame with columns: player_id, season, and
        PROSPECT_COMP_FEATURE_COLUMNS.
    """
    out_cols = ["player_id", "season"] + PROSPECT_COMP_FEATURE_COLUMNS

    if comparison_df.empty:
        return pd.DataFrame(columns=out_cols)

    # Filter to comps that have NFL outcomes
    valid = comparison_df.dropna(subset=["comp_best_season_ppg"])
    if valid.empty:
        return pd.DataFrame(columns=out_cols)

    rows = []
    for pid, group in valid.groupby("player_id"):
        ppg_values = group["comp_best_season_ppg"]
        career_ppg = group["comp_nfl_ppg"].dropna()
        seasons_played = group["comp_seasons_played"]

        ceiling = float(ppg_values.quantile(0.75)) if len(ppg_values) > 0 else np.nan
        floor = float(ppg_values.quantile(0.25)) if len(ppg_values) > 0 else np.nan
        median = float(ppg_values.median()) if len(ppg_values) > 0 else np.nan

        # Bust rate: % of comps whose career avg was below threshold
        if len(career_ppg) > 0:
            bust_rate = float((career_ppg < _BUST_PPG_THRESHOLD).mean())
        else:
            bust_rate = np.nan

        # Years to breakout: average seasons played by comps (proxy)
        if len(seasons_played) > 0:
            years_breakout = float(seasons_played.mean())
        else:
            years_breakout = np.nan

        rows.append(
            {
                "player_id": pid,
                "season": season,
                "prospect_comp_ceiling": ceiling,
                "prospect_comp_floor": floor,
                "prospect_comp_median": median,
                "prospect_comp_bust_rate": bust_rate,
                "years_to_breakout_comp": years_breakout,
            }
        )

    if not rows:
        return pd.DataFrame(columns=out_cols)

    return pd.DataFrame(rows)[out_cols]


# ---------------------------------------------------------------------------
# Convenience: compute all college network features for a season/week
# ---------------------------------------------------------------------------


def compute_all_college_features(
    draft_picks_df: pd.DataFrame,
    combine_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Compute all college network features for one season/week.

    Orchestrates teammate detection, scheme familiarity, and prospect comps,
    then merges into a single DataFrame.

    Args:
        draft_picks_df: Bronze draft picks data.
        combine_df: Bronze combine data.
        player_weekly_df: Player-week data.
        rosters_df: Bronze rosters data.
        season: NFL season year.
        week: NFL week number.

    Returns:
        DataFrame with player_id, season, week, and all
        COLLEGE_NETWORK_FEATURE_COLUMNS.
    """
    out_cols = ["player_id", "season", "week"] + COLLEGE_NETWORK_FEATURE_COLUMNS

    if player_weekly_df.empty or "season" not in player_weekly_df.columns:
        return pd.DataFrame(columns=out_cols)

    # Current week players
    current = player_weekly_df[
        (player_weekly_df["season"] == season) & (player_weekly_df["week"] == week)
    ]
    if current.empty:
        return pd.DataFrame(columns=out_cols)

    base = current[["player_id", "season", "week"]].copy()

    # 1. College teammate features
    player_college_map = _build_player_college_map(rosters_df, draft_picks_df)
    teammate_edges = build_college_teammate_edges(rosters_df, draft_picks_df)
    teammate_feats = compute_college_teammate_features(
        teammate_edges, player_college_map, player_weekly_df, season, week
    )
    if not teammate_feats.empty:
        base = base.merge(
            teammate_feats, on=["player_id", "season", "week"], how="left"
        )

    # 2. Coaching scheme features
    scheme_edges = build_coaching_scheme_edges(player_college_map, player_weekly_df)
    scheme_feats = compute_coaching_scheme_features(
        scheme_edges, player_weekly_df, season, week
    )
    if not scheme_feats.empty:
        base = base.merge(scheme_feats, on=["player_id", "season", "week"], how="left")

    # 3. Prospect comp features (season-level, no week dimension)
    comp_graph = build_prospect_comparison_graph(
        draft_picks_df, combine_df, player_weekly_df
    )
    comp_feats = compute_prospect_comp_features(comp_graph, season)
    if not comp_feats.empty:
        base = base.merge(comp_feats, on=["player_id", "season"], how="left")

    # Fill missing feature columns with NaN
    for col in COLLEGE_NETWORK_FEATURE_COLUMNS:
        if col not in base.columns:
            base[col] = np.nan

    return base[out_cols]
