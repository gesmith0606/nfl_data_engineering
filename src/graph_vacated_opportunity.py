"""Vacated opportunity network — offseason roster churn features (UC1).

Models the season-to-season redistribution of usage that
``graph_injury_cascade.py`` models in-season: free agency departures,
trades, cuts, and retirements vacate target/carry share; incumbents,
arrivals, and drafted rookies compete to absorb it.

For a target season N, only season N-1 usage plus season N roster /
depth-chart / draft data are used — every feature is knowable before
week 1 of season N, so there is no leakage into preseason projections.

Graph model (Neo4j optional, pure-pandas primary):
    (:Player)-[:VACATED {target_share, carry_share}]->(:Team)
    (:Player)-[:COMPETES_FOR {claim_weight, absorbed_share}]->(:Team)

Exports:
    compute_season_usage_shares: Season-total target/carry share per player-team.
    identify_departures_arrivals: Roster diff between season N-1 usage and season N roster.
    compute_vacated_opportunity_features: Per-player features for the target season.
    build_vacated_opportunity_data: Load Bronze/Silver and compute features for a season.
    build_vacated_opportunity_graph: Optional Neo4j ingestion of VACATED/COMPETES_FOR edges.
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
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")

FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}

# Minimum prior-season relevant share for a returning player to count as
# a competitor when no depth chart entry exists.
MIN_SHARE_COMPETITOR = 0.05

# Depth-chart rank -> claim weight on the vacated pool. Starters claim the
# bulk; depth 3+ claims scraps.
RANK_WEIGHTS = {1: 1.0, 2: 0.45, 3: 0.20}
DEFAULT_RANK_WEIGHT = 0.10

# Drafted rookies without a depth-chart entry claim by draft round.
ROOKIE_ROUND_WEIGHTS = {1: 0.45, 2: 0.25, 3: 0.25, 4: 0.10}
LATE_ROUND_WEIGHT = 0.05

# How much of the *target* vacancy each position competes for. Carries are
# contested by RBs only.
POSITION_TARGET_MULT = {"WR": 1.0, "TE": 1.0, "RB": 0.30}

VACATED_FEATURE_COLUMNS = [
    "vacated_target_share_abs",
    "vacated_carry_share_abs",
    "rz_vacancy_share",
    "net_target_vacancy",
    "net_carry_vacancy",
    "vacancy_competition_n",
    "arrival_displacement",
    "vacancy_absorbed_share",
]


# ---------------------------------------------------------------------------
# Data readers
# ---------------------------------------------------------------------------


def _read_bronze_parquet(subdir: str, season: int) -> pd.DataFrame:
    """Read latest Bronze parquet for a subdirectory and season.

    Args:
        subdir: Path under data/bronze/ (e.g. 'players/weekly').
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if no files exist.
    """
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        pattern_w = os.path.join(
            BRONZE_DIR, subdir, f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            return pd.concat([pd.read_parquet(f) for f in files_w], ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_silver_red_zone(season: int) -> pd.DataFrame:
    """Read latest Silver red-zone graph features for a season.

    Args:
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if not available.
    """
    pattern = os.path.join(
        SILVER_DIR, "graph_features", f"season={season}", "graph_red_zone_*.parquet"
    )
    files = sorted(glob.glob(pattern))
    return pd.read_parquet(files[-1]) if files else pd.DataFrame()


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------


def compute_season_usage_shares(weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Compute season-total target and carry shares per (player, team).

    Shares are totals-based (player targets / team targets over the whole
    regular season) rather than averages of weekly shares, so partial
    seasons weight correctly.

    Args:
        weekly_df: Bronze player_weekly DataFrame for ONE season with
            player_id, recent_team, position, week, targets, carries.

    Returns:
        DataFrame with columns player_id, team, position, target_share,
        carry_share. Empty DataFrame if input is empty.
    """
    if weekly_df.empty:
        return pd.DataFrame(
            columns=["player_id", "team", "position", "target_share", "carry_share"]
        )

    df = weekly_df.copy()
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    for col in ("targets", "carries"):
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)

    grouped = (
        df.groupby(["player_id", "recent_team"], as_index=False)
        .agg(
            targets=("targets", "sum"),
            carries=("carries", "sum"),
            position=("position", "first"),
        )
        .rename(columns={"recent_team": "team"})
    )

    team_totals = grouped.groupby("team").agg(
        team_targets=("targets", "sum"), team_carries=("carries", "sum")
    )
    grouped = grouped.merge(team_totals, on="team", how="left")

    grouped["target_share"] = np.where(
        grouped["team_targets"] > 0,
        grouped["targets"] / grouped["team_targets"],
        0.0,
    )
    grouped["carry_share"] = np.where(
        grouped["team_carries"] > 0,
        grouped["carries"] / grouped["team_carries"],
        0.0,
    )

    return grouped[["player_id", "team", "position", "target_share", "carry_share"]]


