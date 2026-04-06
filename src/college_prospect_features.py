"""
College prospect feature engineering for rookie NFL projections.

Computes four feature groups from college stats and draft profiles:

1. **Conference adjustment** — strength multipliers based on historical
   NFL production by conference.
2. **Prospect similarity** — find k-nearest historical comparisons using
   college stats, combine measurables, and draft capital.
3. **Scheme familiarity** — match college offensive scheme to NFL team scheme.
4. **College production features** — per-game rates, market share, breakout age.

All functions are pure compute (DataFrames in, DataFrames out).
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Conference Adjustment ─────────────────────────────────────────────────

# Default conference strength multipliers based on historical NFL draft
# and career production data.  Updated empirically; SEC and Big Ten
# produce the most NFL-calibre players.
DEFAULT_CONFERENCE_MULTIPLIERS: Dict[str, float] = {
    "SEC": 1.10,
    "Big Ten": 1.05,
    "Big 12": 1.00,
    "ACC": 1.00,
    "Pac-12": 1.00,  # Pre-2024 dissolution
    "Big East": 0.95,
    "AAC": 0.90,
    "Mountain West": 0.88,
    "Sun Belt": 0.85,
    "MAC": 0.85,
    "Conference USA": 0.83,
    "Independent": 0.90,
}

# Fallback for unknown conferences
_DEFAULT_CONFERENCE_MULT = 0.82


def compute_conference_adjustment(
    college_stats_df: pd.DataFrame,
    nfl_career_df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """Calculate per-conference strength multipliers.

    When ``nfl_career_df`` is provided, computes a data-driven multiplier
    by measuring how college players from each conference actually
    performed in the NFL (median fantasy points in first 3 seasons).
    Otherwise returns the static ``DEFAULT_CONFERENCE_MULTIPLIERS``.

    Args:
        college_stats_df: College stats with a ``conference`` column.
        nfl_career_df: Optional NFL career data with ``conference`` (from
            college), ``season``, ``draft_year``, and ``fantasy_points``.

    Returns:
        Dict mapping conference name to a multiplier (median ~1.0).
    """
    if nfl_career_df is None or nfl_career_df.empty:
        # Use static defaults
        conferences_in_data = set()
        if not college_stats_df.empty and "conference" in college_stats_df.columns:
            conferences_in_data = set(college_stats_df["conference"].dropna().unique())

        result = {}
        for conf in conferences_in_data:
            result[conf] = DEFAULT_CONFERENCE_MULTIPLIERS.get(
                conf, _DEFAULT_CONFERENCE_MULT
            )
        # Fill in any known conferences not in the data
        for conf, mult in DEFAULT_CONFERENCE_MULTIPLIERS.items():
            if conf not in result:
                result[conf] = mult

        return result

    # Data-driven: measure NFL success by college conference
    nfl = nfl_career_df.copy()
    required = {"conference", "season", "draft_year", "fantasy_points"}
    if not required.issubset(nfl.columns):
        logger.warning(
            "NFL career data missing columns for conference adjustment; "
            "using defaults"
        )
        return compute_conference_adjustment(college_stats_df, None)

    # First 3 NFL seasons only
    nfl["nfl_year"] = nfl["season"] - nfl["draft_year"]
    nfl = nfl[nfl["nfl_year"].between(0, 2)]

    conf_median = nfl.groupby("conference")["fantasy_points"].median()
    if conf_median.empty:
        return compute_conference_adjustment(college_stats_df, None)

    # Normalise so median conference = 1.0
    overall_median = conf_median.median()
    if overall_median == 0:
        return compute_conference_adjustment(college_stats_df, None)

    result = (conf_median / overall_median).to_dict()

    # Clamp to [0.70, 1.30] to avoid extreme multipliers
    result = {k: round(max(0.70, min(1.30, v)), 3) for k, v in result.items()}
    return result


# ── Prospect Similarity ──────────────────────────────────────────────────

# Feature weights for similarity computation (higher = more important)
_SIMILARITY_WEIGHTS = {
    # College production (per-game)
    "college_rush_ypg": 1.5,
    "college_rec_ypg": 1.5,
    "college_td_pg": 1.0,
    "college_rec_pg": 1.0,
    # Combine measurables
    "forty": 1.2,
    "height_inches": 0.8,
    "wt": 1.0,
    "speed_score": 1.5,
    # Draft capital
    "draft_value": 2.0,
    # Conference
    "conf_adj": 0.5,
}

# Minimum number of features that must be non-NaN for a valid comparison
_MIN_OVERLAP_FEATURES = 3


def compute_prospect_similarity(
    prospect_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    college_stats_df: Optional[pd.DataFrame] = None,
    k: int = 5,
    conference_adj: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Find the k most similar historical prospects for each new rookie.

    Similarity is computed as weighted Euclidean distance on normalised
    features (college stats, combine measurables, draft capital).

    Args:
        prospect_df: Current rookies with draft/combine info.  Expected
            columns: player_name, position, pick (draft overall), and
            optional combine fields (forty, ht/height_inches, wt,
            speed_score).
        historical_df: Historical drafted players with the same schema
            plus NFL outcome columns (e.g. ``nfl_season1_pts``).
        college_stats_df: Optional college stats to enrich both prospect
            and historical DataFrames with per-game production.
        k: Number of similar players to return per prospect.
        conference_adj: Conference multipliers from
            ``compute_conference_adjustment``.

    Returns:
        DataFrame with one row per prospect containing:
        - prospect_comp_median: median NFL outcome of k comps
        - prospect_comp_ceiling: 75th percentile of comps
        - prospect_comp_floor: 25th percentile of comps
        - comp_names: comma-separated names of the k closest comps
    """
    if prospect_df.empty or historical_df.empty:
        return pd.DataFrame()

    conf_adj = conference_adj or DEFAULT_CONFERENCE_MULTIPLIERS

    # Prepare feature vectors for both prospects and historical players
    prospect_features = _build_feature_vectors(prospect_df, college_stats_df, conf_adj)
    historical_features = _build_feature_vectors(
        historical_df, college_stats_df, conf_adj
    )

    if prospect_features.empty or historical_features.empty:
        return pd.DataFrame()

    # Get the feature columns (intersection of available features)
    feat_cols = [
        c
        for c in _SIMILARITY_WEIGHTS.keys()
        if c in prospect_features.columns and c in historical_features.columns
    ]
    if len(feat_cols) < _MIN_OVERLAP_FEATURES:
        logger.warning(
            "Only %d overlapping features — need at least %d for similarity",
            len(feat_cols),
            _MIN_OVERLAP_FEATURES,
        )
        return pd.DataFrame()

    # Normalise features using historical distribution (mean=0, std=1)
    hist_feats = historical_features[feat_cols].copy()
    means = hist_feats.mean()
    stds = hist_feats.std().replace(0, 1)  # avoid div by zero

    hist_normed = (hist_feats - means) / stds
    pros_normed = (prospect_features[feat_cols] - means) / stds

    # Weight vector
    weights = np.array([_SIMILARITY_WEIGHTS.get(c, 1.0) for c in feat_cols])

    # Determine NFL outcome column in historical data
    outcome_col = _find_outcome_column(historical_df)

    results = []
    for i, (idx, p_row) in enumerate(pros_normed.iterrows()):
        p_vec = p_row.values
        p_position = (
            prospect_features.loc[idx, "position"]
            if "position" in prospect_features.columns
            else None
        )

        # Filter historical to same position
        if p_position:
            pos_mask = historical_features["position"] == p_position
            h_normed_pos = hist_normed.loc[pos_mask]
            h_df_pos = historical_df.loc[pos_mask]
        else:
            h_normed_pos = hist_normed
            h_df_pos = historical_df

        if h_normed_pos.empty:
            continue

        # Compute weighted Euclidean distance
        h_matrix = h_normed_pos.values  # (n_historical, n_features)

        # Handle NaN: replace with 0 in distance calc, reduce weight
        p_valid = ~np.isnan(p_vec)
        h_valid = ~np.isnan(h_matrix)
        both_valid = p_valid[np.newaxis, :] & h_valid

        p_filled = np.nan_to_num(p_vec, nan=0.0)
        h_filled = np.nan_to_num(h_matrix, nan=0.0)

        diffs = h_filled - p_filled[np.newaxis, :]
        weighted_sq = (diffs**2) * (weights[np.newaxis, :] ** 2) * both_valid
        distances = np.sqrt(weighted_sq.sum(axis=1))

        # Get k nearest
        k_actual = min(k, len(distances))
        nearest_idx = np.argsort(distances)[:k_actual]
        comp_rows = h_df_pos.iloc[nearest_idx]

        # Extract outcomes
        if outcome_col and outcome_col in comp_rows.columns:
            outcomes = comp_rows[outcome_col].dropna()
        else:
            outcomes = pd.Series(dtype=float)

        # Get prospect identifier
        p_name = (
            prospect_features.loc[idx, "player_name"]
            if "player_name" in prospect_features.columns
            else f"prospect_{i}"
        )
        p_id = (
            prospect_features.loc[idx, "player_id"]
            if "player_id" in prospect_features.columns
            else None
        )

        comp_names = []
        if "player_name" in comp_rows.columns:
            comp_names = comp_rows["player_name"].tolist()

        result_row = {
            "player_name": p_name,
            "position": p_position,
            "prospect_comp_median": outcomes.median() if len(outcomes) > 0 else np.nan,
            "prospect_comp_ceiling": (
                outcomes.quantile(0.75) if len(outcomes) > 0 else np.nan
            ),
            "prospect_comp_floor": (
                outcomes.quantile(0.25) if len(outcomes) > 0 else np.nan
            ),
            "comp_names": ", ".join(str(n) for n in comp_names[:k]),
            "n_comps": len(outcomes),
        }
        if p_id is not None:
            result_row["player_id"] = p_id
        results.append(result_row)

    return pd.DataFrame(results)


