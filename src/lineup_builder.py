#!/usr/bin/env python3
"""
Starting Lineup Builder

Identifies likely starters for all 32 NFL teams by combining depth chart
data (official depth) with snap count data (actual usage).

Depth charts provide the "declared" starters (depth_team == 1), while snap
counts provide empirical confirmation.  When snap count data is unavailable
the module falls back to depth charts alone.
"""

import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Project root (one level up from src/)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Position groups
# ---------------------------------------------------------------------------
# Offensive skill positions relevant for fantasy / lineup display.
OFFENSE_POSITIONS = {"QB", "RB", "WR", "TE", "K", "FB"}

# Defensive position groups we include when depth chart data is available.
DEFENSE_POSITIONS = {
    "CB",
    "LCB",
    "RCB",
    "NCB",
    "NB",
    "NKL",
    "DB",
    "NDB",
    "DE",
    "LDE",
    "RDE",
    "EDGE",
    "RUSH",
    "DT",
    "LDT",
    "RDT",
    "NT",
    "N",
    "DL",
    "LB",
    "ILB",
    "OLB",
    "MLB",
    "LILB",
    "RILB",
    "LOLB",
    "ROLB",
    "SLB",
    "WLB",
    "MIKE",
    "WILL",
    "SAM",
    "S",
    "SS",
    "FS",
}

# Map granular depth_position values to canonical groups for display.
_POS_GROUP_MAP: Dict[str, str] = {
    # Offense
    "QB": "QB",
    "RB": "RB",
    "HB": "RB",
    "FB": "FB",
    "WR": "WR",
    "PR": "WR",
    "KR": "WR",
    "KOR": "WR",
    "TE": "TE",
    "K": "K",
    "PK": "K",
    "KO": "K",
    # Defense
    "CB": "CB",
    "LCB": "CB",
    "RCB": "CB",
    "NCB": "CB",
    "NB": "CB",
    "NKL": "CB",
    "DB": "CB",
    "NDB": "CB",
    "NICKE": "CB",
    "DE": "DE",
    "LDE": "DE",
    "RDE": "DE",
    "EDGE": "DE",
    "RUSH": "DE",
    "DT": "DT",
    "LDT": "DT",
    "RDT": "DT",
    "NT": "DT",
    "N": "DT",
    "DL": "DT",
    "LB": "LB",
    "ILB": "LB",
    "OLB": "LB",
    "MLB": "LB",
    "LILB": "LB",
    "RILB": "LB",
    "LOLB": "LB",
    "ROLB": "LB",
    "SLB": "LB",
    "WLB": "LB",
    "MIKE": "LB",
    "WILL": "LB",
    "SAM": "LB",
    "OLB": "LB",
    "S": "S",
    "SS": "S",
    "FS": "S",
}

# Field-position layout labels for visual rendering.
FIELD_POSITION_MAP: Dict[str, str] = {
    "QB": "qb",
    "RB": "rb",
    "FB": "fb",
    "WR": "wr",
    "TE": "te",
    "K": "k",
    "DE": "edge",
    "DT": "dt",
    "LB": "lb",
    "CB": "cb",
    "S": "s",
}

# Offensive starter slots per position group.
OFFENSE_STARTER_SLOTS: Dict[str, int] = {
    "QB": 1,
    "RB": 2,
    "WR": 3,
    "TE": 1,
    "K": 1,
}

