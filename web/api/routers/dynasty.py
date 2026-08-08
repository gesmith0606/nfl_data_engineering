"""/api/dynasty endpoints — dynasty-format value + rookie rankings.

Market-gap sprint (2026-08): dynasty leagues value players on a multi-year
horizon, not just the current season. This surfaces a simple, defensible
age-adjusted rank over the existing preseason projections — no new modeling.
"""

from __future__ import annotations

import glob
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.projection_store import load_latest_preseason

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dynasty", tags=["dynasty"])

_ROSTER_COLUMNS = ["player_id", "age", "years_exp", "entry_year", "rookie_year"]


# ---------------------------------------------------------------------------
# Schemas (local — only dynasty endpoints use them)
# ---------------------------------------------------------------------------


class DynastyPlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    age: Optional[float] = None
    projected_season_points: float
    dynasty_points: float
    age_multiplier: float
    vorp: Optional[float] = None


class DynastyRankingsResponse(BaseModel):
    season: int
    players: List[DynastyPlayer]


class RookiePlayer(BaseModel):
    player_id: str
    player_name: str
    team: Optional[str] = None
    position: str
    age: Optional[float] = None
    projected_season_points: float
    low_sample_role: Optional[str] = None


class RookieRankingsResponse(BaseModel):
    season: int
    players: List[RookiePlayer]


# ---------------------------------------------------------------------------
# Age multiplier table
# ---------------------------------------------------------------------------


# ponytail: hardcoded dynasty age-curve multipliers. Simple, defensible,
# revisit once we have dynasty ADP/trade data to fit against. Ages fall on
# the low end of each bucket (e.g. RB 26 -> "26-27" bucket, not "<=25").
def age_multiplier(position: str, age: Optional[float]) -> float:
    """Dynasty age-adjustment multiplier for *position* at *age*.

    Missing age returns a neutral 1.0 (fail-open — a player without a
    roster-parquet age match still ranks on raw projection).
    """
    if age is None or pd.isna(age):
        return 1.0
    pos = (position or "").upper()
    if pos == "RB":
        if age <= 25:
            return 1.1
        if age <= 27:
            return 1.0
        if age <= 29:
            return 0.85
        return 0.7
    if pos in ("WR", "TE"):
        if age <= 26:
            return 1.1
        if age <= 29:
            return 1.0
        if age <= 31:
            return 0.9
        return 0.75
    if pos == "QB":
        if age <= 30:
            return 1.05
        if age <= 35:
            return 1.0
        return 0.85
    return 1.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _load_preseason(season: int) -> pd.DataFrame:
    df = load_latest_preseason(season)
    if df is None or df.empty:
        raise HTTPException(
            status_code=503,
            detail=f"No preseason projections on disk for season {season}.",
        )
    return df.copy()


def _load_roster(season: int) -> Optional[pd.DataFrame]:
    """Latest committed roster parquet for *season*, trimmed to id columns.

    Returns ``None`` when no roster parquet exists on disk for the season —
    callers decide whether that is fatal (rookie detection needs it) or
    degrades gracefully (dynasty age multiplier falls back to 1.0).
    """
    files = sorted(
        glob.glob(
            str(
                DATA_DIR
                / "bronze"
                / "players"
                / "rosters"
                / f"season={season}"
                / "*.parquet"
            )
        )
    )
    if not files:
        return None
    df = pd.read_parquet(files[-1])
    cols = [c for c in _ROSTER_COLUMNS if c in df.columns]
    if "player_id" not in cols:
        return None
    df = df[cols].drop_duplicates(subset=["player_id"])
    df["player_id"] = df["player_id"].astype(str)
    return df


def _with_dynasty_points(
    df: pd.DataFrame, roster: Optional[pd.DataFrame]
) -> pd.DataFrame:
    df = df.copy()
    df["player_id"] = df["player_id"].astype(str)
    if roster is not None:
        df = df.merge(roster, on="player_id", how="left")
    else:
        df["age"] = None
    df["age_multiplier"] = [
        age_multiplier(pos, age) for pos, age in zip(df["position"], df["age"])
    ]
    df["dynasty_points"] = (
        df["projected_season_points"].fillna(0) * df["age_multiplier"]
    ).round(2)
    return df


