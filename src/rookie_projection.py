"""Low-sample / rookie projection synthesizer.

Solves the silent-drop bug: ``generate_preseason_projections()`` is fed
``player_seasonal`` Bronze, which only contains players who accumulated stats.
Rookies and journeymen with thin or zero NFL history were silently dropped
from the Gold output, even when they were rostered as starters.

This module produces per-game-rate-based projections for any rostered fantasy
player who is missing from the main projection output. Quality scales with
evidence:

  - 6+ NFL games played → use that per-game rate, scaled to 17 games and
    capped at the position's starter baseline as a sanity rail.
  - 1-5 NFL games        → blend rookie sample with positional baseline.
  - 0 NFL games          → use positional baseline only.

Role weight comes from the latest depth-chart bronze (or the roster's
``depth_chart_position``):

  - depth=1: starter (1.00x baseline)
  - depth=2: backup with injury share (0.40x)
  - depth=3+ or unknown: dev/practice (0.25x)

For year-2 QBs specifically (the highest-impact silent-drop class), the
starter weight is bumped to 1.05x to apply a conservative league-average
year-2 efficiency lift. RB/WR/TE year-2 lifts are not applied — historical
year-2 leaps for skill-position rookies who started year 1 are noisier.

The output schema matches ``generate_preseason_projections``: ``player_id``,
``position``, ``player_name``, ``recent_team``, the 10 stat columns,
``projected_season_points``, and ``proj_season``. Floor/ceiling are not
computed here — the caller's ``add_floor_ceiling`` handles that downstream
with widened variance for ``low_sample=True`` rows.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:
    from src.projection_engine import (
        _ROLE_SCALE,
        _STARTER_BASELINES,
        calculate_fantasy_points_df,
    )
except ImportError:  # script-level execution adds src/ to sys.path directly
    from projection_engine import (
        _ROLE_SCALE,
        _STARTER_BASELINES,
        calculate_fantasy_points_df,
    )

logger = logging.getLogger(__name__)

_FULL_SEASON_GAMES = 17
_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K"}

# Stat columns that flow through the preseason output.
_STAT_COLS: List[str] = [
    "passing_yards",
    "passing_tds",
    "interceptions",
    "rushing_yards",
    "rushing_tds",
    "carries",
    "receiving_yards",
    "receiving_tds",
    "receptions",
    "targets",
]

# Year-2 lift for QBs only — calibrated conservatively. NOT applied to other
# positions (year-2 leaps for RB/WR/TE who already started are noisier and
# already partly captured in their year-1 sample).
_YEAR_2_QB_LIFT = 1.05


def _depth_to_role(depth_chart_position: object) -> str:
    """Map roster's depth_chart_position field to one of role keys.

    Roster bronze has ``depth_chart_position`` as a position abbreviation
    string (e.g. "QB"), not a numeric depth. The numeric depth lives in
    ``depth_charts`` bronze. Without that join we treat any rostered player
    with status ACT as a candidate, with role determined by the per-team
    sort order applied at enumeration time.
    """
    # Default unknown — caller passes resolved role via depth_rank.
    return "unknown"


def _resolve_team_position_role(
    roster: pd.DataFrame,
    position: str,
) -> pd.Series:
    """Fallback role assignment used when no depth_charts data is available.

    Rosters list players multiple deep at each position. The first ACT player
    per (team, position) is treated as the starter, the second as backup,
    the rest as unknown. Order is driven by ``depth_chart_position``
    (presence) then years_exp descending (vets edge rookies for backup slots)
    then jersey_number ascending.

    The preferred path is :func:`_role_from_depth_charts`, which uses the
    nflverse ``depth_charts`` bronze (real 2026 offseason depth charts).
    This function is used only as a fallback for players the depth_charts
    feed doesn't cover.

    Returns a Series keyed by roster index, values in {"starter","backup","unknown"}.
    """
    sub = roster[roster["position"] == position].copy()
    if sub.empty:
        return pd.Series(dtype=str)

    # Sort: ACT first, then by years_exp desc (vets edge ties), then jersey_number asc.
    status_priority = sub["status"].map({"ACT": 0, "RES": 1, "PUP": 2}).fillna(3)
    years = sub["years_exp"].fillna(0)
    jersey = sub["jersey_number"].fillna(99)
    sub = sub.assign(_sp=status_priority, _yrs=years, _jn=jersey)
    sub = sub.sort_values(["team", "_sp", "_yrs", "_jn"], ascending=[True, True, False, True])
    sub["_rank_in_team"] = sub.groupby("team").cumcount()
    role = sub["_rank_in_team"].map({0: "starter", 1: "backup"}).fillna("unknown")
    return role


def _role_from_depth_charts(
    depth_charts_df: pd.DataFrame,
    roster_df: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """Map gsis_id → role using the latest depth_charts snapshot per team/pos.

    Depth_charts bronze is the canonical source for who's actually starting
    on each team — updated through the offseason and reflects coaching
    decisions ahead of the upcoming season (e.g. Dart promoted to NYG QB1
    despite Winston still on the 2025-end roster).

    Logic:
      - Cross-reference each depth_charts row against the latest roster.
        A player tagged as on team X in depth_charts but NOT on team X per
        the roster bronze is dropped — protects against feed errors like
        "Kyler Murray as MIN QB1 starting 2026-03-13" which propagated for
        two days in the depth_charts feed before being corrected upstream.
      - For each (team, pos_abb) take the rows with the most-recent ``dt``
        AFTER the team-roster validation pass.
      - Within that snapshot, pos_rank=1 → starter, pos_rank=2 → backup,
        pos_rank>=3 → unknown.
      - Returns a dict keyed on gsis_id (matches roster bronze's player_id).

    Empty/missing depth_charts → returns empty dict; caller falls back to
    roster-based ordering.
    """
    if depth_charts_df is None or depth_charts_df.empty:
        return {}
    df = depth_charts_df
    needed = {"dt", "team", "pos_abb", "pos_rank", "gsis_id"}
    if not needed.issubset(df.columns):
        logger.warning(
            "depth_charts missing required columns; have %s",
            list(df.columns),
        )
        return {}

    # Restrict to fantasy positions and rows that carry a player id.
    df = df[df["pos_abb"].isin(_FANTASY_POSITIONS) & df["gsis_id"].notna()].copy()
    if df.empty:
        return {}

    # Validate against roster: a (gsis_id, team) pair only counts if the
    # roster bronze also says that player is on that team. This filters
    # out depth_charts feed errors where the upstream attribution is wrong.
    if roster_df is not None and not roster_df.empty and "player_id" in roster_df.columns:
        roster_pairs = set(
            zip(
                roster_df["player_id"].astype(str),
                roster_df["team"].astype(str),
            )
        )
        before = len(df)
        df["_pair"] = list(zip(df["gsis_id"].astype(str), df["team"].astype(str)))
        df = df[df["_pair"].isin(roster_pairs)].drop(columns="_pair")
        dropped = before - len(df)
        if dropped > 0:
            logger.info(
                "Filtered %d depth_charts rows where (player_id, team) "
                "didn't match the roster (likely feed errors)",
                dropped,
            )

    if df.empty:
        return {}

    # Latest dt per (team, pos_abb) — that's the most current depth chart.
    latest_dt = (
        df.groupby(["team", "pos_abb"])["dt"]
        .transform("max")
    )
    df = df[df["dt"] == latest_dt].copy()

    # Re-rank within (team, pos_abb) after the team-validation filter. If a
    # ghost row at pos_rank=1 was dropped (e.g. Kyler Murray ghosted as MIN
    # QB1), the remaining players' original pos_ranks no longer reflect
    # reality — the de-facto starter is whoever now sorts first by pos_rank.
    df["pos_rank_int"] = pd.to_numeric(df["pos_rank"], errors="coerce")
    df = df.dropna(subset=["pos_rank_int"]).copy()
    df = df.sort_values(["team", "pos_abb", "pos_rank_int"])
    df["effective_rank"] = df.groupby(["team", "pos_abb"]).cumcount() + 1

    rank_to_role: Dict[int, str] = {1: "starter", 2: "backup"}
    role_map: Dict[str, str] = {}
    for _, row in df.iterrows():
        gsis = str(row["gsis_id"])
        if not gsis or gsis in role_map:
            # First-write-wins: a player listed at multiple positions on the
            # same team (rare) keeps whichever pos_abb was iterated first.
            continue
        rank = int(row["effective_rank"])
        role_map[gsis] = rank_to_role.get(rank, "unknown")
    return role_map


def _rookie_year_per_game_rates(
    weekly_df: pd.DataFrame,
    player_id: str,
) -> Optional[Dict[str, float]]:
    """Compute per-game stat rates for a player from any weekly history.

    Returns None if the player has no usable rows. Otherwise returns a dict
    mapping each stat in _STAT_COLS to per-game average over their entire
    available sample. The caller scales by 17 games.
    """
    if weekly_df is None or weekly_df.empty:
        return None
    rows = weekly_df[weekly_df["player_id"] == player_id]
    if rows.empty:
        return None

    available = [c for c in _STAT_COLS if c in rows.columns]
    if not available:
        return None

    rates: Dict[str, float] = {}
    n_games = len(rows)
    for col in available:
        rates[col] = float(rows[col].fillna(0).sum() / n_games)
    rates["_n_games"] = float(n_games)
    return rates


def _baseline_per_game(position: str, role: str) -> Dict[str, float]:
    """Per-game baseline for the (position, role). Empty dict for unknown pos."""
    starter = _STARTER_BASELINES.get(position)
    if starter is None:
        return {}
    scale = _ROLE_SCALE.get(role, _ROLE_SCALE["unknown"])
    return {stat: value * scale for stat, value in starter.items()}


def _blend_with_baseline(
    nfl_rates: Optional[Dict[str, float]],
    baseline: Dict[str, float],
    position: str,
    is_year_2: bool,
) -> Dict[str, float]:
    """Bayesian-style blend: weight = n_games / (n_games + k).

    k is the prior strength in games-equivalents — larger k means we trust
    the baseline more. Calibrated by position so QBs (more variance per
    sample) lean on the baseline longer than RBs.

    For year-2 QBs at starter baseline, applies the +5% efficiency lift to
    passing/rushing yards and TDs.
    """
    k_per_pos = {"QB": 8.0, "RB": 5.0, "WR": 6.0, "TE": 6.0, "K": 4.0}
    k = k_per_pos.get(position, 6.0)

    blended: Dict[str, float] = {}
    n_games = (nfl_rates or {}).get("_n_games", 0.0)
    weight_nfl = n_games / (n_games + k) if n_games > 0 else 0.0

    keys = set(baseline.keys()) | set((nfl_rates or {}).keys()) - {"_n_games"}
    for key in keys:
        nfl_v = (nfl_rates or {}).get(key, 0.0)
        base_v = baseline.get(key, 0.0)
        blended[key] = weight_nfl * nfl_v + (1.0 - weight_nfl) * base_v

    if is_year_2 and position == "QB":
        for key in ("passing_yards", "passing_tds", "rushing_yards", "rushing_tds"):
            if key in blended:
                blended[key] *= _YEAR_2_QB_LIFT

    return blended


def project_low_sample_players(
    roster_df: pd.DataFrame,
    weekly_df: Optional[pd.DataFrame],
    already_projected_player_ids: set,
    target_season: int,
    scoring_format: str = "half_ppr",
    depth_charts_df: Optional[pd.DataFrame] = None,
    team_pos_starter_already_projected: Optional[set] = None,
    college_features_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Synthesize projections for rostered players missing from main pipeline.

    Args:
        roster_df: latest roster bronze (one row per (player_id, team) at
            current snapshot). Must include columns: player_id, player_name,
            position, team, status, years_exp, depth_chart_position,
            jersey_number.
        weekly_df: optional player_weekly bronze covering recent seasons.
            Used to extract per-game rates for players with thin samples.
            Pass None if unavailable; players will fall back to baseline-only.
        already_projected_player_ids: set of player_ids already covered by
            the main preseason path. Their roster rows are skipped to avoid
            double-counting.
        target_season: season being projected for.
        scoring_format: ppr / half_ppr / standard.
        depth_charts_df: optional latest ``depth_charts`` bronze covering the
            offseason. When provided, role assignment uses the canonical
            depth-chart pos_rank (=1 starter / =2 backup) which reflects
            actual 2026 coaching decisions (e.g. Dart promoted to NYG QB1
            even though Winston is still on the 2025-end roster).

    Returns:
        DataFrame with the same columns as ``generate_preseason_projections``
        output (pre-ranking), or an empty frame if no synthesis was needed.
        The caller is responsible for concatenating, ranking, and applying
        floor/ceiling.
    """
    if roster_df is None or roster_df.empty:
        return pd.DataFrame()

    # Filter to active fantasy positions. RES/PUP players still appear in
    # rankings (they're injured, not retired) and the API can show their
    # status. CUT/RET/INA/DEV/TRD/TRC are excluded.
    fantasy_status = {"ACT", "RES", "PUP"}
    sub = roster_df[
        roster_df["position"].isin(_FANTASY_POSITIONS)
        & roster_df["status"].isin(fantasy_status)
    ].copy()

    if sub.empty:
        return pd.DataFrame()

    # De-dupe: a player traded mid-roster snapshot can appear twice. Keep
    # the most-active (ACT > RES > PUP), then most recent.
    status_pri = sub["status"].map({"ACT": 0, "RES": 1, "PUP": 2}).fillna(9)
    sub = sub.assign(_sp=status_pri).sort_values(
        ["player_id", "_sp"], ascending=[True, True]
    )
    sub = sub.drop_duplicates(subset=["player_id"], keep="first").drop(columns="_sp")

    # ------------------------------------------------------------------
    # Role assignment: depth_charts (canonical, current) → roster fallback
    # ------------------------------------------------------------------
    # Step 1: try depth_charts first. This is the authoritative source for
    # offseason starter/backup decisions. Covers most rostered players.
    depth_role_map: Dict[str, str] = _role_from_depth_charts(
        depth_charts_df, roster_df=sub
    )
    if depth_role_map:
        logger.info(
            "depth_charts role map: %d player → role assignments",
            len(depth_role_map),
        )

    # Step 2: roster-based fallback for any player not in depth_charts.
    full_roster_role: Dict[str, str] = {}
    for pos in _FANTASY_POSITIONS:
        pos_role = _resolve_team_position_role(sub, pos)
        for idx, role in pos_role.items():
            pid = sub.at[idx, "player_id"]
            if pd.notna(pid):
                full_roster_role[str(pid)] = role

    def _resolve_role(pid: object) -> str:
        s_pid = str(pid) if pd.notna(pid) else ""
        if s_pid in depth_role_map:
            return depth_role_map[s_pid]
        return full_roster_role.get(s_pid, "unknown")

    sub["_role"] = sub["player_id"].apply(_resolve_role)

    # Step 3: UDFA cap — if depth_charts didn't cover a player AND the roster
    # fallback labeled them "starter" because they were the only ACT player
    # at their (team, position), demote to "backup" unless they have draft
    # capital. This stops UDFAs (e.g. Seth Henigan) from inheriting starter
    # weight just because the previous-season roster snapshot was thin.
    if "draft_number" in sub.columns:
        not_in_depth = ~sub["player_id"].astype(str).isin(depth_role_map.keys())
        no_capital = sub["draft_number"].isna() | sub["draft_number"].gt(150)
        rookie = sub["years_exp"].fillna(99).le(1)
        cap_mask = (
            not_in_depth
            & no_capital
            & rookie
            & sub["_role"].eq("starter")
        )
        if cap_mask.any():
            sub.loc[cap_mask, "_role"] = "backup"
            logger.info(
                "UDFA cap: demoted %d undrafted-or-late-pick rookies from "
                "fallback-starter to backup",
                int(cap_mask.sum()),
            )

    # Step 3.5: starter-conflict demote — if the upstream projections already
    # cover a viable starter at this (team, position), any synthesized
    # "starter" must be a backup at best. Without this, depth_charts feed
    # holes (e.g. Tua not listed at MIA in 2026-03-14 snapshot) let a backup
    # like Quinn Ewers inherit starter weight even though Tua is the real
    # starter. The starter set is supplied by the caller.
    if team_pos_starter_already_projected:
        starter_conflict = sub.apply(
            lambda r: (str(r["team"]), str(r["position"]))
            in team_pos_starter_already_projected,
            axis=1,
        )
        demote_mask = starter_conflict & sub["_role"].eq("starter")
        if demote_mask.any():
            sub.loc[demote_mask, "_role"] = "backup"
            logger.info(
                "Starter-conflict demote: demoted %d synthesized 'starter' "
                "rows to 'backup' because the upstream projections already "
                "cover a starter at that (team, position)",
                int(demote_mask.sum()),
            )

    # Step 4: draft-capital override — a high-pick rookie/year-1 QB sitting
    # behind a veteran on the previous-season roster snapshot may still be
    # missed by depth_charts (rare, but real for late-March picks). Promote
    # when ACT + 1st/2nd round + missing from depth_charts.
    if "draft_number" in sub.columns:
        not_in_depth = ~sub["player_id"].astype(str).isin(depth_role_map.keys())
        promote = (
            not_in_depth
            & sub["status"].eq("ACT")
            & sub["years_exp"].fillna(99).le(1)
            & sub["position"].isin({"QB", "RB", "WR", "TE"})
            & sub["draft_number"].notna()
            & sub["draft_number"].le(64)
            & sub["_role"].ne("starter")
        )
        if promote.any():
            sub.loc[promote, "_role"] = "starter"
            logger.info(
                "Draft-capital override: promoted %d high-pick rookie/year-1 "
                "players to starter role (no depth_charts coverage)",
                int(promote.sum()),
            )

    # Now filter to players missing from the upstream projection pass.
    sub = sub[~sub["player_id"].isin(already_projected_player_ids)].copy()
    if sub.empty:
        return pd.DataFrame()

    # Build projections row by row. Keep this readable; rosters are O(200) max.
    out_rows: List[Dict[str, object]] = []
    for _, row in sub.iterrows():
        position = str(row["position"])
        if position not in _FANTASY_POSITIONS:
            continue
        if position == "K":
            # Kickers are appended separately in the main function. Skip here
            # to avoid double-counting them.
            continue

        player_id = row["player_id"]
        role = row["_role"]
        years_exp = float(row.get("years_exp", 0) or 0)
        is_year_2 = years_exp == 1.0

        baseline = _baseline_per_game(position, role)
        if not baseline:
            continue

        nfl_rates = _rookie_year_per_game_rates(weekly_df, player_id)
        per_game = _blend_with_baseline(nfl_rates, baseline, position, is_year_2)

        # Scale per-game rates to a 17-game season.
        season_totals: Dict[str, float] = {
            stat: round(per_game.get(stat, 0.0) * _FULL_SEASON_GAMES, 2)
            for stat in _STAT_COLS
        }

        out_rows.append(
            {
                "player_id": player_id,
                "position": position,
                "player_name": row.get("player_name"),
                "recent_team": row.get("team"),
                **season_totals,
                "proj_season": target_season,
                "is_low_sample_projection": True,
                "low_sample_role": role,
                "low_sample_n_games": (nfl_rates or {}).get("_n_games", 0.0),
            }
        )

    if not out_rows:
        return pd.DataFrame()

    proj = pd.DataFrame(out_rows)

    # Compute fantasy points from totals.
    proj["projected_season_points"] = (
        calculate_fantasy_points_df(proj, scoring_format=scoring_format, output_col="_pts")["_pts"]
        .clip(lower=0.0)
        .round(1)
    )
    proj.drop(columns=["_pts"], inplace=True, errors="ignore")

    # ------------------------------------------------------------------
    # College-prior blend
    # ------------------------------------------------------------------
    # When a CFBD-driven prospect profile carries a ``prospect_comp_median``
    # (k=5 historical similar players' season-1 fantasy points), blend it
    # with the role-baseline projection. Weight on the prior is largest for
    # players with no NFL sample (n_games=0) and decays as NFL evidence
    # accumulates. The role then scales the prior so a comp-median of 250
    # for "Drake-Maye-as-starter" is taken closer to face value than the
    # same comp-median for a backup buried on the depth chart.
    if college_features_df is not None and not college_features_df.empty:
        cf = college_features_df.copy()
        # Find a join key. Player_id is best when both have it; otherwise fall
        # back to (player_name) — name collisions across positions are rare
        # for skill positions and acceptable risk here.
        if "gsis_id" in cf.columns and "player_id" not in cf.columns:
            cf = cf.rename(columns={"gsis_id": "player_id"})
        merge_cols = (
            ["player_id"]
            if "player_id" in cf.columns and proj["player_id"].notna().any()
            else ["player_name"]
        )
        cols_to_pull = [
            "prospect_comp_median",
            "prospect_comp_floor",
            "prospect_comp_ceiling",
            "scheme_familiarity_score",
        ]
        available = [c for c in cols_to_pull if c in cf.columns]
        if available:
            proj = proj.merge(
                cf[merge_cols + available].drop_duplicates(subset=merge_cols),
                on=merge_cols,
                how="left",
            )

            # Prior weight by NFL sample size + role.
            # Role scales the prior to NOT over-credit a backup with a
            # high prospect_comp (the comp distribution mixes starters and
            # high draft picks).
            role_scale = proj["low_sample_role"].map(_ROLE_SCALE).fillna(_ROLE_SCALE["unknown"])
            n = proj.get("low_sample_n_games", pd.Series(0.0, index=proj.index)).fillna(0.0)
            # k=8 games-equivalent prior strength for the comp median.
            k_comp = 8.0
            prior_w = pd.Series(0.0, index=proj.index)
            comp_present = proj["prospect_comp_median"].notna()
            prior_w.loc[comp_present] = k_comp / (n.loc[comp_present] + k_comp)

            # Scheme familiarity nudges the prior a bit (+/- 5%).
            scheme = (
                proj["scheme_familiarity_score"].fillna(0.5)
                if "scheme_familiarity_score" in proj.columns
                else pd.Series(0.5, index=proj.index)
            )
            scheme_factor = 0.95 + scheme * 0.10  # 0.95 .. 1.05

            comp_target = (
                proj["prospect_comp_median"].fillna(0.0)
                * role_scale
                * scheme_factor
            )

            blended = (
                prior_w * comp_target
                + (1.0 - prior_w) * proj["projected_season_points"]
            )
            proj.loc[comp_present, "projected_season_points"] = (
                blended.loc[comp_present].clip(lower=0.0).round(1)
            )
            logger.info(
                "College-prior blend applied to %d rows (comp_median present)",
                int(comp_present.sum()),
            )

    logger.info(
        "Low-sample projection synthesizer added %d rows (positions: %s)",
        len(proj),
        proj["position"].value_counts().to_dict(),
    )
    return proj
