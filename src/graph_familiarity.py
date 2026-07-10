"""Cross-team familiarity network — QB changes & reunions (UC2).

Extends the QB-WR chemistry graph with the two events that move
early-season projections most:

1. **Cold start** — a pass-catcher whose expected QB has never thrown to
   them (``qb_is_new``). Existing chemistry features are NaN here, which
   models cannot distinguish from "no data"; this makes the cold start an
   explicit signal.
2. **Reunion** — a pair with history on a *previous* team
   (``qb_familiarity_games`` / ``reunion_epa_prior`` span all team stints,
   any season).

Plus two team-level offense-continuity features
(``offense_continuity_pct``, ``weapons_new_pct``) built on the UC1
roster-diff machinery.

Leakage discipline: the expected QB for week W is the team's primary QB
from the most recent week BEFORE W (for week 1: the prior-season primary
QB still on the roster, else the rostered QB with the most prior-season
attempts anywhere). Pair histories are cumulative through the PRIOR game
only (shift(1)). Continuity features use prior-season usage plus the
current roster — all knowable before kickoff.

Graph model (Neo4j optional, pure-pandas primary):
    (:Player)-[:PLAYED_WITH {games, epa_per_target}]->(:Player)

Exports:
    FAMILIARITY_FEATURE_COLUMNS: Output feature names.
    build_expected_qb_map: Lagged (team, season, week) -> expected QB.
    compute_pair_history: Cumulative cross-team pair stats per pair-week.
    compute_familiarity_features: Per WR/TE player-week features.
    build_familiarity_data: Load Bronze data and compute for one season.
"""

import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

FAMILIARITY_FEATURE_COLUMNS: List[str] = [
    "qb_is_new",
    "qb_familiarity_games",
    "reunion_epa_prior",
    "offense_continuity_pct",
    "weapons_new_pct",
]

RECEIVER_POSITIONS = {"WR", "TE"}


# ---------------------------------------------------------------------------
# Expected QB assignment (strictly lagged)
# ---------------------------------------------------------------------------


def _primary_qb_by_week(player_weekly_df: pd.DataFrame) -> pd.DataFrame:
    """Primary QB (most pass attempts) per team-season-week.

    Args:
        player_weekly_df: Bronze player_weekly (any number of seasons).

    Returns:
        DataFrame with team, season, week, qb_player_id.
    """
    pw = player_weekly_df
    if pw.empty or "position" not in pw.columns:
        return pd.DataFrame(columns=["team", "season", "week", "qb_player_id"])

    team_col = "recent_team" if "recent_team" in pw.columns else "team"
    qbs = pw[pw["position"] == "QB"].copy()
    if qbs.empty or team_col not in qbs.columns:
        return pd.DataFrame(columns=["team", "season", "week", "qb_player_id"])

    att_col = "attempts" if "attempts" in qbs.columns else None
    if att_col is None:
        for alt in ("passing_attempts", "completions"):
            if alt in qbs.columns:
                att_col = alt
                break
    if att_col is None:
        qbs = qbs.drop_duplicates(subset=[team_col, "season", "week"])
        out = qbs[[team_col, "season", "week", "player_id"]]
    else:
        qbs[att_col] = qbs[att_col].fillna(0)
        idx = qbs.groupby([team_col, "season", "week"])[att_col].idxmax()
        out = qbs.loc[idx, [team_col, "season", "week", "player_id"]]

    return out.rename(
        columns={team_col: "team", "player_id": "qb_player_id"}
    ).reset_index(drop=True)