# Defensive starter slots per position group.
DEFENSE_STARTER_SLOTS: Dict[str, int] = {
    "DE": 2,
    "DT": 2,
    "LB": 3,
    "CB": 2,
    "S": 2,
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


# Re-export the team-alias normalizer at module level so existing test
# imports (`from lineup_builder import _canonical_team`) keep working;
# the canonical implementation now lives in src/utils.py.
try:
    from src.utils import canonical_team as _canonical_team  # type: ignore
except ImportError:  # script-level execution
    from utils import canonical_team as _canonical_team  # type: ignore


_STAMP = re.compile(r"(\d{8}_\d{6})")
_ET = ZoneInfo("America/New_York")
#: A depth-chart snapshot older than this, relative to the week asked about, is stale.
_MAX_SNAPSHOT_AGE_DAYS = 14
#: Games played / minutes of status data we trust: see ``_availability``.
_UNAVAILABLE = {"out", "ir", "pup", "sus", "suspended", "doubtful", "nfi", "cov", "dnr"}
#: P(plays) for the injury designations that still play some of the time. Same
#: constants as ``lineup_setter.P_PLAYS_*`` (a test pins them together).
_P_PLAYS = {"questionable": 0.71, "doubtful": 0.065}


def _file_stamp(path: Path) -> Tuple[int, float]:
    """Sort key for a Bronze/Gold file: the timestamp in its NAME, mtime only as a last
    resort. A checkout or copy rewrites mtime (the lineup CLI once read a board that was
    not the newest for weeks 4-7 because of it); the name is the data's own time."""
    m = _STAMP.search(path.name)
    if m:
        return 1, dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").timestamp()
    return 0, path.stat().st_mtime


def _latest_file(paths) -> Optional[Path]:
    paths = [Path(p) for p in paths]
    return max(paths, key=_file_stamp) if paths else None


def _normalize_depth_chart_schema(
    df: pd.DataFrame, as_of: Optional[dt.datetime] = None
) -> pd.DataFrame:
    """Translate the post-draft ESPN/Sleeper depth chart schema to nflverse.

    The 2025+ Bronze ingestion (commit ac482a1) uses a different column
    layout than the legacy nflverse `import_depth_charts` output:

      legacy (<=2024) -> new (2025+)
      ---------------------------------
      club_code      -> team
      full_name      -> player_name
      depth_position -> pos_abb
      depth_team     -> pos_rank
      week           -> (absent: rolling daily snapshots keyed by ``dt``)

    The Bronze file holds EVERY daily snapshot (289 of them, 773k rows, by mid-November
    2026). We keep exactly one: the newest snapshot at or before ``as_of`` (the week's
    first kickoff; the newest overall when ``as_of`` is None). The old code kept the
    newest ROW per player across all snapshots, so a player cut or traded weeks ago
    still "started" for his old team. If every snapshot is newer than ``as_of`` the
    earliest is used and ``df.attrs['snapshot']`` says so. ``week`` is synthesized as 1
    so legacy week filters stay a no-op.
    """
    # Detect new schema by its signature columns rather than the absence of
    # legacy ones — guards against partial-migration frames that carry one
    # legacy column but not the others (would silently no-op the rename and
    # produce a malformed result).
    has_new_schema = "pos_abb" in df.columns and "team" in df.columns
    has_legacy_schema = all(
        c in df.columns
        for c in ("club_code", "full_name", "depth_position", "depth_team", "week")
    )

    if has_legacy_schema and not has_new_schema:
        return df  # already nflverse

    if not has_new_schema:
        logger.warning(
            "Unrecognized depth-chart schema (cols=%s)", list(df.columns)[:10]
        )
        return df

    df = df.copy()
    info: Dict[str, Any] = {}
    if "dt" in df.columns:
        stamps = pd.to_datetime(df["dt"], utc=True, errors="coerce")
        snaps = sorted(stamps.dropna().unique())
        if snaps:
            eligible = [x for x in snaps if as_of is None or x <= pd.Timestamp(as_of)]
            chosen = eligible[-1] if eligible else snaps[0]
            df = df[stamps == chosen]
            info = {
                "snapshot": chosen.isoformat(),
                "predates_data": bool(as_of is not None and not eligible),
                "as_of": None if as_of is None else pd.Timestamp(as_of).isoformat(),
            }
    df = df.drop_duplicates(subset=["team", "gsis_id", "pos_abb"], keep="first")

    df = df.rename(
        columns={
            "team": "club_code",
            "player_name": "full_name",
            "pos_abb": "depth_position",
            "pos_rank": "depth_team",
        }
    )
    df["position"] = df["depth_position"]
    df["week"] = 1
    df.attrs["snapshot"] = info
    return df


def _load_schedule(season: int) -> pd.DataFrame:
    """Bronze schedule for the season (newest file by name), or an empty frame."""
    sched_dir = _DATA_DIR / "bronze" / "schedules" / f"season={season}"
    latest = _latest_file(sched_dir.glob("*.parquet"))
    if latest is None:
        return pd.DataFrame()
    return pd.read_parquet(latest)


def _week_kickoffs(schedule: pd.DataFrame, week: int) -> List[dt.datetime]:
    """Kickoff instants (UTC) of every game in ``week``."""
    if schedule.empty or "week" not in schedule.columns:
        return []
    out = []
    for row in schedule[schedule["week"] == week].itertuples(index=False):
        try:
            day = dt.date.fromisoformat(str(row.gameday))
            hh, mm = str(getattr(row, "gametime", None) or "13:00").split(":")[:2]
            out.append(
                dt.datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=_ET)
                .astimezone(dt.timezone.utc)
            )
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def _load_depth_charts(season: int, week: Optional[int] = None) -> pd.DataFrame:
    """Load Bronze depth chart data for the given season as of ``week``'s first kickoff.

    Returns an empty DataFrame if no data is found. The file is the newest by the
    timestamp in its name; the snapshot inside it is the newest one at or before the
    week starts (see :func:`_normalize_depth_chart_schema`).
    """
    dc_dir = _DATA_DIR / "bronze" / "depth_charts" / f"season={season}"
    latest = _latest_file(dc_dir.glob("*.parquet"))
    if latest is None:
        logger.warning("No depth chart data for season=%d", season)
        return pd.DataFrame()
    as_of = None
    if week is not None:
        starts = _week_kickoffs(_load_schedule(season), week)
        as_of = min(starts) if starts else None
    df = _normalize_depth_chart_schema(pd.read_parquet(latest), as_of=as_of)
    logger.info(
        "Loaded depth charts: season=%d, rows=%d from %s", season, len(df), latest.name
    )
    return df


