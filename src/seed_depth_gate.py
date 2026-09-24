"""Gate the Week-1 prior-season seed on the CURRENT depth chart.

Week 1 of a new season has no in-season rows, so the projection engine seeds
every player's rolling state from his final prior-season regular-season row
(:func:`projection_engine.prior_season_feature_rows`, PR #109). That row says
nothing about the player's role NOW: a backup whose last rows came from a
starting stretch inherits a starter projection. The 2026 Week 1 board
projected ~20 non-starting QBs as starters (Fields 18.1 as KC's QB2, Winston
16.3, Mariota 14.5, a retired Rivers 13.8) plus non-QBs who were not playing
(Jacobs 11.6 as GB's RB4 on the commissioner-exempt list, an unsigned Tyreek
Hill) — see ``.planning/SEASON_2026_WEEKS_1_2_RETRO.md``.

The gate reads the OurLads daily depth-chart snapshots
(``data/bronze/depth_charts/season=YYYY``: ``dt``, ``team``, ``gsis_id``,
``pos_abb``, ``pos_rank``), takes the latest snapshot at or before ``as_of``
and, for Week 1 only:

* a player on NO team's depth chart (retired, unsigned, suspended/exempt and
  removed) is zeroed (``seed_depth_gate = "off_depth_chart"``) — same
  keep-the-row-at-zero precedent as an injury-report "Out";
* a player deeper than :data:`STARTER_DEPTH` at his position (only the QB1
  keeps a starter QB projection) is scaled by the engine's own backup role
  scale, ``projection_engine._ROLE_SCALE['backup']``
  (``seed_depth_gate = "backup_depth"``).

Everything else — and every week after Week 1, where rolling state comes from
the current season — is untouched. Guards keep a bad snapshot from zeroing the
board: teams absent from the snapshot are left alone, and the gate is skipped
entirely when fewer than :data:`MIN_MATCH_RATE` of the covered rows join on
``gsis_id``.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from graph_vacated_opportunity import normalize_depth_chart
from projection_engine import _ROLE_SCALE

logger = logging.getLogger(__name__)

#: Deepest depth-chart rank (team-level ordinal within position, OurLads
#: ``pos_rank``) that still supports a seeded starter-level projection.
STARTER_DEPTH = {"QB": 1, "RB": 2, "WR": 3, "TE": 2}

#: Scale applied to a seeded projection beyond :data:`STARTER_DEPTH`.
BACKUP_SCALE = _ROLE_SCALE["backup"]

#: Below this share of snapshot-covered rows joining on gsis_id the snapshot
#: (or the id space) is suspect and the gate is skipped.
MIN_MATCH_RATE = 0.5

_PROTECTED_COLS = {"proj_season", "proj_week"}


def depth_chart_snapshot(
    depth_chart_df: Optional[pd.DataFrame],
    as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Latest depth-chart snapshot at or before ``as_of``, one row per player.

    Args:
        depth_chart_df: OurLads Bronze depth charts (``dt``, ``team``,
            ``gsis_id``, ``pos_abb``, ``pos_rank``) — any number of daily
            snapshots.
        as_of: Cut-off timestamp (UTC-aware or naive-UTC). ``None`` = latest.

    Returns:
        ``team``, ``player_id``, ``position``, ``pos_rank`` (best rank per
        player, QB/RB/WR/TE only). Empty when nothing qualifies.
    """
    cols = ["team", "player_id", "position", "pos_rank"]
    if depth_chart_df is None or depth_chart_df.empty:
        return pd.DataFrame(columns=cols)
    if not {"dt", "pos_rank"}.issubset(depth_chart_df.columns):
        return pd.DataFrame(columns=cols)
    dc = depth_chart_df.copy()
    dc["dt"] = pd.to_datetime(dc["dt"], utc=True, errors="coerce")
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff
        dc = dc[dc["dt"] <= cutoff]
    dc = dc.dropna(subset=["dt"])
    if dc.empty:
        return pd.DataFrame(columns=cols)
    dc = dc[dc["dt"] == dc["dt"].max()]
    snap = normalize_depth_chart(dc)
    # normalize_depth_chart dedups per (team, player); keep one row per player.
    return snap.sort_values("pos_rank").drop_duplicates("player_id")[cols]


def apply_week1_seed_depth_gate(
    proj_df: pd.DataFrame,
    depth_chart_df: Optional[pd.DataFrame],
    week: int,
    as_of: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Zero / backup-scale Week-1 seeded projections the depth chart doesn't support.

    Args:
        proj_df: Weekly projections (``player_id`` = gsis_id, ``position``,
            ``recent_team``, ``projected_points`` and ``proj_*`` stats).
        depth_chart_df: OurLads Bronze depth charts for the projected season.
        week: Projected week — the gate only runs for Week 1 (the only week
            projected from the prior-season seed).
        as_of: Use the latest snapshot at or before this timestamp
            (``None`` = latest available).

    Returns:
        Copy of ``proj_df`` with gated rows rescaled and a ``seed_depth_gate``
        provenance column (``"off_depth_chart"``, ``"backup_depth"`` or None).
    """
    out = proj_df.copy()
    out["seed_depth_gate"] = None
    if week > 1 or out.empty:
        return out

    snap = depth_chart_snapshot(depth_chart_df, as_of=as_of)
    if snap.empty:
        logger.warning("Week-1 seed depth gate skipped: no depth-chart snapshot")
        return out

    covered = out["recent_team"].isin(set(snap["team"])) & out["position"].isin(
        STARTER_DEPTH
    )
    rank_by_id = snap.set_index(snap["player_id"].astype(str))["pos_rank"]
    rank = out["player_id"].astype(str).map(rank_by_id)
    matched = covered & rank.notna()
    rate = matched.sum() / covered.sum() if covered.any() else 0.0
    if rate < MIN_MATCH_RATE:
        logger.warning(
            "Week-1 seed depth gate skipped: only %.0f%% of %d rows joined the "
            "depth chart on gsis_id (< %.0f%%)",
            100 * rate,
            int(covered.sum()),
            100 * MIN_MATCH_RATE,
        )
        return out

    off_chart = covered & rank.isna()
    too_deep = matched & (rank > out["position"].map(STARTER_DEPTH))

    scale_cols = [
        c
        for c in out.columns
        if (c.startswith("proj_") or c.startswith("projected_"))
        and c not in _PROTECTED_COLS
        and pd.api.types.is_numeric_dtype(out[c])
    ]
    out.loc[too_deep, scale_cols] = (
        out.loc[too_deep, scale_cols] * BACKUP_SCALE
    ).round(2)
    out.loc[off_chart, scale_cols] = 0.0
    out.loc[too_deep, "seed_depth_gate"] = "backup_depth"
    out.loc[off_chart, "seed_depth_gate"] = "off_depth_chart"

    # Ranks were assigned upstream on the ungated points (Fields stayed
    # overall #16 at 7 pts); re-derive them so the board order matches.
    out = out.sort_values("projected_points", ascending=False, kind="stable")
    if "overall_rank" in out.columns:
        out["overall_rank"] = range(1, len(out) + 1)
    if "position_rank" in out.columns:
        out["position_rank"] = (
            out.groupby("position")["projected_points"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    out = out.reset_index(drop=True)

    logger.info(
        "Week-1 seed depth gate: %.0f%% of %d rows joined; %d off depth chart "
        "(zeroed), %d beyond starter depth (x%.2f)",
        100 * rate,
        int(covered.sum()),
        int(off_chart.sum()),
        int(too_deep.sum()),
        BACKUP_SCALE,
    )
    return out
