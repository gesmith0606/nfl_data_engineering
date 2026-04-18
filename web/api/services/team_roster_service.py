"""
Service layer for the teams API (/api/teams/*).

Loads:
- Bronze rosters (``data/bronze/players/rosters/season=YYYY/rosters_*.parquet``)
- Bronze snap counts (``data/bronze/players/snaps/season=YYYY/week=WW/snap_counts_*.parquet``)
- Bronze schedules (``data/bronze/schedules/season=YYYY/schedules_*.parquet``)

Responsibilities:
- ``get_current_week(today)`` — resolve (season, week) from today's date against the
  latest local schedule parquet. Falls back to the max (season, week) in the data lake
  when today falls outside any gameday window (offseason).
- ``load_team_roster(team, season, week, side)`` — merge roster + snap counts,
  assign display slot hints, handle fallback to the latest available season when
  the requested season's parquet is absent.

The service reads local parquet directly (no S3 round-trip) per the offline-first
convention documented in CLAUDE.md. All API field shapes match
``.planning/phases/64-matchup-view-completion/API-CONTRACT.md``.
"""

from __future__ import annotations

import glob
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Ensure project src/ is importable for utilities that may be reused later
_SRC = str(Path(__file__).resolve().parent.parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ..config import DATA_DIR
from ..models.schemas import (
    CurrentWeekResponse,
    RosterPlayer,
    TeamRosterResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — roster positional groupings
# ---------------------------------------------------------------------------

_ROSTERS_ROOT = DATA_DIR / "bronze" / "players" / "rosters"
_SNAPS_ROOT = DATA_DIR / "bronze" / "players" / "snaps"
_SCHEDULES_ROOT = DATA_DIR / "bronze" / "schedules"

_OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE", "FB"}
_OFFENSE_DEPTH = {"QB", "RB", "WR", "TE", "FB", "T", "G", "C"}
_OL_DEPTH = {"T", "G", "C"}

_DEFENSE_POSITIONS = {"DE", "DT", "LB", "CB", "S", "DB", "DL"}
_DEFENSE_DEPTH = {
    "DE",
    "DT",
    "NT",
    "OLB",
    "ILB",
    "MLB",
    "LB",
    "CB",
    "FS",
    "SS",
    "DB",
}

_ACTIVE_STATUSES = {"ACT", "RES"}


# ---------------------------------------------------------------------------
# Helpers — NaN cleaning + parquet discovery
# ---------------------------------------------------------------------------


def _nan_to_none(val):
    """Convert NaN/NaT/pd.NA to None for JSON serialisation."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _latest_parquet(pattern: str) -> Optional[Path]:
    """Return the newest Parquet file matching *pattern* (sorted alphabetically by
    timestamped filename, which is equivalent to chronological for our scheme)."""
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    return Path(matches[-1])


def _available_seasons(root: Path) -> List[int]:
    """Return sorted list of season ints present under *root*."""
    if not root.exists():
        return []
    seasons: List[int] = []
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.startswith("season="):
            try:
                seasons.append(int(entry.name.split("=", 1)[1]))
            except ValueError:
                continue
    return sorted(seasons)


# ---------------------------------------------------------------------------
# Low-level parquet loaders
# ---------------------------------------------------------------------------


def _load_rosters(season: int) -> Tuple[pd.DataFrame, int]:
    """Load the latest roster parquet for *season*; if absent, walk back to the most
    recent season that does have a roster parquet.

    Returns:
        (df, effective_season) — effective_season may differ from the requested season
        when a fallback occurred.

    Raises:
        FileNotFoundError: no roster parquet exists for any season.
    """
    tried: List[int] = []
    # Walk from requested season downward
    requested_seasons = _available_seasons(_ROSTERS_ROOT)
    if not requested_seasons:
        raise FileNotFoundError(f"No roster parquet found under {_ROSTERS_ROOT}")

    # Candidates: requested season first (if present in dir listing), then
    # any available season <= requested, descending; then any remaining available.
    ordered: List[int] = []
    if season in requested_seasons:
        ordered.append(season)
    ordered.extend(sorted((s for s in requested_seasons if s < season), reverse=True))
    ordered.extend(sorted((s for s in requested_seasons if s > season), reverse=True))

    for candidate in ordered:
        pattern = str(_ROSTERS_ROOT / f"season={candidate}" / "rosters_*.parquet")
        latest = _latest_parquet(pattern)
        if latest is None:
            tried.append(candidate)
            continue
        df = pd.read_parquet(latest)
        logger.info(
            "Loaded %d roster rows from %s (requested season=%s, effective=%s)",
            len(df),
            latest,
            season,
            candidate,
        )
        return df, candidate

    raise FileNotFoundError(
        f"No roster parquet available for season {season} " f"(tried {tried})"
    )


def _load_snaps(season: int, week: int) -> Optional[pd.DataFrame]:
    """Load the latest snap-counts parquet for (*season*, *week*) or None if absent.

    If the exact week is missing, walk backwards (week-1, week-2, ..., 1) within the
    same season and return the first file found. When all prior weeks are absent
    return ``None`` so callers can leave snap fields null.
    """
    for w in range(week, 0, -1):
        pattern = str(
            _SNAPS_ROOT / f"season={season}" / f"week={w}" / "snap_counts_*.parquet"
        )
        latest = _latest_parquet(pattern)
        if latest is None:
            continue
        df = pd.read_parquet(latest)
        logger.info(
            "Loaded %d snap rows from %s (requested week=%s, effective=%s)",
            len(df),
            latest,
            week,
            w,
        )
        return df
    return None


def _load_schedule(season: int) -> Optional[pd.DataFrame]:
    """Return the latest schedule parquet for *season* or None."""
    pattern = str(_SCHEDULES_ROOT / f"season={season}" / "schedules_*.parquet")
    latest = _latest_parquet(pattern)
    if latest is None:
        return None
    return pd.read_parquet(latest)


def _latest_schedule_any() -> Optional[Tuple[pd.DataFrame, int]]:
    """Load the latest schedule for the highest season available."""
    seasons = _available_seasons(_SCHEDULES_ROOT)
    for season in reversed(seasons):
        df = _load_schedule(season)
        if df is not None and not df.empty:
            return df, season
    return None


# ---------------------------------------------------------------------------
# Current-week helper
# ---------------------------------------------------------------------------


def get_current_week(today: Optional[date] = None) -> CurrentWeekResponse:
    """Return the current NFL (season, week) from today's date.

    Strategy:
    1. Try ``today.year`` and ``today.year - 1`` schedule parquets in order.
    2. For each, find any row where ``gameday <= today <= gameday + 6 days`` —
       that's the current game week (``source="schedule"``).
    3. If no match in any candidate season, load the latest schedule overall and
       return its max (season, week) with ``source="fallback"``.
    4. Raises ``FileNotFoundError`` if no schedule parquet exists anywhere.
    """
    if today is None:
        today = date.today()

    # Try today's year then prior year
    for candidate_year in (today.year, today.year - 1):
        df = _load_schedule(candidate_year)
        if df is None or df.empty:
            continue
        # Ensure gameday is parseable
        gamedays = pd.to_datetime(df["gameday"], errors="coerce").dt.date
        mask = gamedays.apply(
            lambda gd: (
                gd is not None
                and not (isinstance(gd, float) and np.isnan(gd))
                and gd <= today <= gd + timedelta(days=6)
                if gd is not pd.NaT and gd is not None
                else False
            )
        )
        matched = df[mask]
        if not matched.empty:
            row = matched.iloc[0]
            return CurrentWeekResponse(
                season=int(row["season"]),
                week=int(row["week"]),
                source="schedule",
            )

    # Fallback: latest schedule parquet's max (season, week)
    result = _latest_schedule_any()
    if result is None:
        raise FileNotFoundError(f"No schedule parquet found under {_SCHEDULES_ROOT}")
    df, season = result
    max_week = int(df["week"].max())
    return CurrentWeekResponse(
        season=int(season),
        week=max_week,
        source="fallback",
    )


# ---------------------------------------------------------------------------
# Roster assembly
# ---------------------------------------------------------------------------


def _reduce_to_latest_row_per_player(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multiple weekly snapshots per ``player_id`` to the row with the
    highest ``week`` value. Handles the bronze/rosters layout where the parquet
    stores one row per (player, week) snapshot.
    """
    if df.empty:
        return df
    if "week" not in df.columns:
        return df.drop_duplicates(subset=["player_id"], keep="last")
    sorted_df = df.sort_values(["player_id", "week"], kind="stable")
    return sorted_df.drop_duplicates(subset=["player_id"], keep="last")


def _assign_offense_slot_hints(df: pd.DataFrame) -> pd.Series:
    """Return a Series of slot_hint strings (or None) aligned to df.index.

    QB: top snap → QB1, next → QB2.
    RB: top 2 → RB1, RB2.
    WR: top 3 → WR1, WR2, WR3.
    TE: top 1 → TE1.
    OL: single C snap leader → C; top 2 G by snap → LG, RG; top 2 T by snap → LT, RT.
    """
    hints = pd.Series([None] * len(df), index=df.index, dtype=object)

    # Sort stable descending by snap_pct_offense (NaN last)
    order_key = df["snap_pct_offense"].fillna(-1)

    # Skill positions keyed on depth_chart_position
    def _assign_group(depth_value: str, labels: List[str]) -> None:
        mask = df["depth_chart_position"] == depth_value
        if not mask.any():
            return
        sub = df[mask].copy()
        sub = sub.assign(_key=order_key[mask]).sort_values(
            "_key", ascending=False, kind="stable"
        )
        for lbl, idx in zip(labels, sub.index):
            hints.loc[idx] = lbl

    _assign_group("QB", ["QB1", "QB2"])
    _assign_group("RB", ["RB1", "RB2"])
    _assign_group("WR", ["WR1", "WR2", "WR3"])
    _assign_group("TE", ["TE1"])

    # OL — T, G, C
    _assign_group("C", ["C"])

    # Two Ts become LT/RT (LT = highest snap), two Gs → LG/RG
    for depth_value, slot_pair in (("T", ["LT", "RT"]), ("G", ["LG", "RG"])):
        mask = df["depth_chart_position"] == depth_value
        if not mask.any():
            continue
        sub = df[mask].copy()
        sub = sub.assign(_key=order_key[mask]).sort_values(
            "_key", ascending=False, kind="stable"
        )
        for lbl, idx in zip(slot_pair, sub.index):
            hints.loc[idx] = lbl

    return hints


def _assign_defense_slot_hints(df: pd.DataFrame) -> pd.Series:
    """Return slot_hint Series for defensive players.

    DE/OLB pooled → DE1, DE2.
    DT/NT pooled → DT1, DT2.
    ILB/MLB/LB pooled → LB1, LB2, LB3.
    CB → top 2 → CB1, CB2.
    FS → top 1 (or first "DB"), SS → top 1 (or second "DB").
    """
    hints = pd.Series([None] * len(df), index=df.index, dtype=object)
    order_key = df["snap_pct_defense"].fillna(-1)

    def _assign_pool(depth_values: List[str], labels: List[str]) -> None:
        mask = df["depth_chart_position"].isin(depth_values)
        if not mask.any():
            return
        sub = df[mask].copy()
        sub = sub.assign(_key=order_key[mask]).sort_values(
            "_key", ascending=False, kind="stable"
        )
        for lbl, idx in zip(labels, sub.index):
            hints.loc[idx] = lbl

    _assign_pool(["DE", "OLB"], ["DE1", "DE2"])
    _assign_pool(["DT", "NT"], ["DT1", "DT2"])
    _assign_pool(["ILB", "MLB", "LB"], ["LB1", "LB2", "LB3"])
    _assign_pool(["CB"], ["CB1", "CB2"])

    # FS / SS (dedicated positions first)
    fs_mask = df["depth_chart_position"] == "FS"
    if fs_mask.any():
        fs = (
            df[fs_mask]
            .copy()
            .assign(_key=order_key[fs_mask])
            .sort_values("_key", ascending=False, kind="stable")
        )
        hints.loc[fs.index[0]] = "FS"
    ss_mask = df["depth_chart_position"] == "SS"
    if ss_mask.any():
        ss = (
            df[ss_mask]
            .copy()
            .assign(_key=order_key[ss_mask])
            .sort_values("_key", ascending=False, kind="stable")
        )
        hints.loc[ss.index[0]] = "SS"

    # Generic DB fallback if no FS/SS rows
    if not fs_mask.any() or not ss_mask.any():
        db_mask = df["depth_chart_position"] == "DB"
        if db_mask.any():
            db = (
                df[db_mask]
                .copy()
                .assign(_key=order_key[db_mask])
                .sort_values("_key", ascending=False, kind="stable")
            )
            remaining = [
                lbl
                for lbl, mask in (("FS", fs_mask), ("SS", ss_mask))
                if not mask.any()
            ]
            # If both missing, put SS first then FS (per API-CONTRACT.md)
            if "FS" in remaining and "SS" in remaining:
                remaining = ["SS", "FS"]
            for lbl, idx in zip(remaining, db.index):
                hints.loc[idx] = lbl

    return hints


def _build_roster_players(
    roster_df: pd.DataFrame,
    snaps_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Join snaps onto the already-filtered roster frame and add snap_pct columns.

    Snaps use ``player`` as the name column; rosters use ``player_name``. Join key is
    ``player_name``; positions collide on common names rarely enough that MVP accepts
    the approximation.
    """
    df = roster_df.copy()
    df["snap_pct_offense"] = np.nan
    df["snap_pct_defense"] = np.nan

    if snaps_df is not None and not snaps_df.empty:
        team_col = roster_df["team"].iloc[0] if len(roster_df) else None
        snaps = snaps_df.copy()
        if team_col is not None and "team" in snaps.columns:
            snaps = snaps[snaps["team"] == team_col]
        if not snaps.empty:
            snap_agg = snaps.groupby("player", as_index=False).agg(
                snap_pct_offense=("offense_pct", "max"),
                snap_pct_defense=("defense_pct", "max"),
            )
            df = df.merge(
                snap_agg,
                left_on="player_name",
                right_on="player",
                how="left",
                suffixes=("", "_from_snaps"),
            )
            # Prefer snap-derived values when present
            df["snap_pct_offense"] = (
                df["snap_pct_offense_from_snaps"].combine_first(df["snap_pct_offense"])
                if "snap_pct_offense_from_snaps" in df.columns
                else df["snap_pct_offense"]
            )
            df["snap_pct_defense"] = (
                df["snap_pct_defense_from_snaps"].combine_first(df["snap_pct_defense"])
                if "snap_pct_defense_from_snaps" in df.columns
                else df["snap_pct_defense"]
            )
            # Drop helper columns
            for col in (
                "player",
                "snap_pct_offense_from_snaps",
                "snap_pct_defense_from_snaps",
            ):
                if col in df.columns:
                    df = df.drop(columns=[col])

    return df


def _row_to_player(row: pd.Series, slot_hint: Optional[str]) -> RosterPlayer:
    jersey = _nan_to_none(row.get("jersey_number"))
    if jersey is not None:
        try:
            jersey = int(jersey)
        except (TypeError, ValueError):
            jersey = None
    return RosterPlayer(
        player_id=str(row.get("player_id") or ""),
        player_name=str(row.get("player_name") or ""),
        team=str(row.get("team") or ""),
        position=str(row.get("position") or ""),
        depth_chart_position=_nan_to_none(row.get("depth_chart_position")),
        jersey_number=jersey,
        status=str(row.get("status") or ""),
        snap_pct_offense=_nan_to_none(row.get("snap_pct_offense")),
        snap_pct_defense=_nan_to_none(row.get("snap_pct_defense")),
        injury_status=_nan_to_none(row.get("status_description_abbr")),
        slot_hint=slot_hint,
    )


def load_team_roster(
    team: str,
    season: int,
    week: int,
    side: str = "all",
) -> TeamRosterResponse:
    """Return the roster (offense, defense, or combined) for a team-week.

    Args:
        team: 3-letter NFL team code.
        season: NFL season (e.g., 2024). Falls back to latest available if absent.
        week: NFL week (1..22). Snap pct walks back to earlier weeks if specific week
            has no snap parquet.
        side: 'offense' | 'defense' | 'all'.

    Raises:
        ValueError: when *team* is not present in the loaded roster.
    """
    side = (side or "all").lower()
    if side not in {"offense", "defense", "all"}:
        raise ValueError(f"invalid side: {side!r}")

    roster_df, effective_season = _load_rosters(season)
    fallback = effective_season != season
    fallback_season = effective_season if fallback else None

    team_upper = team.upper()
    known_teams = set(roster_df["team"].dropna().astype(str).str.upper().unique())
    if team_upper not in known_teams:
        raise ValueError(f"team {team_upper!r} not found in roster")

    # Filter to team + active statuses, collapse to one row per player_id (latest week)
    team_df = roster_df[
        (roster_df["team"].astype(str).str.upper() == team_upper)
        & (roster_df["status"].isin(_ACTIVE_STATUSES))
    ].copy()
    team_df = _reduce_to_latest_row_per_player(team_df)

    # Join snap counts (uses effective_season because snaps partition aligns with roster)
    snaps_df = _load_snaps(effective_season, week)
    team_df = _build_roster_players(team_df, snaps_df)

    # Partition into offense / defense subsets
    offense_mask = team_df["position"].isin(_OFFENSE_POSITIONS) | team_df[
        "depth_chart_position"
    ].isin(_OFFENSE_DEPTH)
    defense_mask = team_df["position"].isin(_DEFENSE_POSITIONS) | team_df[
        "depth_chart_position"
    ].isin(_DEFENSE_DEPTH)

    players: List[RosterPlayer] = []

    if side in {"offense", "all"}:
        off_df = team_df[offense_mask].copy()
        if not off_df.empty:
            off_hints = _assign_offense_slot_hints(off_df)
            for idx, row in off_df.iterrows():
                players.append(_row_to_player(row, off_hints.get(idx)))

    if side in {"defense", "all"}:
        def_df = (
            team_df[defense_mask & ~offense_mask].copy()
            if side == "all"
            else team_df[defense_mask].copy()
        )
        if not def_df.empty:
            def_hints = _assign_defense_slot_hints(def_df)
            for idx, row in def_df.iterrows():
                players.append(_row_to_player(row, def_hints.get(idx)))

    # Stable sort: slotted first, then by depth_chart_position alphabetically, then snap pct desc
    def _sort_key(p: RosterPlayer) -> Tuple[int, str, float]:
        slotted = 0 if p.slot_hint else 1
        dcp = p.depth_chart_position or "zz"
        snap = -(p.snap_pct_defense or p.snap_pct_offense or 0.0)
        return (slotted, dcp, snap)

    players.sort(key=_sort_key)

    return TeamRosterResponse(
        team=team_upper,
        season=season,
        week=week,
        side=side,  # type: ignore[arg-type]
        fallback=fallback,
        fallback_season=fallback_season,
        roster=players,
    )