def normalize_depth_chart(depth_charts_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize depth chart data to (team, player_id, position, pos_rank).

    Handles both nflverse schemas:
    - Pre-2025: club_code, gsis_id, position, depth_team (rank), week,
      formation. Uses the earliest week (preseason snapshot).
    - 2025+: team, gsis_id, pos_abb, pos_rank, dt. Uses the earliest dt.

    Args:
        depth_charts_df: Bronze depth chart DataFrame for one season.

    Returns:
        DataFrame with columns team, player_id, position, pos_rank
        (one row per player, minimum rank kept). Empty on empty input.
    """
    out_cols = ["team", "player_id", "position", "pos_rank"]
    if depth_charts_df.empty:
        return pd.DataFrame(columns=out_cols)

    dc = depth_charts_df.copy()

    if "pos_rank" in dc.columns:  # 2025+ schema
        if "dt" in dc.columns:
            dc = dc[dc["dt"] == dc["dt"].min()]
        dc = dc.rename(columns={"gsis_id": "player_id", "pos_abb": "position"})
    else:  # pre-2025 schema
        if "formation" in dc.columns:
            dc = dc[dc["formation"] == "Offense"]
        if "week" in dc.columns:
            dc = dc[dc["week"] == dc["week"].min()]
        dc = dc.rename(
            columns={
                "club_code": "team",
                "gsis_id": "player_id",
                "depth_team": "pos_rank",
            }
        )

    if not set(out_cols).issubset(dc.columns):
        logger.warning(
            "Depth chart missing expected columns after normalization: %s",
            set(out_cols) - set(dc.columns),
        )
        return pd.DataFrame(columns=out_cols)

    dc = dc[dc["position"].isin(FANTASY_POSITIONS)].copy()
    dc["pos_rank"] = pd.to_numeric(dc["pos_rank"], errors="coerce")
    dc = dc.dropna(subset=["player_id", "pos_rank"])
    dc["pos_rank"] = dc["pos_rank"].astype(int)

    # One row per player: keep their best (lowest) rank.
    dc = (
        dc.sort_values("pos_rank")
        .drop_duplicates(subset=["team", "player_id"])
        .reset_index(drop=True)
    )
    return dc[out_cols]


def identify_departures_arrivals(
    prior_usage: pd.DataFrame,
    current_roster: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Diff season N-1 usage against the season N roster.

    A departure is a player who logged usage for team T in season N-1 but
    is not on T's season-N roster. An arrival is a player on T's season-N
    roster whose season N-1 usage was for a different team.

    Args:
        prior_usage: Output of compute_season_usage_shares for season N-1.
        current_roster: DataFrame with player_id, team, position for
            season N (deduplicated, fantasy positions).

    Returns:
        Tuple of (departures, arrivals). Departures has prior_usage columns
        (team = the team departed from). Arrivals has player_id, team
        (new team), position, prior_team, target_share, carry_share
        (shares from the prior team with the most usage).
    """
    empty_dep = pd.DataFrame(
        columns=["player_id", "team", "position", "target_share", "carry_share"]
    )
    empty_arr = pd.DataFrame(
        columns=[
            "player_id",
            "team",
            "position",
            "prior_team",
            "target_share",
            "carry_share",
        ]
    )
    if prior_usage.empty or current_roster.empty:
        return empty_dep, empty_arr

    roster_pairs = set(
        zip(current_roster["player_id"].astype(str), current_roster["team"])
    )

    usage = prior_usage.copy()
    usage["_on_same_team"] = [
        (str(pid), team) in roster_pairs
        for pid, team in zip(usage["player_id"], usage["team"])
    ]
    departures = usage[~usage["_on_same_team"]].drop(columns=["_on_same_team"])

    # Prior team per player = the team where they had the most combined usage.
    usage["_combined"] = usage["target_share"] + usage["carry_share"]
    prior_main = (
        usage.sort_values("_combined", ascending=False)
        .drop_duplicates(subset=["player_id"])
        .rename(columns={"team": "prior_team"})
    )[["player_id", "prior_team", "target_share", "carry_share"]]

    arrivals = current_roster.merge(prior_main, on="player_id", how="inner")
    arrivals = arrivals[arrivals["team"] != arrivals["prior_team"]]

    return (
        departures.reset_index(drop=True),
        arrivals[
            [
                "player_id",
                "team",
                "position",
                "prior_team",
                "target_share",
                "carry_share",
            ]
        ].reset_index(drop=True),
    )


def _compute_rz_vacancy(
    departures: pd.DataFrame, rz_features_df: pd.DataFrame
) -> pd.Series:
    """Sum departed players' red-zone usage share per team.

    Uses each departed player's season-mean rz_target_share_roll3 +
    rz_carry_share_roll3 from the Silver red-zone graph features. Returns
    0.0 per team when red-zone data is unavailable.

    Args:
        departures: Departures DataFrame from identify_departures_arrivals.
        rz_features_df: Silver graph_red_zone features for season N-1.

    Returns:
        Series indexed by team with the vacated red-zone share.
    """
    if departures.empty:
        return pd.Series(dtype=float)
    zero = pd.Series(0.0, index=departures["team"].unique())

    rz_cols = {"rz_target_share_roll3", "rz_carry_share_roll3", "player_id"}
    if rz_features_df.empty or not rz_cols.issubset(rz_features_df.columns):
        return zero

    rz = rz_features_df.copy()
    rz["_rz_usage"] = rz["rz_target_share_roll3"].fillna(0.0) + rz[
        "rz_carry_share_roll3"
    ].fillna(0.0)
    player_rz = rz.groupby("player_id")["_rz_usage"].mean()

    dep = departures.copy()
    dep["_rz"] = dep["player_id"].map(player_rz).fillna(0.0)
    return dep.groupby("team")["_rz"].sum().reindex(zero.index, fill_value=0.0)


def _claim_weights(
    players: pd.DataFrame,
    depth_chart: pd.DataFrame,
    draft_picks: pd.DataFrame,
) -> pd.Series:
    """Compute each rostered player's claim weight on vacated volume.

    Priority: depth-chart rank -> rookie draft round -> prior-season share
    above MIN_SHARE_COMPETITOR (default weight). Players with none of the
    three get weight 0 and do not compete.

    Args:
        players: One team-position group with player_id, prior_share columns.
        depth_chart: Normalized depth chart (team, player_id, pos_rank).
        draft_picks: Draft picks for season N with gsis_id, round.

    Returns:
        Series of claim weights aligned to players.index.
    """
    dc_rank = (
        depth_chart.set_index("player_id")["pos_rank"]
        if not depth_chart.empty
        else pd.Series(dtype=float)
    )
    rookie_round = (
        draft_picks.dropna(subset=["gsis_id"]).set_index("gsis_id")["round"]
        if not draft_picks.empty and "gsis_id" in draft_picks.columns
        else pd.Series(dtype=float)
    )

    weights = []
    for _, row in players.iterrows():
        pid = row["player_id"]
        if pid in dc_rank.index:
            rank = int(dc_rank.loc[pid])
            weights.append(RANK_WEIGHTS.get(rank, DEFAULT_RANK_WEIGHT))
        elif pid in rookie_round.index:
            rnd = int(rookie_round.loc[pid])
            weights.append(ROOKIE_ROUND_WEIGHTS.get(rnd, LATE_ROUND_WEIGHT))
        elif row["prior_share"] >= MIN_SHARE_COMPETITOR:
            weights.append(DEFAULT_RANK_WEIGHT)
        else:
            weights.append(0.0)
    return pd.Series(weights, index=players.index)


def compute_vacated_opportunity_features(
    prior_weekly_df: pd.DataFrame,
    current_roster_df: pd.DataFrame,
    season: int,
    depth_charts_df: Optional[pd.DataFrame] = None,
    draft_picks_df: Optional[pd.DataFrame] = None,
    rz_features_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute vacated-opportunity features for every rostered fantasy player.

    Per team: gross vacancy = sum of departed players' season N-1 shares;
    arrivals import the share they held elsewhere; net vacancy = gross -
    imported (floored at 0) is then distributed across the roster by
    depth-chart claim weights.

    Args:
        prior_weekly_df: Bronze player_weekly for season N-1.
        current_roster_df: Roster for season N with player_id, team,
            position (fantasy positions).
        season: Target season N (stamped on output rows).
        depth_charts_df: Optional Bronze depth charts for season N.
        draft_picks_df: Optional Bronze draft picks for season N.
        rz_features_df: Optional Silver red-zone features for season N-1.

    Returns:
        DataFrame keyed (player_id, team, position, season) with
        VACATED_FEATURE_COLUMNS. Empty DataFrame when inputs are empty.
    """
    out_cols = ["player_id", "team", "position", "season"] + VACATED_FEATURE_COLUMNS
    if prior_weekly_df.empty or current_roster_df.empty:
        return pd.DataFrame(columns=out_cols)

    roster = current_roster_df[
        current_roster_df["position"].isin(FANTASY_POSITIONS)
    ].drop_duplicates(subset=["player_id", "team"])

    prior_usage = compute_season_usage_shares(prior_weekly_df)
    departures, arrivals = identify_departures_arrivals(prior_usage, roster)

    depth_chart = normalize_depth_chart(
        depth_charts_df if depth_charts_df is not None else pd.DataFrame()
    )
    draft_picks = draft_picks_df if draft_picks_df is not None else pd.DataFrame()
    rz_vacancy = _compute_rz_vacancy(
        departures,
        rz_features_df if rz_features_df is not None else pd.DataFrame(),
    )

    # Team-level gross vacated shares.
    gross = departures.groupby("team").agg(
        vacated_target_share_abs=("target_share", "sum"),
        vacated_carry_share_abs=("carry_share", "sum"),
    )
    # Team-level imported shares from arrivals.
    imported = arrivals.groupby("team").agg(
        imported_target=("target_share", "sum"),
        imported_carry=("carry_share", "sum"),
    )

    # Prior-season share per rostered player (from any team) for competitor
    # detection and arrival displacement.
    prior_main = (
        prior_usage.assign(_c=lambda d: d["target_share"] + d["carry_share"])
        .sort_values("_c", ascending=False)
        .drop_duplicates(subset=["player_id"])
        .set_index("player_id")
    )
    arrival_ids = set(arrivals["player_id"])

    rows: List[Dict[str, object]] = []
    for team, team_roster in roster.groupby("team"):
        g_target = float(gross["vacated_target_share_abs"].get(team, 0.0))
        g_carry = float(gross["vacated_carry_share_abs"].get(team, 0.0))
        net_target = max(
            0.0, g_target - float(imported["imported_target"].get(team, 0.0))
        )
        net_carry = max(0.0, g_carry - float(imported["imported_carry"].get(team, 0.0)))
        team_rz = float(rz_vacancy.get(team, 0.0))
        team_dc = depth_chart[depth_chart["team"] == team]

        team_players = team_roster.copy()
        team_players["prior_target_share"] = (
            team_players["player_id"].map(prior_main["target_share"]).fillna(0.0)
        )
        team_players["prior_carry_share"] = (
            team_players["player_id"].map(prior_main["carry_share"]).fillna(0.0)
        )

        # Target pool: WR/TE/RB weighted claims. Carry pool: RB claims.
        target_pool = team_players[
            team_players["position"].isin(POSITION_TARGET_MULT)
        ].copy()
        target_pool["prior_share"] = target_pool["prior_target_share"]
        t_weights = _claim_weights(target_pool, team_dc, draft_picks)
        t_weights = t_weights * target_pool["position"].map(POSITION_TARGET_MULT)
        t_total = t_weights.sum()

        carry_pool = team_players[team_players["position"] == "RB"].copy()
        carry_pool["prior_share"] = carry_pool["prior_carry_share"]
        c_weights = _claim_weights(carry_pool, team_dc, draft_picks)
        c_total = c_weights.sum()

        absorbed_target = (
            (t_weights / t_total * net_target) if t_total > 0 else t_weights * 0.0
        )
        absorbed_carry = (
            (c_weights / c_total * net_carry) if c_total > 0 else c_weights * 0.0
        )

        # Competition counts per position group: players with a real claim.
        claims_by_pos: Dict[str, int] = {}
        for pos, pos_players in team_players.groupby("position"):
            pos_players = pos_players.copy()
            rel = "prior_carry_share" if pos == "RB" else "prior_target_share"
            pos_players["prior_share"] = pos_players[rel]
            w = _claim_weights(pos_players, team_dc, draft_picks)
            claims_by_pos[pos] = int((w > 0).sum())

        for idx, row in team_players.iterrows():
            pid = row["player_id"]
            pos = row["position"]
            a_target = float(absorbed_target.get(idx, 0.0))
            a_carry = float(absorbed_carry.get(idx, 0.0))
            displacement = 0.0
            if pid in arrival_ids:
                rel = "prior_carry_share" if pos == "RB" else "prior_target_share"
                displacement = float(row[rel])

            rows.append(
                {
                    "player_id": pid,
                    "team": team,
                    "position": pos,
                    "season": season,
                    "vacated_target_share_abs": round(g_target, 4),
                    "vacated_carry_share_abs": round(g_carry, 4),
                    "rz_vacancy_share": round(team_rz, 4),
                    "net_target_vacancy": round(net_target, 4),
                    "net_carry_vacancy": round(net_carry, 4),
                    "vacancy_competition_n": max(0, claims_by_pos.get(pos, 0) - 1),
                    "arrival_displacement": round(displacement, 4),
                    "vacancy_absorbed_share": round(a_target + a_carry, 4),
                }
            )

    result = pd.DataFrame(rows, columns=out_cols)
    logger.info(
        "Vacated opportunity features: %d players, %d teams for season %d",
        len(result),
        result["team"].nunique() if not result.empty else 0,
        season,
    )
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_vacated_opportunity_data(target_season: int) -> pd.DataFrame:
    """Load Bronze/Silver data and compute UC1 features for a target season.

    Reads season N-1 player_weekly and red-zone Silver, plus season N
    rosters, depth charts, and draft picks — all local-first.

    Args:
        target_season: The season being projected (features describe the
            N-1 -> N transition).

    Returns:
        Feature DataFrame from compute_vacated_opportunity_features.
    """
    prior = target_season - 1
    weekly = _read_bronze_parquet("players/weekly", prior)
    rosters = _read_bronze_parquet("players/rosters", target_season)

    if weekly.empty or rosters.empty:
        logger.warning(
            "Missing weekly (season %d) or roster (season %d) data — "
            "skipping vacated opportunity features",
            prior,
            target_season,
        )
        return pd.DataFrame()

    # Deduplicate roster: latest week per player, fantasy positions only.
    roster = rosters.copy()
    if "week" in roster.columns:
        roster = roster.sort_values("week").drop_duplicates(
            subset=["player_id"], keep="last"
        )
    roster = roster[["player_id", "team", "position"]].dropna(subset=["player_id"])

    return compute_vacated_opportunity_features(
        prior_weekly_df=weekly,
        current_roster_df=roster,
        season=target_season,
        depth_charts_df=_read_bronze_parquet("depth_charts", target_season),
        draft_picks_df=_read_bronze_parquet("draft_picks", target_season),
        rz_features_df=_read_silver_red_zone(prior),
    )


def build_vacated_opportunity_graph(
    gdb: "GraphDB",
    target_season: int,
) -> Tuple[int, int]:
    """Ingest VACATED and COMPETES_FOR edges into Neo4j (optional path).

    Args:
        gdb: Connected GraphDB instance.
        target_season: Season N of the transition.

    Returns:
        Tuple of (n_vacated_edges, n_competes_edges). (0, 0) when Neo4j
        is unavailable.
    """
    if not gdb.is_connected:
        logger.warning("Neo4j not connected — skipping vacated opportunity graph")
        return 0, 0

    prior = target_season - 1
    weekly = _read_bronze_parquet("players/weekly", prior)
    rosters = _read_bronze_parquet("players/rosters", target_season)
    if weekly.empty or rosters.empty:
        return 0, 0

    roster = rosters.copy()
    if "week" in roster.columns:
        roster = roster.sort_values("week").drop_duplicates(
            subset=["player_id"], keep="last"
        )
    roster = roster[["player_id", "team", "position"]].dropna(subset=["player_id"])
    roster = roster[roster["position"].isin(FANTASY_POSITIONS)]

    prior_usage = compute_season_usage_shares(weekly)
    departures, _ = identify_departures_arrivals(prior_usage, roster)
    features = build_vacated_opportunity_data(target_season)

    batch_size = 500
    n_vacated = 0
    dep_edges = [
        {
            "player_id": str(r["player_id"]),
            "team": str(r["team"]),
            "season": int(target_season),
            "target_share": float(r["target_share"]),
            "carry_share": float(r["carry_share"]),
        }
        for _, r in departures.iterrows()
    ]
    for i in range(0, len(dep_edges), batch_size):
        batch = dep_edges[i : i + batch_size]
        gdb.run_write(
            "UNWIND $edges AS e "
            "MATCH (p:Player {gsis_id: e.player_id}) "
            "MATCH (t:Team {abbr: e.team}) "
            "MERGE (p)-[r:VACATED {season: e.season}]->(t) "
            "SET r.target_share = e.target_share, "
            "    r.carry_share = e.carry_share",
            {"edges": batch},
        )
        n_vacated += len(batch)

    n_competes = 0
    if not features.empty:
        comp = features[features["vacancy_absorbed_share"] > 0]
        comp_edges = [
            {
                "player_id": str(r["player_id"]),
                "team": str(r["team"]),
                "season": int(target_season),
                "absorbed_share": float(r["vacancy_absorbed_share"]),
                "competition_n": int(r["vacancy_competition_n"]),
            }
            for _, r in comp.iterrows()
        ]
        for i in range(0, len(comp_edges), batch_size):
            batch = comp_edges[i : i + batch_size]
            gdb.run_write(
                "UNWIND $edges AS e "
                "MATCH (p:Player {gsis_id: e.player_id}) "
                "MATCH (t:Team {abbr: e.team}) "
                "MERGE (p)-[r:COMPETES_FOR {season: e.season}]->(t) "
                "SET r.absorbed_share = e.absorbed_share, "
                "    r.competition_n = e.competition_n",
                {"edges": batch},
            )
            n_competes += len(batch)

    logger.info(
        "Created %d VACATED edges, %d COMPETES_FOR edges", n_vacated, n_competes
    )
    return n_vacated, n_competes