def _to_dynasty_player(row: Dict[str, Any]) -> DynastyPlayer:
    age = row.get("age")
    vorp = row.get("vorp")
    return DynastyPlayer(
        player_id=str(row.get("player_id") or ""),
        player_name=str(row.get("player_name") or ""),
        team=row.get("team") or row.get("recent_team"),
        position=str(row.get("position") or "").upper(),
        age=None if age is None or pd.isna(age) else float(age),
        projected_season_points=float(row.get("projected_season_points") or 0),
        dynasty_points=float(row.get("dynasty_points") or 0),
        age_multiplier=float(row.get("age_multiplier") or 1.0),
        vorp=None if vorp is None or pd.isna(vorp) else float(vorp),
    )


# ---------------------------------------------------------------------------
# Dynasty rankings
# ---------------------------------------------------------------------------


@router.get("/rankings", response_model=DynastyRankingsResponse)
def dynasty_rankings(
    season: int = Query(..., ge=1999, le=2030),
    position: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> DynastyRankingsResponse:
    """Dynasty-value rankings: projected season points x age multiplier."""
    df = _load_preseason(season)
    roster = _load_roster(season)  # optional — missing age degrades to 1.0
    df = _with_dynasty_points(df, roster)
    if position:
        df = df[df["position"].astype(str).str.upper() == position.upper()]
    df = df.sort_values("dynasty_points", ascending=False).head(limit)
    return DynastyRankingsResponse(
        season=season,
        players=[_to_dynasty_player(r) for r in df.to_dict("records")],
    )


# ---------------------------------------------------------------------------
# Rookie rankings
# ---------------------------------------------------------------------------


@router.get("/rookies", response_model=RookieRankingsResponse)
def rookie_rankings(
    season: int = Query(..., ge=1999, le=2030),
    limit: int = Query(200, ge=1, le=1000),
) -> RookieRankingsResponse:
    """Rookie-class rankings by projected season points.

    Rookie = roster ``entry_year`` matches *season*, or ``years_exp == 0``.
    Requires the roster parquet (source of rookie detection) — 404 when
    absent, distinct from the 503 raised when preseason projections
    themselves are missing.
    """
    roster = _load_roster(season)
    if roster is None:
        raise HTTPException(
            status_code=404, detail=f"No roster data for season {season}."
        )
    df = _load_preseason(season)
    df["player_id"] = df["player_id"].astype(str)
    df = df.merge(roster, on="player_id", how="inner")
    # Roster schema drifts by season — entry_year/years_exp aren't always
    # present (see _load_roster). Missing columns degrade to "no match" for
    # that signal instead of a KeyError/500.
    entry_year = df["entry_year"] if "entry_year" in df.columns else pd.Series(
        pd.NA, index=df.index
    )
    years_exp = df["years_exp"] if "years_exp" in df.columns else pd.Series(
        pd.NA, index=df.index
    )
    is_rookie = (entry_year == season) | (years_exp == 0)
    df = df[is_rookie]
    df = df.sort_values("projected_season_points", ascending=False).head(limit)
    return RookieRankingsResponse(
        season=season,
        players=[
            RookiePlayer(
                player_id=str(r.get("player_id") or ""),
                player_name=str(r.get("player_name") or ""),
                team=r.get("team") or r.get("recent_team"),
                position=str(r.get("position") or "").upper(),
                age=None if pd.isna(r.get("age")) else float(r.get("age")),
                projected_season_points=float(r.get("projected_season_points") or 0),
                low_sample_role=(
                    str(r.get("low_sample_role"))
                    if r.get("low_sample_role") is not None
                    and pd.notna(r.get("low_sample_role"))
                    else None
                ),
            )
            for r in df.to_dict("records")
        ],
    )