def _load_snap_counts(season: int, week: int) -> pd.DataFrame:
    """Load Bronze snap count data for the given season/week.

    Returns an empty DataFrame if no data is found.
    """
    # NOTE (2026-08-09 completeness audit): this used to read
    # data/bronze/snap_counts/, a path that has never existed anywhere —
    # the actual ingestion CLI (scripts/bronze_ingestion_simple.py,
    # PLAYER_S3_KEYS in src/config.py) writes to data/bronze/players/snaps/,
    # the same path team_roster_service.py already reads correctly. The old
    # path made this function a guaranteed silent no-op (empty DataFrame,
    # logger.debug only) in every environment, dev included.
    sc_dir = (
        _DATA_DIR / "bronze" / "players" / "snaps" / f"season={season}" / f"week={week}"
    )
    if not sc_dir.exists():
        # Try season-level directory (some ingestion layouts)
        sc_dir = _DATA_DIR / "bronze" / "players" / "snaps" / f"season={season}"
    latest = _latest_file(sc_dir.glob("*.parquet"))
    if latest is None:
        logger.debug("No snap count data for season=%d week=%d", season, week)
        return pd.DataFrame()
    df = pd.read_parquet(latest)
    if "week" in df.columns:
        df = df[df["week"] == week]
    logger.info(
        "Loaded snap counts: season=%d week=%d, rows=%d",
        season,
        week,
        len(df),
    )
    return df


def _load_projections(season: int, week: int) -> pd.DataFrame:
    """Load Gold projections for the given season/week.

    Returns an empty DataFrame if unavailable.
    """
    proj_dir = _DATA_DIR / "gold" / "projections" / f"season={season}" / f"week={week}"
    if not proj_dir.exists():
        logger.debug("No projection data for season=%d week=%d", season, week)
        return pd.DataFrame()
    # ``*_derived`` boards are an experiment's output, never the published projections.
    latest = _latest_file(p for p in proj_dir.glob("*.parquet") if "derived" not in p.name)
    if latest is None:
        return pd.DataFrame()
    df = pd.read_parquet(latest)
    logger.info("Loaded projections: season=%d week=%d, rows=%d", season, week, len(df))
    return df


