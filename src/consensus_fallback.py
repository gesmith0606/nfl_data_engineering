"""Guarantee a board row for every player the consensus projects >= 5 points.

The weekly engine builds a week-W row from each player's week W-1 stats, so a
player with no recent game (returning from a short or long absence, a
week-2/3 debut, a spot starter between starts) has no basis and silently drops
off the board. In 2026 weeks 1-9 that was 34 of 1,294 eligible player-weeks,
among them Puka Nacua (week 4, scored 30.2) and Nico Collins (27.3); scored
as zero they doubled the gap to Sleeper (+0.165 -> +0.327 MAE).

This module is the safety net, not a model: when the engine has no row for a
player the consensus rates >= ``MIN_CONSENSUS_PTS``, the board gets a row that
carries the consensus number and ``projection_source == "consensus_fallback"``,
so the number's provenance is explicit and graders can split it out.
"""

from __future__ import annotations

import glob
import os
from typing import Optional, Tuple

import numpy as np
import pandas as pd

FALLBACK_SOURCE = "consensus_fallback"
MIN_CONSENSUS_PTS = 5.0  # the repo's cons>=5 evaluation population
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
CONSENSUS_SOURCE = "sleeper"

_DEFAULT_SILVER_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "silver")
_COLUMNS = ["player_id", "player_name", "position", "team", "consensus"]


def load_consensus_week(
    season: int,
    week: int,
    scoring: str = "half_ppr",
    silver_dir: Optional[str] = None,
    source: str = CONSENSUS_SOURCE,
) -> pd.DataFrame:
    """Latest Silver consensus snapshot for one week.

    Returns:
        Frame with ``player_id, player_name, position, team, consensus``; empty
        when the week has no snapshot.
    """
    base = silver_dir or _DEFAULT_SILVER_DIR
    files = sorted(
        glob.glob(os.path.join(base, "external_projections", f"season={season}", f"week={week:02d}", "*.parquet"))
    )
    if not files:
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.read_parquet(files[-1])
    if "source" in df.columns:
        df = df[df["source"] == source]
    if "scoring_format" in df.columns:
        df = df[df["scoring_format"] == scoring]
    captured = str(df["projected_at"].max()) if "projected_at" in df.columns and len(df) else "unknown"
    df = df.dropna(subset=["player_id", "projected_points"]).rename(columns={"projected_points": "consensus"})
    df = df.sort_values("consensus", ascending=False).drop_duplicates("player_id")
    out = df.reindex(columns=_COLUMNS).reset_index(drop=True)
    # Provenance for the log line: the `week=W` snapshot on a Tuesday run is the
    # Sunday capture taken before week W-1 finished, so say how old it is.
    out.attrs["snapshot"] = f"{os.path.basename(files[-1])} (captured {captured})"
    return out


def _short_name(full: pd.Series) -> pd.Series:
    """'Dee Four' -> 'D.Four' (the board's, and Silver usage's, convention)."""
    full = full.astype(str).str.strip()
    return full.str[:1] + "." + full.str.split(" ", n=1).str[-1]


def _rank(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["position_rank"] = df.groupby("position")["projected_points"].rank(ascending=False, method="first").astype(int)
    if "overall_rank" in df.columns:
        df["overall_rank"] = df["projected_points"].rank(ascending=False, method="first").astype(int)
    return df


def apply_consensus_fallback(
    board: pd.DataFrame,
    consensus: pd.DataFrame,
    season: int,
    week: int,
    injuries_df: Optional[pd.DataFrame] = None,
    min_pts: float = MIN_CONSENSUS_PTS,
) -> Tuple[pd.DataFrame, int]:
    """Add a consensus-number row for each eligible player the board lacks.

    Args:
        board: the weekly board (``player_id``, ``position``, ``projected_points``...).
        consensus: output of :func:`load_consensus_week`.
        season: projected season.
        week: projected week.
        injuries_df: the injury frame the engine's rows were adjusted with, so a
            sidelined fallback player gets an explicit 0.0 row like everyone
            else (a row, not a hole).
        min_pts: consensus threshold.

    Returns:
        ``(board, n_added)``; ``board`` is returned unchanged when nothing is
        missing or the snapshot is absent (that case prints a ``::warning::``).
    """
    snapshot = (consensus.attrs.get("snapshot") if consensus is not None else None) or "unknown"
    if consensus is None or consensus.empty:
        print(
            f"::warning::Consensus fallback: no consensus snapshot for season={season} week={week}; "
            "cannot guarantee a row for every consensus>=5 player"
        )
        return board, 0
    missing = consensus[
        consensus["position"].isin(SKILL_POSITIONS)
        & (consensus["consensus"] >= min_pts)
        & ~consensus["player_id"].astype(str).isin(set(board["player_id"].astype(str)))
    ].copy()
    if missing.empty:
        return board, 0

    from projection_engine import add_floor_ceiling, apply_injury_adjustments

    rows = pd.DataFrame(
        {
            "player_id": missing["player_id"].astype(str).to_numpy(),
            "player_name": _short_name(missing["player_name"]).to_numpy(),
            "position": missing["position"].to_numpy(),
            "recent_team": missing["team"].to_numpy(),
            "proj_season": season,
            "proj_week": week,
            "projected_points": missing["consensus"].astype(float).round(2).to_numpy(),
            "is_bye_week": False,
            "is_rookie_projection": False,
            "is_veteran_return": False,
            "vegas_multiplier": 1.0,
            "week": week,
            "season": season,
            "projection_source": FALLBACK_SOURCE,
        }
    )
    rows = apply_injury_adjustments(rows, injuries_df if injuries_df is not None else pd.DataFrame())
    rows = add_floor_ceiling(rows)

    out = pd.concat([board, rows.reindex(columns=[c for c in board.columns if c in rows.columns] + [c for c in rows.columns if c not in board.columns])], ignore_index=True)
    for col in board.columns:
        if col in rows.columns:
            continue
        if col.endswith("_flag") or col.startswith("is_"):
            out[col] = out[col].fillna(False).astype(bool)
    out = _rank(out)
    out = out.sort_values("projected_points", ascending=False, kind="stable").reset_index(drop=True)
    print(
        f"Consensus fallback: added {len(rows)} row(s) for consensus>={min_pts:g} player(s) the engine had no "
        f"basis for ({', '.join(rows['player_name'].head(8))}{'...' if len(rows) > 8 else ''}); "
        f"consensus snapshot: {snapshot}"
    )
    return out, len(rows)
