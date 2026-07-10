"""Player correlation network — stacking & lineup covariance (UC3).

Everything graph-side before this fed point estimates; the lineup builder
and floor/ceiling bands treat players as independent. Fantasy outcomes are
not: a QB and his WR1 spike together, two backs in one backfield split a
fixed pie, and opposing QBs correlate through game environment. This
module computes those covariances as CORRELATES edges from historical
weekly fantasy points (2016-2025) and serves them as a product surface —
stack bonuses and shared-ceiling warnings — NOT as model features, so it
carries no projection-model risk.

Structural pairs only (all-pairs correlation mining overfits and is
uninterpretable):
    qb_stack:       QB <-> same-team WR/TE
    same_backfield: RB <-> same-team RB
    wr_teammates:   WR <-> same-team WR (target competition)
    game_stack:     QB <-> opposing QB (game environment / shootouts)

Stability gate (pre-registered in .planning/GRAPH_USECASES_2026_07.md):
an edge is served only when its correlation sign on 2016-2022 holds on
2023-2025 with minimum shared-game counts in each window. Relation-level
pooled priors (for pairs without individual history, e.g. a brand-new
stack) pass the same gate.

Graph model (Neo4j optional, pure-pandas primary):
    (:Player)-[:CORRELATES {rho, n_games, relation}]->(:Player)

Exports:
    CORRELATION_RELATIONS: The four structural relation types.
    compute_weekly_points: Player-week fantasy points from Bronze weekly.
    build_pair_observations: Shared-game point pairs per structural relation.
    compute_correlation_edges: Gated pair edges + relation priors.
    build_correlation_data: Load Bronze 2016-2025 and compute everything.
    compute_stack_insights: Lineup-facing pair insights for a player set.
"""

import glob
import logging
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from scoring_calculator import calculate_fantasy_points_df
except ImportError:  # pragma: no cover
    from src.scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
GOLD_CORRELATIONS_DIR = os.path.join(BASE_DIR, "data", "gold", "correlations")

CORRELATION_RELATIONS = [
    "qb_stack",
    "same_backfield",
    "wr_teammates",
    "game_stack",
]

# Stability-gate windows (pre-registered).
TRAIN_SEASONS = list(range(2016, 2023))  # 2016-2022
HOLDOUT_SEASONS = list(range(2023, 2026))  # 2023-2025

# Minimum shared games for a pair edge to be evaluated in each window.
MIN_GAMES_TRAIN = 8
MIN_GAMES_HOLDOUT = 4

# Minimum shared games for a pair to contribute an observation to the
# relation-level pooled prior.
MIN_GAMES_PRIOR_PAIR = 4

# Lineup insights: pairs below this |rho| are noise, not a story.
MIN_INSIGHT_RHO = 0.10

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}