def _trailing_snap_share(season: int, week: int, weeks_back: int = 3) -> Dict[Tuple[str, str], float]:
    """``(TEAM, player name) -> mean offensive snap share`` over the weeks BEFORE ``week``.

    The week's own snap counts are the outcome, not a signal (they do not exist yet for the
    upcoming week, which is why ``snap_pct`` was empty for every starter, and they are
    look-ahead for any week already played).
    """
    shares: Dict[Tuple[str, str], List[float]] = {}
    for prior in range(max(1, week - weeks_back), week):
        snaps = _load_snap_counts(season, prior)
        if snaps is None or snaps.empty:
            continue
        col = "offense_pct" if "offense_pct" in snaps.columns else "snap_pct"
        if col not in snaps.columns:
            continue
        team_col = "team" if "team" in snaps.columns else "club_code"
        name_col = "player" if "player" in snaps.columns else "full_name"
        for team, name, val in zip(snaps[team_col], snaps[name_col], snaps[col]):
            try:
                shares.setdefault((str(team).upper(), str(name)), []).append(float(val))
            except (ValueError, TypeError):
                continue
    return {k: float(np.mean(v)) for k, v in shares.items()}


class _Availability:
    """Who cannot play in a week, and who is a doubt, from what is on disk.

    * ``bye_teams``: canonical codes with no game in the Bronze schedule for the week
      (None when the schedule is unavailable).
    * ``status``: ``gsis_id -> status`` (Out / Questionable / ...), the week's official
      nflverse injury report first, then the Gold projection's ``injury_status`` for
      anyone the report does not list.
    * ``notes``: why anything is degraded, surfaced to the API's ``degraded`` flag.
    """

    def __init__(self, bye_teams: Optional[Set[str]], status: Dict[str, str], notes: List[str]):
        self.bye_teams, self.status, self.notes = bye_teams, status, notes

    def is_bye(self, team: str) -> bool:
        return self.bye_teams is not None and _canonical_team(team) in self.bye_teams


def _availability(
    season: int,
    week: int,
    teams: List[str],
    projections_df: Optional[pd.DataFrame] = None,
) -> _Availability:
    notes: List[str] = []
    # --- bye weeks from the schedule
    sched = _load_schedule(season)
    wk = sched[sched["week"] == week] if not sched.empty and "week" in sched.columns else sched
    bye: Optional[Set[str]] = None
    if wk.empty:
        notes.append(f"no schedule for {season} week {week}: bye weeks not applied")
    else:
        playing = {_canonical_team(t) for t in list(wk["home_team"]) + list(wk["away_team"])}
        bye = {_canonical_team(t) for t in teams} - playing
    # --- injury designations
    status: Dict[str, str] = {}
    proj = projections_df if projections_df is not None else _load_projections(season, week)
    if proj is not None and not proj.empty and {"player_id", "injury_status"} <= set(proj.columns):
        for pid, st in zip(proj["player_id"], proj["injury_status"]):
            if isinstance(st, str) and st and st.lower() not in ("active", "nan", "none"):
                status[str(pid)] = st
    inj_dir = _DATA_DIR / "bronze" / "players" / "injuries" / f"season={season}"
    latest = _latest_file(inj_dir.glob("injuries_*.parquet"))
    official = 0
    if latest is not None:
        inj = pd.read_parquet(latest)
        if {"week", "gsis_id", "report_status"} <= set(inj.columns):
            for pid, st in zip(inj.loc[inj["week"] == week, "gsis_id"], inj.loc[inj["week"] == week, "report_status"]):
                if isinstance(st, str) and st:
                    status[str(pid)] = st  # the official report wins over the projection tag
                    official += 1
    if not status and not official:
        notes.append(f"no injury report or projection statuses for week {week}: Out/Questionable not applied")
    return _Availability(bye, status, notes)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _resolve_position_group(depth_position: str, position: str) -> str:
    """Map a depth chart position to a canonical group.

    Falls back to the roster ``position`` column when depth_position
    is not recognized.
    """
    dp = str(depth_position).strip()
    if dp in _POS_GROUP_MAP:
        return _POS_GROUP_MAP[dp]
    pos = str(position).strip()
    if pos in _POS_GROUP_MAP:
        return _POS_GROUP_MAP[pos]
    return pos