def _build_feature_vectors(
    df: pd.DataFrame,
    college_stats_df: Optional[pd.DataFrame],
    conf_adj: Dict[str, float],
) -> pd.DataFrame:
    """Build a normalised feature vector DataFrame for similarity matching.

    Args:
        df: Player DataFrame with draft/combine info.
        college_stats_df: Optional college stats for production features.
        conf_adj: Conference strength multipliers.

    Returns:
        DataFrame with one row per player and feature columns.
    """
    result = df.copy()

    # Ensure height_inches exists
    if "height_inches" not in result.columns and "ht" in result.columns:
        from historical_profiles import parse_height_to_inches

        result["height_inches"] = result["ht"].apply(parse_height_to_inches)

    # Ensure speed_score exists
    if (
        "speed_score" not in result.columns
        and "wt" in result.columns
        and "forty" in result.columns
    ):
        from historical_profiles import compute_speed_score

        result["speed_score"] = compute_speed_score(result["wt"], result["forty"])

    # Draft value from Jimmy Johnson chart
    if "draft_value" not in result.columns and "pick" in result.columns:
        from historical_profiles import build_jimmy_johnson_chart

        chart = build_jimmy_johnson_chart()
        result["draft_value"] = result["pick"].map(chart)

    # Conference adjustment
    if "conference" in result.columns:
        result["conf_adj"] = (
            result["conference"].map(conf_adj).fillna(_DEFAULT_CONFERENCE_MULT)
        )
    else:
        result["conf_adj"] = _DEFAULT_CONFERENCE_MULT

    # College production features (per-game)
    if college_stats_df is not None and not college_stats_df.empty:
        college = _compute_per_game_stats(college_stats_df)
        if not college.empty:
            # Merge on player_name (fuzzy — best effort)
            merge_cols = ["player_name"]
            if "college_team" in result.columns and "college_team" in college.columns:
                merge_cols.append("college_team")

            available_merge = [
                c for c in merge_cols if c in result.columns and c in college.columns
            ]
            if available_merge:
                result = result.merge(
                    college, on=available_merge, how="left", suffixes=("", "_college")
                )

    # Rename college stat columns to match similarity weight keys
    rename_map = {
        "rushing_yards_pg": "college_rush_ypg",
        "receiving_yards_pg": "college_rec_ypg",
        "total_tds_pg": "college_td_pg",
        "receptions_pg": "college_rec_pg",
    }
    for old, new in rename_map.items():
        if old in result.columns:
            result[new] = result[old]

    return result