EDGE_COLUMNS = [
    "level",  # 'pair' or 'relation'
    "relation",
    "player_id_a",
    "player_id_b",
    "player_name_a",
    "player_name_b",
    "rho",
    "n_games",
    "rho_train",
    "n_train",
    "rho_holdout",
    "n_holdout",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _read_bronze_weekly(season: int) -> pd.DataFrame:
    """Read latest Bronze player_weekly parquet for a season.

    Args:
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if no files exist.
    """
    pattern = os.path.join(
        BRONZE_DIR, "players", "weekly", f"season={season}", "*.parquet"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        pattern_w = os.path.join(
            BRONZE_DIR, "players", "weekly", f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            return pd.concat([pd.read_parquet(f) for f in files_w], ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------


def compute_weekly_points(
    weekly_df: pd.DataFrame, scoring_format: str = "half_ppr"
) -> pd.DataFrame:
    """Per player-week fantasy points from Bronze weekly stats.

    Args:
        weekly_df: Bronze player_weekly (any seasons) with player_id,
            player_name, position, recent_team, opponent_team, season, week.
        scoring_format: Fantasy scoring format.

    Returns:
        DataFrame with player_id, player_name, position, team, opponent,
        season, week, points. Regular-season skill positions only.
    """
    out_cols = [
        "player_id",
        "player_name",
        "position",
        "team",
        "opponent",
        "season",
        "week",
        "points",
    ]
    if weekly_df.empty:
        return pd.DataFrame(columns=out_cols)

    df = weekly_df.copy()
    if "week" in df.columns:
        df = df[df["week"] <= 18]
    df = df[df["position"].isin(SKILL_POSITIONS)]
    if df.empty:
        return pd.DataFrame(columns=out_cols)

    df = calculate_fantasy_points_df(
        df, scoring_format=scoring_format, output_col="points"
    )

    df = df.rename(columns={"recent_team": "team", "opponent_team": "opponent"})
    if "team" not in df.columns:
        logger.warning("Weekly data missing recent_team/team — no pairs possible")
        return pd.DataFrame(columns=out_cols)
    if "opponent" not in df.columns:
        df["opponent"] = np.nan
    if "player_name" not in df.columns:
        df["player_name"] = df["player_id"]

    return df[out_cols].reset_index(drop=True)


def _same_team_pairs(points_df: pd.DataFrame) -> pd.DataFrame:
    """Shared-game observations for same-team structural pairs.

    Args:
        points_df: Output of compute_weekly_points.

    Returns:
        DataFrame with player_id_a/b, player_name_a/b, relation, season,
        week, points_a, points_b. IDs ordered a < b so pairs deduplicate.
    """
    cols = ["player_id", "player_name", "position", "team", "season", "week", "points"]
    base = points_df[cols]
    merged = base.merge(
        base,
        on=["team", "season", "week"],
        suffixes=("_a", "_b"),
    )
    merged = merged[merged["player_id_a"] < merged["player_id_b"]]

    pos_a, pos_b = merged["position_a"], merged["position_b"]
    conditions = [
        ((pos_a == "QB") & pos_b.isin({"WR", "TE"}))
        | ((pos_b == "QB") & pos_a.isin({"WR", "TE"})),
        (pos_a == "RB") & (pos_b == "RB"),
        (pos_a == "WR") & (pos_b == "WR"),
    ]
    labels = ["qb_stack", "same_backfield", "wr_teammates"]
    merged["relation"] = np.select(conditions, labels, default="")
    merged = merged[merged["relation"] != ""]

    return merged[
        [
            "player_id_a",
            "player_id_b",
            "player_name_a",
            "player_name_b",
            "relation",
            "season",
            "week",
            "points_a",
            "points_b",
        ]
    ]


def _game_stack_pairs(points_df: pd.DataFrame) -> pd.DataFrame:
    """Shared-game observations for opposing-QB pairs.

    Args:
        points_df: Output of compute_weekly_points.

    Returns:
        Same schema as _same_team_pairs with relation='game_stack'.
    """
    qbs = points_df[points_df["position"] == "QB"][
        ["player_id", "player_name", "team", "opponent", "season", "week", "points"]
    ]
    if qbs.empty:
        return pd.DataFrame(
            columns=[
                "player_id_a",
                "player_id_b",
                "player_name_a",
                "player_name_b",
                "relation",
                "season",
                "week",
                "points_a",
                "points_b",
            ]
        )

    merged = qbs.merge(
        qbs,
        left_on=["opponent", "season", "week"],
        right_on=["team", "season", "week"],
        suffixes=("_a", "_b"),
    )
    # Keep true head-to-head rows and dedup the mirrored pair.
    merged = merged[merged["team_a"] == merged["opponent_b"]]
    merged = merged[merged["player_id_a"] < merged["player_id_b"]]
    merged["relation"] = "game_stack"

    return merged[
        [
            "player_id_a",
            "player_id_b",
            "player_name_a",
            "player_name_b",
            "relation",
            "season",
            "week",
            "points_a",
            "points_b",
        ]
    ]


def build_pair_observations(points_df: pd.DataFrame) -> pd.DataFrame:
    """All structural pair observations (one row per pair per shared game).

    Args:
        points_df: Output of compute_weekly_points.

    Returns:
        Concatenated same-team and game-stack observations.
    """
    if points_df.empty:
        return pd.DataFrame(
            columns=[
                "player_id_a",
                "player_id_b",
                "player_name_a",
                "player_name_b",
                "relation",
                "season",
                "week",
                "points_a",
                "points_b",
            ]
        )
    return pd.concat(
        [_same_team_pairs(points_df), _game_stack_pairs(points_df)],
        ignore_index=True,
    )


def _pair_rho(obs: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation per (pair, relation) over shared games.

    Args:
        obs: Pair observations (points_a, points_b per shared game).

    Returns:
        DataFrame keyed (player_id_a, player_id_b, relation) with rho and
        n_games. Pairs with < 3 games or zero variance are dropped (rho
        undefined). The 3-game floor is only a numerical-validity minimum
        (a 2-point correlation is always ±1); the real serving thresholds
        are MIN_GAMES_TRAIN / MIN_GAMES_HOLDOUT, applied by the gate in
        compute_correlation_edges.
    """
    keys = ["player_id_a", "player_id_b", "relation"]
    if obs.empty:
        return pd.DataFrame(columns=keys + ["rho", "n_games"])

    # Vectorized Pearson via sufficient statistics — no per-group apply.
    df = obs[keys + ["points_a", "points_b"]].copy()
    df["ab"] = df["points_a"] * df["points_b"]
    df["a2"] = df["points_a"] ** 2
    df["b2"] = df["points_b"] ** 2
    agg = df.groupby(keys, as_index=False).agg(
        n_games=("ab", "size"),
        sum_a=("points_a", "sum"),
        sum_b=("points_b", "sum"),
        sum_ab=("ab", "sum"),
        sum_a2=("a2", "sum"),
        sum_b2=("b2", "sum"),
    )
    n = agg["n_games"]
    cov = agg["sum_ab"] - agg["sum_a"] * agg["sum_b"] / n
    var_a = agg["sum_a2"] - agg["sum_a"] ** 2 / n
    var_b = agg["sum_b2"] - agg["sum_b"] ** 2 / n
    denom = np.sqrt(var_a.clip(lower=0) * var_b.clip(lower=0))
    with np.errstate(divide="ignore", invalid="ignore"):
        agg["rho"] = np.where(denom > 0, cov / denom, np.nan)

    result = agg[(agg["n_games"] >= 3) & agg["rho"].notna()]
    return result[keys + ["rho", "n_games"]].reset_index(drop=True)


def compute_correlation_edges(obs: pd.DataFrame) -> pd.DataFrame:
    """Stability-gated pair edges plus relation-level pooled priors.

    Pair edges: rho on TRAIN_SEASONS (>= MIN_GAMES_TRAIN shared games) must
    hold sign on HOLDOUT_SEASONS (>= MIN_GAMES_HOLDOUT). Served rho is
    computed over all games.

    Relation priors: n-weighted mean of per-pair rhos (pairs with >=
    MIN_GAMES_PRIOR_PAIR games per window), same sign-stability gate.

    Args:
        obs: Output of build_pair_observations across all seasons.

    Returns:
        DataFrame with EDGE_COLUMNS: level='pair' rows for stable pairs,
        level='relation' rows for stable pooled priors.
    """
    if obs.empty:
        return pd.DataFrame(columns=EDGE_COLUMNS)

    keys = ["player_id_a", "player_id_b", "relation"]
    train_obs = obs[obs["season"].isin(TRAIN_SEASONS)]
    hold_obs = obs[obs["season"].isin(HOLDOUT_SEASONS)]

    rho_train = _pair_rho(train_obs).rename(
        columns={"rho": "rho_train", "n_games": "n_train"}
    )
    rho_hold = _pair_rho(hold_obs).rename(
        columns={"rho": "rho_holdout", "n_games": "n_holdout"}
    )
    rho_full = _pair_rho(obs)

    names = obs.drop_duplicates(subset=keys)[keys + ["player_name_a", "player_name_b"]]

    # --- Pair edges ---
    pairs = (
        rho_full.merge(rho_train, on=keys, how="left")
        .merge(rho_hold, on=keys, how="left")
        .merge(names, on=keys, how="left")
    )
    gated = pairs[
        (pairs["n_train"].fillna(0) >= MIN_GAMES_TRAIN)
        & (pairs["n_holdout"].fillna(0) >= MIN_GAMES_HOLDOUT)
        & (np.sign(pairs["rho_train"]) == np.sign(pairs["rho_holdout"]))
        & (pairs["rho_train"] != 0)
    ].copy()
    gated["level"] = "pair"

    # --- Relation-level pooled priors ---
    prior_rows: List[Dict[str, object]] = []
    for relation in CORRELATION_RELATIONS:
        rel_train = rho_train[
            (rho_train["relation"] == relation)
            & (rho_train["n_train"] >= MIN_GAMES_PRIOR_PAIR)
        ]
        rel_hold = rho_hold[
            (rho_hold["relation"] == relation)
            & (rho_hold["n_holdout"] >= MIN_GAMES_PRIOR_PAIR)
        ]
        rel_full = rho_full[
            (rho_full["relation"] == relation)
            & (rho_full["n_games"] >= MIN_GAMES_PRIOR_PAIR)
        ]
        if rel_train.empty or rel_hold.empty or rel_full.empty:
            continue

        def _pooled(df: pd.DataFrame, rho_col: str, n_col: str) -> float:
            return float(np.average(df[rho_col], weights=df[n_col]))

        p_train = _pooled(rel_train, "rho_train", "n_train")
        p_hold = _pooled(rel_hold, "rho_holdout", "n_holdout")
        if np.sign(p_train) != np.sign(p_hold) or p_train == 0:
            logger.info(
                "Relation prior %s failed stability gate "
                "(train %.3f vs holdout %.3f) — not served",
                relation,
                p_train,
                p_hold,
            )
            continue

        prior_rows.append(
            {
                "level": "relation",
                "relation": relation,
                "player_id_a": None,
                "player_id_b": None,
                "player_name_a": None,
                "player_name_b": None,
                "rho": round(_pooled(rel_full, "rho", "n_games"), 4),
                "n_games": int(rel_full["n_games"].sum()),
                "rho_train": round(p_train, 4),
                "n_train": int(rel_train["n_train"].sum()),
                "rho_holdout": round(p_hold, 4),
                "n_holdout": int(rel_hold["n_holdout"].sum()),
            }
        )

    gated["rho"] = gated["rho"].round(4)
    gated["rho_train"] = gated["rho_train"].round(4)
    gated["rho_holdout"] = gated["rho_holdout"].round(4)
    gated[["n_train", "n_holdout"]] = gated[["n_train", "n_holdout"]].astype(int)

    edges = pd.concat(
        [gated[EDGE_COLUMNS], pd.DataFrame(prior_rows, columns=EDGE_COLUMNS)],
        ignore_index=True,
    )
    logger.info(
        "Correlation edges: %d stable pairs (of %d candidates), %d relation priors",
        int((edges["level"] == "pair").sum()),
        len(pairs),
        int((edges["level"] == "relation").sum()),
    )
    return edges


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_correlation_data(
    seasons: Optional[List[int]] = None,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Load Bronze weekly data and compute the full correlation edge set.

    Args:
        seasons: Seasons to pool. Defaults to TRAIN_SEASONS + HOLDOUT_SEASONS
            (2016-2025).
        scoring_format: Fantasy scoring format for the point series.

    Returns:
        Edge DataFrame from compute_correlation_edges. Empty when no
        Bronze weekly data is found.
    """
    seasons = seasons or (TRAIN_SEASONS + HOLDOUT_SEASONS)
    frames = []
    for s in seasons:
        df = _read_bronze_weekly(s)
        if not df.empty:
            if "season" not in df.columns:
                df["season"] = s
            frames.append(df)
    if not frames:
        logger.warning("No Bronze weekly data for seasons %s", seasons)
        return pd.DataFrame(columns=EDGE_COLUMNS)

    weekly = pd.concat(frames, ignore_index=True)
    points = compute_weekly_points(weekly, scoring_format=scoring_format)
    obs = build_pair_observations(points)
    return compute_correlation_edges(obs)


def load_latest_correlations() -> pd.DataFrame:
    """Read the latest saved Gold correlation edges parquet.

    Returns:
        Edge DataFrame, or empty DataFrame if none has been built.
    """
    files = sorted(
        glob.glob(os.path.join(GOLD_CORRELATIONS_DIR, "correlations_*.parquet"))
    )
    return pd.read_parquet(files[-1]) if files else pd.DataFrame(columns=EDGE_COLUMNS)


# ---------------------------------------------------------------------------
# Lineup-facing insights
# ---------------------------------------------------------------------------


def compute_stack_insights(
    player_ids: List[str],
    edges_df: Optional[pd.DataFrame] = None,
) -> List[Dict[str, object]]:
    """Correlation insights for a set of players (a lineup or roster).

    Args:
        player_ids: Player IDs in the lineup.
        edges_df: Optional pre-loaded edge DataFrame; defaults to the
            latest saved Gold correlations.

    Returns:
        List of dicts (one per pair present in the lineup with
        |rho| >= MIN_INSIGHT_RHO), each with player ids/names, relation,
        rho, n_games, and insight type: 'stack_bonus' for positive rho,
        'shared_ceiling_warning' for negative. Sorted by |rho| descending.
    """
    if edges_df is None:
        edges_df = load_latest_correlations()
    if edges_df.empty or not player_ids:
        return []

    ids = set(str(p) for p in player_ids)
    pairs = edges_df[
        (edges_df["level"] == "pair")
        & edges_df["player_id_a"].isin(ids)
        & edges_df["player_id_b"].isin(ids)
        & (edges_df["rho"].abs() >= MIN_INSIGHT_RHO)
    ].copy()
    if pairs.empty:
        return []

    pairs["abs_rho"] = pairs["rho"].abs()
    pairs = pairs.sort_values("abs_rho", ascending=False)

    insights = []
    for _, row in pairs.iterrows():
        insights.append(
            {
                "player_id_a": str(row["player_id_a"]),
                "player_id_b": str(row["player_id_b"]),
                "player_name_a": str(row["player_name_a"]),
                "player_name_b": str(row["player_name_b"]),
                "relation": str(row["relation"]),
                "rho": float(row["rho"]),
                "n_games": int(row["n_games"]),
                "insight": (
                    "stack_bonus" if row["rho"] > 0 else "shared_ceiling_warning"
                ),
            }
        )
    return insights