def _assign_field_position(pos_group: str, rank_in_group: int) -> str:
    """Return a field-position label for visual layout.

    ``rank_in_group`` is 1-based (1 = first starter at that group).
    """
    base = FIELD_POSITION_MAP.get(pos_group, pos_group.lower())
    if pos_group == "WR":
        label_map = {1: "wr_left", 2: "wr_right", 3: "wr_slot"}
        return label_map.get(rank_in_group, f"wr_{rank_in_group}")
    if pos_group == "RB":
        if rank_in_group == 1:
            return "rb"
        return f"rb_{rank_in_group}"
    if pos_group == "DE":
        label_map = {1: "edge_left", 2: "edge_right"}
        return label_map.get(rank_in_group, f"edge_{rank_in_group}")
    if pos_group == "DT":
        label_map = {1: "dt_left", 2: "dt_right"}
        return label_map.get(rank_in_group, f"dt_{rank_in_group}")
    if pos_group == "CB":
        label_map = {1: "cb_left", 2: "cb_right"}
        return label_map.get(rank_in_group, f"cb_{rank_in_group}")
    if pos_group == "S":
        label_map = {1: "s_left", 2: "s_right"}
        return label_map.get(rank_in_group, f"s_{rank_in_group}")
    if pos_group == "LB":
        label_map = {1: "lb_left", 2: "lb_mid", 3: "lb_right"}
        return label_map.get(rank_in_group, f"lb_{rank_in_group}")
    return base


def _compute_starter_confidence(
    is_depth_starter: bool,
    snap_pct: Optional[float],
) -> float:
    """Return a 0-1 confidence score for starter designation.

    ``snap_pct`` is a 0.0-1.0 fraction (matching the rest of the codebase,
    e.g. ``player_feature_engineering``'s ``snap_pct_roll3 >= 0.20`` filter),
    not a 0-100 percentage.

    Heuristic:
      - depth_team=1 alone => 0.70
      - snap_pct >= 0.60 alone => 0.65
      - both => 0.85 + bonus up to 0.15 based on snap_pct
    """
    if is_depth_starter and snap_pct is not None and snap_pct >= 0.50:
        return min(1.0, 0.85 + (snap_pct - 0.50) / 3.333)
    if is_depth_starter:
        return 0.70
    if snap_pct is not None and snap_pct >= 0.60:
        return 0.65
    return 0.40