def _compute_per_game_stats(
    college_stats_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-game college production metrics.

    Args:
        college_stats_df: Wide-form college stats (one row per player-season).

    Returns:
        DataFrame with per-game rates.
    """
    df = college_stats_df.copy()

    # Need a games column; if not present, assume 12 (typical FBS season)
    if "games" not in df.columns:
        df["games"] = 12

    df["games"] = df["games"].fillna(12).clip(lower=1)

    per_game = pd.DataFrame()
    per_game["player_name"] = df.get("player_name")
    if "college_team" in df.columns:
        per_game["college_team"] = df["college_team"]

    if "rushing_yards" in df.columns:
        per_game["rushing_yards_pg"] = df["rushing_yards"].fillna(0) / df["games"]
    if "receiving_yards" in df.columns:
        per_game["receiving_yards_pg"] = df["receiving_yards"].fillna(0) / df["games"]
    if "receptions" in df.columns:
        per_game["receptions_pg"] = df["receptions"].fillna(0) / df["games"]

    # Total TDs per game
    td_cols = [
        c for c in ["rushing_tds", "receiving_tds", "passing_tds"] if c in df.columns
    ]
    if td_cols:
        per_game["total_tds_pg"] = df[td_cols].fillna(0).sum(axis=1) / df["games"]

    return per_game


def _find_outcome_column(df: pd.DataFrame) -> Optional[str]:
    """Find the best NFL outcome column in a historical DataFrame.

    Looks for (in priority order): nfl_season1_pts, fantasy_points,
    projected_season_points, projected_points.

    Args:
        df: Historical player DataFrame.

    Returns:
        Column name or None.
    """
    candidates = [
        "nfl_season1_pts",
        "fantasy_points",
        "projected_season_points",
        "projected_points",
    ]
    for col in candidates:
        if col in df.columns:
            return col
    return None


# ── Scheme Familiarity ────────────────────────────────────────────────────

# College offensive scheme classifications
COLLEGE_SCHEME_MAP: Dict[str, str] = {
    # Air Raid schools
    "Washington State": "air_raid",
    "Texas Tech": "air_raid",
    "Mississippi State": "air_raid",
    "Western Kentucky": "air_raid",
    "Houston": "air_raid",
    # Spread schools
    "Oregon": "spread",
    "Ohio State": "spread",
    "Oklahoma": "spread",
    "Alabama": "spread",
    "Clemson": "spread",
    "LSU": "spread",
    "USC": "spread",
    "Michigan": "spread",
    "Penn State": "spread",
    "Georgia": "spread",
    "Florida": "spread",
    "Tennessee": "spread",
    "Texas": "spread",
    "Notre Dame": "spread",
    "Miami": "spread",
    "Florida State": "spread",
    "Auburn": "spread",
    "Ole Miss": "spread",
    "Utah": "spread",
    "Washington": "spread",
    "Arizona State": "spread",
    "Oregon State": "spread",
    "UCLA": "spread",
    "Colorado": "spread",
    # Pro-style schools
    "Stanford": "pro_style",
    "Iowa": "pro_style",
    "Wisconsin": "pro_style",
    "Michigan State": "pro_style",
    "North Carolina": "pro_style",
    "Virginia": "pro_style",
    "Boston College": "pro_style",
    "Northwestern": "pro_style",
    "Vanderbilt": "pro_style",
    "Duke": "pro_style",
    "California": "pro_style",
    "Pittsburgh": "pro_style",
    # West Coast
    "Baylor": "west_coast",
    "TCU": "west_coast",
    "BYU": "west_coast",
    "San Jose State": "west_coast",
    "Fresno State": "west_coast",
    # Option / run-heavy
    "Navy": "option",
    "Army": "option",
    "Air Force": "option",
    "Georgia Tech": "option",
    "Georgia Southern": "option",
}

# NFL team scheme classifications (simplified)
NFL_SCHEME_MAP: Dict[str, str] = {
    "ARI": "spread",
    "ATL": "west_coast",
    "BAL": "spread",
    "BUF": "spread",
    "CAR": "west_coast",
    "CHI": "west_coast",
    "CIN": "spread",
    "CLE": "west_coast",
    "DAL": "spread",
    "DEN": "west_coast",
    "DET": "spread",
    "GB": "west_coast",
    "HOU": "spread",
    "IND": "west_coast",
    "JAX": "west_coast",
    "KC": "spread",
    "LA": "spread",
    "LAC": "spread",
    "LV": "spread",
    "MIA": "spread",
    "MIN": "west_coast",
    "NE": "pro_style",
    "NO": "west_coast",
    "NYG": "west_coast",
    "NYJ": "west_coast",
    "PHI": "spread",
    "PIT": "pro_style",
    "SEA": "west_coast",
    "SF": "west_coast",
    "TB": "spread",
    "TEN": "pro_style",
    "WAS": "spread",
}

# Scheme family adjacency — how similar two scheme families are
_SCHEME_ADJACENCY: Dict[Tuple[str, str], float] = {
    ("air_raid", "spread"): 0.85,
    ("spread", "west_coast"): 0.70,
    ("pro_style", "spread"): 0.55,
    ("option", "spread"): 0.40,
    ("air_raid", "west_coast"): 0.60,
    ("air_raid", "pro_style"): 0.45,
    ("air_raid", "option"): 0.30,
    ("pro_style", "west_coast"): 0.80,
    ("option", "west_coast"): 0.40,
    ("option", "pro_style"): 0.50,
}


def compute_scheme_familiarity(
    college_stats_df: pd.DataFrame,
    nfl_team_col: str = "recent_team",
    college_team_col: str = "college_team",
) -> pd.DataFrame:
    """Score how well a prospect's college scheme maps to their NFL team.

    Args:
        college_stats_df: DataFrame with ``college_team`` and NFL team
            columns. Each row is a prospect.
        nfl_team_col: Column name for the NFL team abbreviation.
        college_team_col: Column name for the college team.

    Returns:
        DataFrame with ``scheme_familiarity_score`` column added (0.0–1.0).
    """
    df = college_stats_df.copy()

    if college_team_col not in df.columns or nfl_team_col not in df.columns:
        df["scheme_familiarity_score"] = 0.5  # neutral default
        return df

    scores = []
    for _, row in df.iterrows():
        college = row.get(college_team_col)
        nfl_team = row.get(nfl_team_col)

        college_scheme = COLLEGE_SCHEME_MAP.get(college, "unknown")
        nfl_scheme = NFL_SCHEME_MAP.get(nfl_team, "unknown")

        if college_scheme == "unknown" or nfl_scheme == "unknown":
            scores.append(0.5)
        elif college_scheme == nfl_scheme:
            scores.append(1.0)
        else:
            key = tuple(sorted([college_scheme, nfl_scheme]))
            score = _SCHEME_ADJACENCY.get(key, 0.4)
            scores.append(score)

    df["scheme_familiarity_score"] = scores
    return df


# ── College Production Features ──────────────────────────────────────────


def compute_college_production_features(
    college_stats_df: pd.DataFrame,
    conference_adj: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Compute college production features for prospect evaluation.

    Features:
    - conference_adjusted_yards: total yards * conference multiplier
    - college_market_share: player's % of team's total yards
    - college_per_game_rate: yards and TDs per game
    - college_breakout_age: age at best college season (lower = better)

    Args:
        college_stats_df: Wide-form college player stats with columns
            including yards, TDs, conference, college_team.
        conference_adj: Conference multipliers. Uses defaults if None.

    Returns:
        DataFrame enriched with college production feature columns.
    """
    if college_stats_df.empty:
        return college_stats_df

    df = college_stats_df.copy()
    conf_adj = conference_adj or DEFAULT_CONFERENCE_MULTIPLIERS

    # Total yards
    yard_cols = [
        c
        for c in ["rushing_yards", "receiving_yards", "passing_yards"]
        if c in df.columns
    ]
    if yard_cols:
        df["total_yards"] = df[yard_cols].fillna(0).sum(axis=1)
    else:
        df["total_yards"] = 0.0

    # Total TDs
    td_cols = [
        c for c in ["rushing_tds", "receiving_tds", "passing_tds"] if c in df.columns
    ]
    if td_cols:
        df["total_tds"] = df[td_cols].fillna(0).sum(axis=1)
    else:
        df["total_tds"] = 0.0

    # Conference-adjusted yards
    if "conference" in df.columns:
        df["conf_multiplier"] = (
            df["conference"].map(conf_adj).fillna(_DEFAULT_CONFERENCE_MULT)
        )
    else:
        df["conf_multiplier"] = _DEFAULT_CONFERENCE_MULT

    df["conference_adjusted_yards"] = (df["total_yards"] * df["conf_multiplier"]).round(
        1
    )

    # Per-game rates
    games = df.get("games", pd.Series(12, index=df.index))
    games = games.fillna(12).clip(lower=1)
    df["college_yards_per_game"] = (df["total_yards"] / games).round(1)
    df["college_tds_per_game"] = (df["total_tds"] / games).round(2)

    # Market share: player's yards as % of team total
    if "college_team" in df.columns:
        team_totals = df.groupby("college_team")["total_yards"].transform("sum")
        df["college_market_share"] = np.where(
            team_totals > 0,
            (df["total_yards"] / team_totals * 100).round(1),
            0.0,
        )
    else:
        df["college_market_share"] = 0.0

    # Breakout age: age at best college season
    # (lower = better prospect — early breakout correlates with NFL success)
    if "season" in df.columns and "age" in df.columns:
        best_season_idx = df.groupby("player_name")["total_yards"].idxmax()
        best_ages = df.loc[best_season_idx, ["player_name", "age"]].rename(
            columns={"age": "college_breakout_age"}
        )
        df = df.merge(best_ages, on="player_name", how="left")
    elif "draft_year" in df.columns and "season" in df.columns:
        # Approximate age from draft year and season
        # Most prospects are 21-22 at draft; best season is usually draft_year - 1
        df["college_breakout_age"] = np.nan
    else:
        df["college_breakout_age"] = np.nan

    return df


# ── Integration: Build Full Prospect Profile ─────────────────────────────


def build_prospect_profile(
    prospect_df: pd.DataFrame,
    historical_df: pd.DataFrame,
    college_stats_df: Optional[pd.DataFrame] = None,
    nfl_career_df: Optional[pd.DataFrame] = None,
    k_comps: int = 5,
) -> pd.DataFrame:
    """Build a complete prospect profile combining all feature groups.

    Orchestration function that calls conference adjustment, prospect
    similarity, scheme familiarity, and college production features.

    Args:
        prospect_df: Current rookies with draft/combine info.
        historical_df: Historical drafted players with NFL outcomes.
        college_stats_df: College stats for production features.
        nfl_career_df: NFL career data for data-driven conference adj.
        k_comps: Number of comparisons per prospect.

    Returns:
        Prospect DataFrame enriched with all feature columns.
    """
    if prospect_df.empty:
        return prospect_df

    # Step 1: Conference adjustment
    empty_college = pd.DataFrame(columns=["conference"])
    cdf = college_stats_df if college_stats_df is not None else empty_college
    conf_adj = compute_conference_adjustment(cdf, nfl_career_df)

    # Step 2: Prospect similarity
    similarity_df = compute_prospect_similarity(
        prospect_df=prospect_df,
        historical_df=historical_df,
        college_stats_df=college_stats_df,
        k=k_comps,
        conference_adj=conf_adj,
    )

    # Step 3: Scheme familiarity
    result = prospect_df.copy()
    if "college_team" in result.columns and "recent_team" in result.columns:
        result = compute_scheme_familiarity(result)
    else:
        result["scheme_familiarity_score"] = 0.5

    # Step 4: Merge similarity results
    if not similarity_df.empty:
        merge_cols = ["player_name"]
        if "player_id" in result.columns and "player_id" in similarity_df.columns:
            merge_cols = ["player_id"]

        sim_cols = [
            "prospect_comp_median",
            "prospect_comp_ceiling",
            "prospect_comp_floor",
            "comp_names",
            "n_comps",
        ]
        available_sim = [c for c in sim_cols if c in similarity_df.columns]
        merge_on = [
            c for c in merge_cols if c in result.columns and c in similarity_df.columns
        ]

        if merge_on and available_sim:
            result = result.merge(
                similarity_df[merge_on + available_sim],
                on=merge_on,
                how="left",
            )

    # Fill defaults for missing similarity columns
    for col in ["prospect_comp_median", "prospect_comp_ceiling", "prospect_comp_floor"]:
        if col not in result.columns:
            result[col] = np.nan
    if "comp_names" not in result.columns:
        result["comp_names"] = ""
    if "n_comps" not in result.columns:
        result["n_comps"] = 0

    return result