def build_expected_qb_map(
    player_weekly_multi_df: pd.DataFrame,
    season: int,
    roster_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Lagged expected-QB assignment per (team, season, week).

    For week W > 1: the team's primary QB from the most recent prior week
    with data (bye-week safe). For week 1: the team's prior-season primary
    QB if still rostered, else the rostered QB with the most prior-season
    attempts anywhere (new signing), else NaN (rookie starter — no prior
    data by construction).

    Args:
        player_weekly_multi_df: Bronze player_weekly spanning at least
            seasons [season-1, season].
        season: Target season.
        roster_df: Optional roster for the target season with player_id,
            team, position. Required for the week-1 new-signing fallback.

    Returns:
        DataFrame with team, season, week, expected_qb_id (may be NaN).
    """
    out_cols = ["team", "season", "week", "expected_qb_id"]
    pw = player_weekly_multi_df
    if pw.empty:
        return pd.DataFrame(columns=out_cols)

    primary = _primary_qb_by_week(pw)
    cur = primary[primary["season"] == season].sort_values(["team", "week"])
    if cur.empty:
        return pd.DataFrame(columns=out_cols)

    # In-season: expected QB for week W = last observed primary QB before W.
    cur = cur.copy()
    cur["expected_qb_id"] = cur.groupby("team")["qb_player_id"].shift(1)

    # Week-1 (and any team's first observed week): prior-season fallback.
    prior = primary[primary["season"] == season - 1].sort_values(["team", "week"])
    prior_final_qb = (
        prior.drop_duplicates(subset=["team"], keep="last").set_index("team")[
            "qb_player_id"
        ]
        if not prior.empty
        else pd.Series(dtype=object)
    )

    rostered_qbs: dict = {}
    if roster_df is not None and not roster_df.empty:
        rq = roster_df[roster_df["position"] == "QB"]
        rostered_qbs = rq.groupby("team")["player_id"].apply(set).to_dict()

    # Prior-season attempts per QB (any team) for the new-signing fallback.
    qb_attempts = pd.Series(dtype=float)
    if "attempts" in pw.columns and "position" in pw.columns:
        prior_qbs = pw[(pw["season"] == season - 1) & (pw["position"] == "QB")]
        if not prior_qbs.empty:
            qb_attempts = prior_qbs.groupby("player_id")["attempts"].sum()

    def _week1_qb(team: str):
        prev = prior_final_qb.get(team)
        roster_set = rostered_qbs.get(team, set())
        if prev is not None and (not roster_set or prev in roster_set):
            return prev
        if roster_set and not qb_attempts.empty:
            candidates = qb_attempts.reindex(list(roster_set)).dropna()
            if not candidates.empty:
                return candidates.idxmax()
        return np.nan

    first_week_mask = cur["expected_qb_id"].isna()
    cur.loc[first_week_mask, "expected_qb_id"] = cur.loc[first_week_mask, "team"].map(
        _week1_qb
    )

    return cur[out_cols].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Cross-team pair history
# ---------------------------------------------------------------------------


def compute_pair_history(qb_wr_df: pd.DataFrame) -> pd.DataFrame:
    """Cumulative career stats per QB-receiver pair, strictly lagged.

    Pairs are keyed by player IDs only — team stints and seasons do not
    reset the history, so a reunion on a new team carries the pair's full
    record.

    Args:
        qb_wr_df: Output of graph_qb_wr_chemistry.build_qb_wr_chemistry
            spanning ALL available seasons (pair-week rows with passer_id,
            receiver_id, season, week, targets, epa_sum).

    Returns:
        DataFrame with passer_id, receiver_id, season, week,
        career_games_prior (games together before this week) and
        career_epa_per_target_prior (career EPA per target before this
        week; NaN with no history). Empty on empty input.
    """
    out_cols = [
        "passer_id",
        "receiver_id",
        "season",
        "week",
        "career_games_prior",
        "career_epa_per_target_prior",
        "career_games_after",
        "career_epa_per_target_after",
    ]
    if qb_wr_df.empty:
        return pd.DataFrame(columns=out_cols)

    pair = qb_wr_df.sort_values(["passer_id", "receiver_id", "season", "week"]).copy()
    keys = ["passer_id", "receiver_id"]

    grp = pair.groupby(keys)
    pair["career_games_prior"] = grp.cumcount()  # games BEFORE this one
    pair["career_games_after"] = pair["career_games_prior"] + 1
    cum_epa_after = grp["epa_sum"].cumsum()
    cum_targets_after = grp["targets"].cumsum()
    cum_epa = cum_epa_after - pair["epa_sum"]
    cum_targets = cum_targets_after - pair["targets"]
    pair["career_epa_per_target_prior"] = np.where(
        cum_targets > 0, cum_epa / cum_targets, np.nan
    )
    pair["career_epa_per_target_after"] = np.where(
        cum_targets_after > 0, cum_epa_after / cum_targets_after, np.nan
    )

    return pair[out_cols]


# ---------------------------------------------------------------------------
# Team-level continuity (reuses UC1 roster-diff machinery)
# ---------------------------------------------------------------------------


def _continuity_by_team(
    prior_weekly_df: pd.DataFrame,
    roster_df: pd.DataFrame,
    expected_week1_qb: pd.Series,
) -> pd.DataFrame:
    """Offense continuity and new-weapons share per team for one season.

    offense_continuity_pct: fraction of the team's prior-season targets
    accounted for by players still on the current roster.
    weapons_new_pct: fraction of the expected week-1 QB's prior-season
    targets (any team) thrown to receivers NOT on his current roster.

    Args:
        prior_weekly_df: Bronze player_weekly for season N-1.
        roster_df: Current-season roster (player_id, team, position).
        expected_week1_qb: Series team -> expected week-1 QB id.

    Returns:
        DataFrame with team, offense_continuity_pct, weapons_new_pct.
    """
    try:
        from graph_vacated_opportunity import compute_season_usage_shares
    except ImportError:  # pragma: no cover
        from src.graph_vacated_opportunity import compute_season_usage_shares

    out_cols = ["team", "offense_continuity_pct", "weapons_new_pct"]
    if prior_weekly_df.empty or roster_df.empty:
        return pd.DataFrame(columns=out_cols)

    usage = compute_season_usage_shares(prior_weekly_df)
    roster_pairs = set(zip(roster_df["player_id"].astype(str), roster_df["team"]))
    rostered_anywhere = roster_df.groupby("team")["player_id"].apply(set).to_dict()

    rows = []
    for team in roster_df["team"].dropna().unique():
        team_usage = usage[usage["team"] == team]
        total = team_usage["target_share"].sum()
        in_roster = pd.Series(
            [(str(pid), team) in roster_pairs for pid in team_usage["player_id"]],
            index=team_usage.index,
            dtype=bool,
        )
        retained = team_usage.loc[in_roster, "target_share"].sum()
        continuity = retained / total if total > 0 else np.nan

        weapons_new = np.nan
        qb_id = expected_week1_qb.get(team)
        if qb_id is not None and not pd.isna(qb_id):
            # QB's prior-season target distribution requires pair data —
            # approximated here from prior team usage: receivers on the
            # QB's prior team weighted by their target share.
            qb_prior_team = usage[usage["player_id"] == qb_id]
            if not qb_prior_team.empty:
                pt = qb_prior_team.iloc[0]["team"]
                pt_receivers = usage[
                    (usage["team"] == pt)
                    & (usage["position"].isin(RECEIVER_POSITIONS | {"RB"}))
                ]
                pt_total = pt_receivers["target_share"].sum()
                on_roster = rostered_anywhere.get(team, set())
                still = pt_receivers[pt_receivers["player_id"].isin(on_roster)][
                    "target_share"
                ].sum()
                if pt_total > 0:
                    weapons_new = 1.0 - (still / pt_total)

        rows.append(
            {
                "team": team,
                "offense_continuity_pct": (
                    np.nan if pd.isna(continuity) else round(float(continuity), 4)
                ),
                "weapons_new_pct": (
                    np.nan if pd.isna(weapons_new) else round(float(weapons_new), 4)
                ),
            }
        )
    return pd.DataFrame(rows, columns=out_cols)


# ---------------------------------------------------------------------------
# Feature assembly
# ---------------------------------------------------------------------------


def compute_familiarity_features(
    qb_wr_df: pd.DataFrame,
    player_weekly_multi_df: pd.DataFrame,
    season: int,
    roster_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Per WR/TE player-week familiarity features for one season.

    Args:
        qb_wr_df: Multi-season pair-week stats from build_qb_wr_chemistry
            (must include seasons before ``season`` for career histories).
        player_weekly_multi_df: Bronze player_weekly spanning at least
            [season-1, season].
        season: Target season.
        roster_df: Optional current-season roster (player_id, team,
            position) for week-1 QB fallback and continuity features.

    Returns:
        DataFrame with player_id, season, week + FAMILIARITY_FEATURE_COLUMNS.
        One row per WR/TE player-week. Empty on empty inputs.
    """
    out_cols = ["player_id", "season", "week"] + FAMILIARITY_FEATURE_COLUMNS
    pw = player_weekly_multi_df
    if pw.empty:
        return pd.DataFrame(columns=out_cols)

    team_col = "recent_team" if "recent_team" in pw.columns else "team"
    receivers = pw[
        (pw["season"] == season) & (pw["position"].isin(RECEIVER_POSITIONS))
    ][["player_id", team_col, "season", "week"]].rename(columns={team_col: "team"})
    if receivers.empty:
        return pd.DataFrame(columns=out_cols)

    qb_map = build_expected_qb_map(pw, season, roster_df)
    receivers = receivers.merge(qb_map, on=["team", "season", "week"], how="left")

    # Pair history lookup at (qb, receiver, season, week). Rows exist only
    # for weeks where the pair connected; for a receiver-week with no pair
    # row we need the pair's cumulative state, so build a per-pair asof
    # lookup: last known career totals as of any (season, week).
    history = compute_pair_history(qb_wr_df)

    if not history.empty:
        # Asof-style lookup: for each receiver-week, the pair's cumulative
        # state after their most recent game strictly BEFORE that week.
        hist = history.rename(
            columns={"passer_id": "expected_qb_id", "receiver_id": "player_id"}
        ).copy()
        hist["_pair_order"] = hist["season"] * 100 + hist["week"]
        receivers["_order"] = receivers["season"] * 100 + receivers["week"]

        matches = receivers[
            ["player_id", "season", "week", "expected_qb_id", "_order"]
        ].merge(
            hist[
                [
                    "expected_qb_id",
                    "player_id",
                    "_pair_order",
                    "career_games_after",
                    "career_epa_per_target_after",
                ]
            ],
            on=["expected_qb_id", "player_id"],
            how="inner",
        )
        matches = matches[matches["_pair_order"] < matches["_order"]]
        matches = matches.sort_values("_pair_order").drop_duplicates(
            subset=["player_id", "season", "week"], keep="last"
        )
        # Join back so receiver-weeks with no prior pair history are kept.
        receivers = receivers.merge(
            matches[
                [
                    "player_id",
                    "season",
                    "week",
                    "career_games_after",
                    "career_epa_per_target_after",
                ]
            ],
            on=["player_id", "season", "week"],
            how="left",
        )
        receivers["qb_familiarity_games"] = receivers["career_games_after"]
        receivers["reunion_epa_prior"] = receivers["career_epa_per_target_after"]
    else:
        receivers["qb_familiarity_games"] = 0
        receivers["reunion_epa_prior"] = np.nan

    receivers["qb_familiarity_games"] = (
        receivers["qb_familiarity_games"].fillna(0).astype(int)
    )
    # Disambiguation: (qb_is_new=0, qb_familiarity_games=0) means the
    # expected QB is UNKNOWN (NaN — e.g. rookie starter with no prior data);
    # (qb_is_new=1, games=0) is a genuine cold start with a known new QB;
    # (qb_is_new=0, games>0) is a familiar pair. Models using both features
    # can separate all three states.
    receivers["qb_is_new"] = np.where(
        receivers["expected_qb_id"].notna() & (receivers["qb_familiarity_games"] == 0),
        1,
        0,
    ).astype(int)

    # Team-level continuity features (constant per team-season).
    prior_weekly = pw[pw["season"] == season - 1]
    # Per-team earliest week (not the global minimum — a team missing the
    # league's first data week must still get its own first-week QB).
    week1_qb = (
        qb_map.sort_values("week")
        .drop_duplicates(subset=["team"], keep="first")
        .set_index("team")["expected_qb_id"]
        if not qb_map.empty
        else pd.Series(dtype=object)
    )
    continuity = _continuity_by_team(
        prior_weekly,
        roster_df if roster_df is not None else pd.DataFrame(),
        week1_qb,
    )
    if not continuity.empty:
        receivers = receivers.merge(continuity, on="team", how="left")
    else:
        receivers["offense_continuity_pct"] = np.nan
        receivers["weapons_new_pct"] = np.nan

    result = receivers[[c for c in out_cols if c in receivers.columns]].copy()
    for col in FAMILIARITY_FEATURE_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan
    result = result[out_cols].drop_duplicates(
        subset=["player_id", "season", "week"], keep="first"
    )

    logger.info(
        "Familiarity features: %d player-weeks (%d cold starts) for season %d",
        len(result),
        int(result["qb_is_new"].sum()),
        season,
    )
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_familiarity_data(
    season: int,
    qb_wr_df: pd.DataFrame,
    player_weekly_multi_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute UC2 features for one season from pre-loaded multi-season data.

    Callers (compute_graph_features.py) already hold multi-season PBP pair
    stats and player_weekly frames — this avoids re-reading Bronze.

    Args:
        season: Target season.
        qb_wr_df: Multi-season output of build_qb_wr_chemistry.
        player_weekly_multi_df: Multi-season Bronze player_weekly.

    Returns:
        Feature DataFrame from compute_familiarity_features.
    """
    try:
        from graph_vacated_opportunity import _load_transition_inputs
    except ImportError:  # pragma: no cover
        from src.graph_vacated_opportunity import _load_transition_inputs

    _, roster = _load_transition_inputs(season)
    return compute_familiarity_features(
        qb_wr_df=qb_wr_df,
        player_weekly_multi_df=player_weekly_multi_df,
        season=season,
        roster_df=roster if not roster.empty else None,
    )