def get_team_starters(
    season: int,
    week: int,
    team: Optional[str] = None,
    projections_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Get starting lineup for all teams (or a specific team) for a given week.

    Combines depth charts (official depth) with trailing snap counts (recent usage)
    and the week's availability (bye, Out / Doubtful / Questionable) to identify who
    will actually start.

    Note:
        For 2025+ seasons the Bronze depth chart is a rolling set of daily snapshots;
        the one used is the newest at or before the week's first kickoff
        (:func:`_normalize_depth_chart_schema`), so ``week`` matters. Calling with
        ``week=0`` returns an empty DataFrame (no valid weeks).

        A player who is on bye, ruled Out, on IR or Doubtful is NOT a starter: the
        next man up takes the slot, and the unavailable player stays in the frame
        with ``is_starter=False`` and his status in ``injury_status``. A team on bye
        has no starters (its depth-chart players are listed with ``injury_status``
        ``"BYE"``). ``starter_confidence`` is the chance he starts: his recent snap
        share, times the chance he plays (Questionable = 71%).

        ``df.attrs["degraded_reasons"]`` lists every fallback taken (snapshot older
        than the week, schedule or injury data missing) so the API can say so rather
        than serve a guess as fact.

    Args:
        season: NFL season year.
        week: Week number (1-18 regular season).
        team: Optional 2/3 letter team abbreviation (e.g. ``"KC"``).
        projections_df: Gold projections already loaded by the caller; their
            ``injury_status`` fills in statuses the official report lacks.

    Returns:
        DataFrame with columns:
            team, position, position_group, depth_position, player_name,
            player_id, depth_rank, snap_pct, is_starter, starter_confidence,
            injury_status, field_position, side (offense / defense).
    """
    dc = _load_depth_charts(season, week)
    degraded: List[str] = []
    snapshot = dict(getattr(dc, "attrs", {}).get("snapshot") or {})
    if snapshot.get("predates_data"):
        degraded.append(
            f"depth chart: no snapshot at or before week {week} kickoff; using the "
            f"earliest ({snapshot.get('snapshot')})"
        )
    elif snapshot.get("snapshot") and snapshot.get("as_of"):
        age = (pd.Timestamp(snapshot["as_of"]) - pd.Timestamp(snapshot["snapshot"])).days
        if age > _MAX_SNAPSHOT_AGE_DAYS:
            degraded.append(
                f"depth chart is {age} days older than week {week} "
                f"(snapshot {snapshot['snapshot']})"
            )
    if dc.empty:
        logger.error("No depth chart data available for season=%d", season)
        return pd.DataFrame()

    # --- Filter to latest available week <= target week ---
    dc["week"] = pd.to_numeric(dc["week"], errors="coerce")
    dc = dc.dropna(subset=["week"])
    available_weeks = dc["week"].unique()
    valid_weeks = [w for w in available_weeks if w <= week]
    if not valid_weeks:
        logger.warning("No depth chart weeks <= %d for season=%d", week, season)
        return pd.DataFrame()

    # For each player, keep the row from the latest week they appear in.
    # This handles mid-season roster moves.
    dc = dc[dc["week"].isin(valid_weeks)]
    dc = dc.sort_values("week", ascending=False)
    dc = dc.drop_duplicates(subset=["club_code", "gsis_id", "position"], keep="first")

    if team:
        dc = dc[dc["club_code"] == team.upper()]
        if dc.empty:
            logger.warning("No depth chart data for team=%s", team)
            return pd.DataFrame()

    # --- Coerce depth_team to a sortable numeric so the per-group ranking
    # below picks lower-string players first (1 before 2 before 3). The
    # legacy nflverse schema stored this as a string; the new ESPN/Sleeper
    # schema stores it as an int. Both coerce cleanly. ---
    dc["depth_team_ord"] = pd.to_numeric(
        dc["depth_team"], errors="coerce"
    ).fillna(99)
    # Retain the boolean flag for downstream reporting (the player IS marked
    # starting somewhere on the depth chart). It is no longer used to filter
    # the candidate pool — see comment in the per-group loop below.
    dc["is_depth_starter"] = dc["depth_team_ord"] <= 1

    # --- Recent usage: snap share over the PRIOR weeks (the week's own are the outcome) ---
    snap_lookup = _trailing_snap_share(season, week)
    avail = _availability(
        season, week, sorted(dc["club_code"].dropna().astype(str).unique()), projections_df
    )
    degraded.extend(avail.notes)

    # --- Build result ---
    rows: List[Dict] = []
    dc["position_group"] = dc.apply(
        lambda r: _resolve_position_group(r["depth_position"], r["position"]),
        axis=1,
    )

    # Filter to offensive & defensive positions we care about
    offense_groups = set(OFFENSE_STARTER_SLOTS.keys()) | {"FB"}
    defense_groups = set(DEFENSE_STARTER_SLOTS.keys())
    all_groups = offense_groups | defense_groups
    dc = dc[dc["position_group"].isin(all_groups)]

    # For each team + position group, pick the top max_slots players by
    # depth_team ascending. We do NOT pre-filter to depth_team==1:
    #
    # * Legacy nflverse depth charts mark every "first string" player at a
    #   formation slot as depth_team=1 (e.g. 3 WRs in 11-personnel each get
    #   depth_team=1), so a `head(max_slots)` from the depth_team=1 subset
    #   produces the right starters. Sorting by depth_team asc in that case
    #   is a no-op for the picked rows.
    # * New ESPN/Sleeper depth charts encode depth as a strict 1/2/3 ordering
    #   per pos_abb — only ONE player per slot has depth_team=1. To recover
    #   "WR1 + WR2 + WR3" we have to pull the top 3 ranks within the WR
    #   position group regardless of whether they're 1, 2, or 3.
    #
    # Sorting by depth_team asc (then snap_pct desc, then alphabetical)
    # produces the right starters under both schemas.
    candidates = dc.copy()

    for (club, pos_group), group_df in candidates.groupby(
        ["club_code", "position_group"]
    ):
        side = "offense" if pos_group in offense_groups else "defense"
        slots_map = (
            OFFENSE_STARTER_SLOTS if side == "offense" else DEFENSE_STARTER_SLOTS
        )
        max_slots = slots_map.get(pos_group, 1)

        # Skip return specialists (PR/KR mapped to WR but with those depth_positions)
        group_df = group_df[~group_df["depth_position"].isin(["PR", "KR", "KOR"])]
        if group_df.empty:
            continue

        # Within this group, sort by depth_team asc (lowest-numbered first),
        # then snap_pct desc, then alphabetical for stability.
        group_df = group_df.copy()
        group_df["_snap_pct"] = group_df.apply(
            lambda r: snap_lookup.get(
                (str(r["club_code"]).upper(), str(r["full_name"])), np.nan
            ),
            axis=1,
        )
        group_df = group_df.sort_values(
            ["depth_team_ord", "_snap_pct", "full_name"],
            ascending=[True, False, True],
        )

        # Walk the depth chart in order. Anyone unavailable who would have started is
        # listed as a non-starter and the next man up takes the slot; a team on bye
        # has no starters at all.
        on_bye = avail.is_bye(club)
        picked: List[Tuple[Any, Optional[str]]] = []
        sidelined: List[Tuple[Any, str]] = []
        for _, row in group_df.iterrows():
            st = avail.status.get(str(row.get("gsis_id", "")))
            reason = (
                "BYE"
                if on_bye
                else (st if st and st.lower() in _UNAVAILABLE else None)
            )
            if reason:
                if len(sidelined) < max_slots:
                    sidelined.append((row, reason))
                if on_bye and len(sidelined) >= max_slots:
                    break
                continue  # keep walking: the next man up takes his slot
            picked.append((row, st))
            if len(picked) >= max_slots:
                break

        def _emit(row, rank, is_starter, status, confidence):
            snap_pct_val = row["_snap_pct"] if not np.isnan(row["_snap_pct"]) else None
            rows.append(
                {
                    "team": club,
                    "position": row["position"],
                    "position_group": pos_group,
                    "depth_position": row["depth_position"],
                    "player_name": row["full_name"],
                    "player_id": row.get("gsis_id", ""),
                    "depth_rank": rank,
                    "snap_pct": snap_pct_val,
                    "is_starter": is_starter,
                    "starter_confidence": round(confidence, 2),
                    "injury_status": status,
                    "field_position": _assign_field_position(pos_group, rank),
                    "side": side,
                }
            )

        for rank, (row, st) in enumerate(picked, start=1):
            snap = row["_snap_pct"] if not np.isnan(row["_snap_pct"]) else None
            plays = _P_PLAYS.get(str(st).lower(), 1.0)
            _emit(row, rank, True, st, _compute_starter_confidence(True, snap) * plays)
        for rank, (row, reason) in enumerate(sidelined, start=len(picked) + 1):
            _emit(row, rank, False, reason, 0.0)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result.attrs["degraded_reasons"] = degraded
    # Sort by team, side (offense first), position group, rank
    side_order = {"offense": 0, "defense": 1}
    result["_side_ord"] = result["side"].map(side_order)
    pos_order = ["QB", "RB", "FB", "WR", "TE", "K", "DE", "DT", "LB", "CB", "S"]
    pos_rank = {p: i for i, p in enumerate(pos_order)}
    result["_pos_ord"] = result["position_group"].map(pos_rank).fillna(99)
    result = result.sort_values(["team", "_side_ord", "_pos_ord", "depth_rank"]).drop(
        columns=["_side_ord", "_pos_ord"]
    )
    result = result.reset_index(drop=True)
    result.attrs["degraded_reasons"] = degraded

    return result


def get_team_lineup_with_projections(
    season: int,
    week: int,
    team: str,
    scoring_format: str = "half_ppr",
    projections_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Get starting lineup with fantasy projections for a specific team.

    Loads starters via :func:`get_team_starters` and joins Gold projections
    when available.

    Args:
        season: NFL season year.
        week: Week number.
        team: Team abbreviation (e.g. ``"KC"``).
        scoring_format: One of ``"ppr"``, ``"half_ppr"``, ``"standard"``.
        projections_df: Pre-loaded projections to join instead of reading the
            weekly Gold parquet from local disk. The web API passes the
            projection service's DataFrame here so lineups inherit its
            DB/preseason fallback; ``None`` keeps the local-disk read.

    Returns:
        DataFrame with columns:
            team, position, position_group, field_position, player_name,
            player_id, projected_points, projected_floor, projected_ceiling,
            snap_pct, depth_rank, is_starter, starter_confidence, side.
    """
    starters = get_team_starters(season, week, team=team, projections_df=projections_df)
    if starters.empty:
        return starters
    degraded = list(starters.attrs.get("degraded_reasons") or [])

    proj = projections_df if projections_df is not None else _load_projections(season, week)
    if proj.empty:
        starters["projected_points"] = np.nan
        starters["projected_floor"] = np.nan
        starters["projected_ceiling"] = np.nan
        return starters

    # Normalize join keys
    proj_team_col = "recent_team" if "recent_team" in proj.columns else "team"
    proj_name_col = "player_name" if "player_name" in proj.columns else "full_name"
    proj_id_col = "player_id" if "player_id" in proj.columns else None

    # A non-empty projections frame may still lack floor/ceiling (or even
    # points) — e.g. a source that carries only projected_points, or a stale
    # local parquet from an older schema. Guarantee the value columns exist so
    # the column selection below degrades to NaN instead of raising KeyError.
    proj = proj.copy()
    for _col in ("projected_points", "projected_floor", "projected_ceiling"):
        if _col not in proj.columns:
            proj[_col] = np.nan

    # Try joining on player_id first, fall back to name+team. We also bring
    # the projection's team along so we can null out any stale-team
    # projection (the player was traded / promoted and the Gold parquet
    # still has him scored under his previous team's role). Keying on
    # player_id alone would otherwise let, e.g., Malik Willis's GB-backup
    # 53.8-pt projection display under his MIA-starter depth-chart slot.
    if proj_id_col and "player_id" in starters.columns:
        proj_subset = proj[
            [
                proj_id_col,
                proj_team_col,
                "projected_points",
                "projected_floor",
                "projected_ceiling",
            ]
        ].copy()
        proj_subset = proj_subset.rename(
            columns={proj_id_col: "player_id", proj_team_col: "_proj_team"}
        )
        proj_subset = proj_subset.drop_duplicates(subset=["player_id"], keep="first")
        merged = starters.merge(proj_subset, on="player_id", how="left")
    else:
        proj_subset = proj[
            [
                proj_team_col,
                proj_name_col,
                "projected_points",
                "projected_floor",
                "projected_ceiling",
            ]
        ].copy()
        proj_subset = proj_subset.rename(
            columns={proj_team_col: "_proj_team", proj_name_col: "player_name"}
        )
        proj_subset = proj_subset.drop_duplicates(
            subset=["_proj_team", "player_name"], keep="first"
        )
        # Normalize team codes on both sides before joining (same
        # canonicalization used below for the stale-team check) so alias
        # codes like KAN/KC, LAR/LA don't silently miss matches.
        starters_for_merge = starters.copy()
        starters_for_merge["_team_canon"] = starters_for_merge["team"].apply(_canonical_team)
        proj_subset["_proj_team_canon"] = proj_subset["_proj_team"].apply(_canonical_team)
        merged = starters_for_merge.merge(
            proj_subset,
            left_on=["_team_canon", "player_name"],
            right_on=["_proj_team_canon", "player_name"],
            how="left",
        ).drop(columns=["_team_canon", "_proj_team_canon"])

    # Drop projections where the depth chart's team disagrees with the
    # projection's team — the player has moved and the score reflects his
    # previous role. The frontend renders NaN as "--" rather than a stale
    # number. Aliases canonicalized first so KAN/KC, LAR/LA, etc. don't
    # false-positive.
    if "_proj_team" in merged.columns:
        proj_canon = merged["_proj_team"].apply(_canonical_team)
        dc_canon = merged["team"].apply(_canonical_team)
        team_mismatch = merged["_proj_team"].notna() & (proj_canon != dc_canon)
        if team_mismatch.any():
            stale = merged.loc[
                team_mismatch, ["team", "player_name", "_proj_team"]
            ].head(5)
            logger.warning(
                "Dropping %d stale projection(s) where depth-chart team "
                "differs from projection team. Sample: %s",
                int(team_mismatch.sum()),
                stale.to_dict("records"),
            )
            merged.loc[
                team_mismatch,
                ["projected_points", "projected_floor", "projected_ceiling"],
            ] = np.nan
        merged = merged.drop(columns=["_proj_team"])

    merged.attrs["degraded_reasons"] = degraded
    return merged
