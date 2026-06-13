"""
Service layer for reading and filtering player projections.

Supports two data backends:
  1. PostgreSQL -- when DATABASE_URL is set (production)
  2. Parquet    -- local file reads (development fallback)

Preseason Fallback
------------------
When the requested weekly Parquet for a *current or future* season is either
missing or older than ``WEEKLY_STALENESS_THRESHOLD_DAYS`` days, the service
automatically serves the preseason projections for that season instead.  The
response is labelled ``source="preseason_fallback"`` so callers can surface a
freshness indicator without breaking schema compatibility.

Historical seasons (``season < current year``) are never subject to this
check — their frozen data is intentional.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from ..config import DATA_DIR, GOLD_PROJECTIONS_DIR, WEEKLY_STALENESS_THRESHOLD_DAYS
from ..db import get_connection, is_db_enabled

logger = logging.getLogger(__name__)


def _comparison_delta(row) -> Optional[float]:
    """delta_vs_ours = mean(external sources present) - ours.

    Returns None when `ours` is missing or no external sources have data.
    Module-level (M-04 fix): avoids redefining on every request.
    """
    ours = row.get("ours")
    externals = [
        row.get(s) for s in ("espn", "sleeper", "yahoo") if pd.notna(row.get(s))
    ]
    if pd.isna(ours) or not externals:
        return None
    return round(sum(externals) / len(externals) - float(ours), 2)


@dataclass(frozen=True)
class ProjectionMetaInfo:
    """Upstream metadata for a projection read.

    ``data_as_of`` is the ISO 8601 UTC mtime of the most recent parquet for
    the requested ``(season, week)``. ``source_path`` is the project-relative
    path to that parquet. Both are ``None`` when the PostgreSQL backend
    served the query (no filesystem origin).

    ``source`` is either ``"weekly"`` (normal path) or ``"preseason_fallback"``
    when the weekly file was missing / stale and the preseason projections for
    the season were served instead.
    """

    season: int
    week: int
    data_as_of: Optional[str]
    source_path: Optional[str]
    source: str = "weekly"


# ---------------------------------------------------------------------------
# Parquet helpers (development fallback)
# ---------------------------------------------------------------------------


#: Gold filenames embed a YYYYMMDD_HHMMSS generation timestamp. Sort on it,
#: NOT on filesystem mtime: in the HF Spaces deployment the repo is cloned
#: fresh at build time, so every file shares the clone-time mtime and an
#: mtime sort picks an arbitrary file (this served the 2026-04-10 parquet
#: as "latest" in the 2026-06-12 incident).
_FILENAME_TS_RE = re.compile(r"(\d{8}_\d{6})")


def _filename_sort_key(p: Path) -> Tuple[str, str]:
    m = _FILENAME_TS_RE.search(p.name)
    return (m.group(1) if m else "", p.name)


def _latest_parquet(directory: Path, pattern: str = "*.parquet") -> Optional[Path]:
    """Return the newest Parquet in *directory* by filename-embedded timestamp.

    Args:
        directory: Directory to scan (non-recursive).
        pattern: Glob pattern; pass e.g. ``"projections_half_ppr_*.parquet"``
            to scope weekly reads to one scoring format.
    """
    parquets = sorted(directory.glob(pattern), key=_filename_sort_key)
    if not parquets:
        return None
    return parquets[-1]


# Project root anchored off this file: web/api/services/projection_service.py
# -> parents[0]=services, [1]=api, [2]=web, [3]=<project>
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _project_relative(path: Path) -> str:
    """Return *path* relative to the project root when possible, else absolute."""
    try:
        return str(path.resolve().relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def _iso_utc(mtime: float) -> str:
    """Convert a POSIX mtime to an ISO 8601 UTC timestamp."""
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Preseason fallback helpers
# ---------------------------------------------------------------------------

#: Directory pattern for preseason projections (no week partition).
_PRESEASON_DIR_NAME = "preseason"


def _preseason_dir(season: int) -> Path:
    """Return the local preseason projections directory for ``season``."""
    return GOLD_PROJECTIONS_DIR / _PRESEASON_DIR_NAME / f"season={season}"


def _weekly_file_is_stale(parquet_path: Path) -> bool:
    """Return True when the file is older than the staleness threshold.

    Prefers the YYYYMMDD_HHMMSS timestamp embedded in the filename over
    filesystem mtime: in the HF Spaces deployment the repo is cloned fresh at
    build time, so mtime equals build time and would make every committed
    file — however old its contents — look fresh.
    """
    file_ts: Optional[datetime] = None
    m = _FILENAME_TS_RE.search(parquet_path.name)
    if m:
        try:
            file_ts = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            file_ts = None
    if file_ts is None:
        try:
            file_ts = datetime.fromtimestamp(
                parquet_path.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            # File vanished between discovery and stat — treat as stale.
            return True
    age = datetime.now(tz=timezone.utc) - file_ts
    return age > timedelta(days=WEEKLY_STALENESS_THRESHOLD_DAYS)


def _should_apply_fallback(season: int) -> bool:
    """Return True when the preseason fallback is applicable for ``season``.

    Only current and future seasons warrant a freshness check.  Historical
    seasons have intentionally frozen data — treating them as stale would
    incorrectly return preseason projections in place of valid backtest data.
    """
    return season >= datetime.now(tz=timezone.utc).year


def _normalize_preseason_df(
    df: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str,
) -> pd.DataFrame:
    """Normalize a raw preseason DataFrame to match the weekly response schema.

    The preseason parquet uses different column names and lacks per-week stat
    projections (floor/ceiling).  This function:
      * renames columns to the weekly convention,
      * sets ``week`` to the requested week number,
      * synthesises ``projected_floor``/``projected_ceiling`` via the same
        position-specific variance factors used by the projection engine when
        a preseason file has neither column.

    Args:
        df: Raw DataFrame from the preseason parquet.
        season: Requested NFL season year.
        week: Requested NFL week number (1-18).
        scoring_format: Scoring format string (ppr / half_ppr / standard).

    Returns:
        Normalised DataFrame whose columns are compatible with
        ``_df_to_projection_list`` in the router.
    """
    rename_map = {
        "recent_team": "team",
        "passing_yards": "proj_pass_yards",
        "passing_tds": "proj_pass_tds",
        "rushing_yards": "proj_rush_yards",
        "rushing_tds": "proj_rush_tds",
        "receptions": "proj_rec",
        "receiving_yards": "proj_rec_yards",
        "receiving_tds": "proj_rec_tds",
        "interceptions": "proj_interceptions",
        "targets": "proj_targets",
        "carries": "proj_carries",
        # Preseason-specific names
        "projected_season_points": "projected_points",
        "proj_season": "season",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Set season/week to the requested slice so the API envelope is honest.
    df["season"] = season
    df["week"] = week
    df["scoring_format"] = scoring_format

    # Derive floor/ceiling from projected_points when the preseason file does
    # not carry them.  Variance factors mirror projection_engine.py defaults.
    _POSITION_VARIANCE = {"QB": 0.45, "RB": 0.40, "WR": 0.38, "TE": 0.35}
    _DEFAULT_VARIANCE = 0.40

    if "projected_points" in df.columns:
        if "projected_floor" not in df.columns:
            variance = df["position"].map(_POSITION_VARIANCE).fillna(_DEFAULT_VARIANCE)
            df["projected_floor"] = (
                df["projected_points"] * (1.0 - variance)
            ).round(2)

        if "projected_ceiling" not in df.columns:
            variance = df["position"].map(_POSITION_VARIANCE).fillna(_DEFAULT_VARIANCE)
            df["projected_ceiling"] = (
                df["projected_points"] * (1.0 + variance)
            ).round(2)

    # Ensure projected_points >= 0 (business rule for skill positions).
    if "projected_points" in df.columns:
        df["projected_points"] = df["projected_points"].clip(lower=0)

    return df


def _get_preseason_projections_parquet(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Read preseason projections for ``season`` and normalise to weekly schema.

    Args:
        season: NFL season year.
        week: Requested week number — stamped onto every row so the response
            envelope remains consistent (actual projections are season-level).
        scoring_format: One of ppr / half_ppr / standard.
        position: Optional position filter.
        team: Optional team abbreviation filter.
        limit: Maximum rows to return.

    Returns:
        Normalised DataFrame ready for ``_df_to_projection_list``.

    Raises:
        FileNotFoundError: When no preseason parquet exists for ``season``.
    """
    preseason_dir = _preseason_dir(season)
    if not preseason_dir.exists():
        raise FileNotFoundError(
            f"No preseason projection data for season={season}"
        )

    parquet_path = _latest_parquet(preseason_dir)
    if parquet_path is None:
        raise FileNotFoundError(
            f"No preseason parquet files in {preseason_dir}"
        )

    logger.info(
        "Preseason fallback: reading %s for season=%s week=%s",
        parquet_path,
        season,
        week,
    )
    df = pd.read_parquet(parquet_path)
    df = _normalize_preseason_df(df, season, week, scoring_format)

    if position:
        df = df[df["position"].str.upper() == position.upper()]
    if team and "team" in df.columns:
        df = df[df["team"].str.upper() == team.upper()]

    df = df.sort_values("projected_points", ascending=False).head(limit)
    return df


def get_projection_meta(season: int, week: int) -> ProjectionMetaInfo:
    """Return source-parquet metadata for a given season/week.

    Never raises: when no data exists, returns a ``ProjectionMetaInfo`` with
    ``data_as_of=None`` and ``source_path=None`` so the caller can still echo
    the requested slice in the response envelope.
    """
    if is_db_enabled():
        # Postgres backend — no filesystem origin.
        return ProjectionMetaInfo(
            season=season, week=week, data_as_of=None, source_path=None
        )

    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    parquet_path = _latest_parquet(week_dir) if week_dir.exists() else None

    # Mirror the _get_projections_parquet fallback so the envelope reports
    # the file actually served, not the one that was requested.
    if _should_apply_fallback(season) and (
        parquet_path is None or _weekly_file_is_stale(parquet_path)
    ):
        preseason_dir = _preseason_dir(season)
        preseason_path = (
            _latest_parquet(preseason_dir) if preseason_dir.exists() else None
        )
        if preseason_path is not None:
            return ProjectionMetaInfo(
                season=season,
                week=week,
                data_as_of=_iso_utc(preseason_path.stat().st_mtime),
                source_path=_project_relative(preseason_path),
                source="preseason_fallback",
            )

    if parquet_path is None:
        return ProjectionMetaInfo(
            season=season, week=week, data_as_of=None, source_path=None
        )

    mtime = parquet_path.stat().st_mtime
    return ProjectionMetaInfo(
        season=season,
        week=week,
        data_as_of=_iso_utc(mtime),
        source_path=_project_relative(parquet_path),
    )


def get_latest_slice() -> ProjectionMetaInfo:
    """Return the latest (season, week) across **all** projection seasons.

    Phase 66 / v7.0 graceful defaulting helper used by ``/api/lineups`` and
    any downstream that needs "latest played anywhere" without knowing the
    current season ahead of time.

    Returns ``ProjectionMetaInfo(season=0, week=None, ...)`` when no data
    exists. Never raises.
    """
    if not GOLD_PROJECTIONS_DIR.exists():
        return ProjectionMetaInfo(
            season=0, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )

    best: Optional[ProjectionMetaInfo] = None
    for season_dir in GOLD_PROJECTIONS_DIR.glob("season=*"):
        try:
            season_num = int(season_dir.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        candidate = get_latest_week(season_num)
        if candidate.week is None:
            continue
        if best is None or (candidate.season, candidate.week) > (
            best.season,
            best.week or 0,
        ):
            best = candidate

    if best is None:
        return ProjectionMetaInfo(
            season=0, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )
    return best


def get_latest_week(season: int) -> ProjectionMetaInfo:
    """Scan ``data/gold/projections/season=<season>/week=*/`` and return the
    highest week number that has at least one parquet file.

    Returns ``ProjectionMetaInfo(week=None, data_as_of=None, source_path=None)``
    when no data exists for the requested season. Never raises — callers
    always receive a typed response even during the offseason.
    """
    season_dir = GOLD_PROJECTIONS_DIR / f"season={season}"
    if not season_dir.exists():
        return ProjectionMetaInfo(
            season=season, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )

    best_week: Optional[int] = None
    best_path: Optional[Path] = None
    best_mtime: float = -1.0
    for week_dir in season_dir.glob("week=*"):
        try:
            week_num = int(week_dir.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        parquet_path = _latest_parquet(week_dir)
        if parquet_path is None:
            continue
        if best_week is None or week_num > best_week:
            try:
                mtime = parquet_path.stat().st_mtime
            except OSError:
                # Race: file deleted between glob and stat. Skip silently.
                continue
            best_week = week_num
            best_path = parquet_path
            best_mtime = mtime

    if best_week is None or best_path is None:
        return ProjectionMetaInfo(
            season=season, week=None, data_as_of=None, source_path=None  # type: ignore[arg-type]
        )

    return ProjectionMetaInfo(
        season=season,
        week=best_week,
        data_as_of=_iso_utc(best_mtime),
        source_path=_project_relative(best_path),
    )


def _get_projections_parquet(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Read projections from local Parquet files.

    For current/future seasons, falls back to the preseason projections
    when the weekly parquet is missing or stale (see module docstring).
    """
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    # Prefer the file matching the requested scoring format; fall back to any
    # parquet for older partitions written before scoring-named files existed.
    parquet_path = None
    if week_dir.exists():
        parquet_path = _latest_parquet(
            week_dir, f"projections_{scoring_format}_*.parquet"
        ) or _latest_parquet(week_dir)

    if _should_apply_fallback(season) and (
        parquet_path is None or _weekly_file_is_stale(parquet_path)
    ):
        try:
            return _get_preseason_projections_parquet(
                season, week, scoring_format, position, team, limit
            )
        except FileNotFoundError:
            if parquet_path is None:
                raise FileNotFoundError(
                    f"No projection data for season={season} week={week} "
                    f"and no preseason data to fall back to"
                )
            logger.warning(
                "Weekly parquet %s is stale but no preseason data exists "
                "for season=%s; serving the stale file",
                parquet_path,
                season,
            )

    if parquet_path is None:
        raise FileNotFoundError(f"No projection data for season={season} week={week}")

    logger.info("Reading projections from %s", parquet_path)
    df = pd.read_parquet(parquet_path)

    rename_map = {
        "recent_team": "team",
        # Parquet stat columns are unprefixed; map to the proj_ names the router expects
        "passing_yards": "proj_pass_yards",
        "passing_tds": "proj_pass_tds",
        "rushing_yards": "proj_rush_yards",
        "rushing_tds": "proj_rush_tds",
        "receptions": "proj_rec",
        "receiving_yards": "proj_rec_yards",
        "receiving_tds": "proj_rec_tds",
        "interceptions": "proj_interceptions",
        "targets": "proj_targets",
        "carries": "proj_carries",
        # Preseason uses projected_season_points; normalize to projected_points
        "projected_season_points": "projected_points",
        "proj_season": "season",
        "proj_week": "week",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["scoring_format"] = scoring_format

    if position:
        df = df[df["position"].str.upper() == position.upper()]
    if team:
        df = df[df["team"].str.upper() == team.upper()]

    df = df.sort_values("projected_points", ascending=False).head(limit)
    return df


def _search_players_parquet(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search players from local Parquet files."""
    week_dir = GOLD_PROJECTIONS_DIR / f"season={season}" / f"week={week}"
    if not week_dir.exists():
        raise FileNotFoundError(f"No projection data for season={season} week={week}")

    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        raise FileNotFoundError(f"No parquet files in {week_dir}")

    df = pd.read_parquet(parquet_path)
    df = df.rename(columns={"recent_team": "team"})

    mask = df["player_name"].str.lower().str.contains(query.lower(), na=False)
    results = df.loc[mask, ["player_id", "player_name", "team", "position"]]
    return results.drop_duplicates().head(50)


# ---------------------------------------------------------------------------
# PostgreSQL helpers (production)
# ---------------------------------------------------------------------------


def _get_projections_db(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Read projections from PostgreSQL."""
    conditions = [
        "season = %s",
        "week = %s",
        "scoring_format = %s",
    ]
    params: list = [season, week, scoring_format]

    if position:
        conditions.append("UPPER(position) = UPPER(%s)")
        params.append(position)
    if team:
        conditions.append("UPPER(team) = UPPER(%s)")
        params.append(team)

    where = " AND ".join(conditions)
    params.append(limit)

    sql = (
        f"SELECT * FROM projections WHERE {where} "
        f"ORDER BY projected_points DESC LIMIT %s"
    )

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def _search_players_db(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search players from PostgreSQL."""
    sql = (
        "SELECT DISTINCT player_id, player_name, team, position "
        "FROM projections "
        "WHERE season = %s AND week = %s "
        "  AND LOWER(player_name) LIKE LOWER(%s) "
        "LIMIT 50"
    )
    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=[season, week, f"%{query}%"])
    return df


# ---------------------------------------------------------------------------
# Public API (auto-selects backend)
# ---------------------------------------------------------------------------


def get_projections(
    season: int,
    week: int,
    scoring_format: str,
    position: Optional[str] = None,
    team: Optional[str] = None,
    limit: int = 200,
) -> pd.DataFrame:
    """Load cached projections and return a filtered DataFrame.

    Tries PostgreSQL when DATABASE_URL is set; falls back to Parquet on any
    DB error (covers bad credentials, network failures, or stale pool state
    across worker processes).

    Args:
        season: NFL season year.
        week: Week number (1-18).
        scoring_format: One of ppr / half_ppr / standard.
        position: Optional position filter (QB/RB/WR/TE/K).
        team: Optional team abbreviation filter.
        limit: Maximum rows to return (default 200).

    Returns:
        DataFrame with projection data, sorted by projected_points desc.

    Raises:
        FileNotFoundError: If no data exists for the given season/week.
    """
    if is_db_enabled():
        try:
            logger.debug("Using PostgreSQL backend for projections")
            return _get_projections_db(
                season, week, scoring_format, position, team, limit
            )
        except Exception as exc:
            logger.warning("PostgreSQL read failed (%s); falling back to Parquet", exc)
    logger.debug("Using Parquet backend for projections")
    return _get_projections_parquet(season, week, scoring_format, position, team, limit)


def get_comparison(
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 200,
) -> dict:
    """Read the latest external_projections Silver Parquet and pivot to wide format.

    Returns a dict matching the ProjectionComparison Pydantic model. Falls back
    to an empty rows list if the Silver Parquet doesn't exist (D-06 fail-open).

    Args:
        season: NFL season year.
        week: NFL week number.
        scoring_format: Scoring format (ppr / half_ppr / standard).
        position: Optional position filter (QB/RB/WR/TE/K).
        limit: Max rows to return.

    Returns:
        Dict with keys: season, week, scoring_format, rows, source_labels, data_as_of.
    """
    # C-01 fix: anchor to NFL_DATA_DIR (env-overridable, __file__-resolved)
    # instead of CWD. Railway uvicorn's CWD is not the repo root.
    silver_root = DATA_DIR / "silver" / "external_projections"
    week_dir = silver_root / f"season={season}" / f"week={week:02d}"

    source_labels = {
        "ours": "Our projections",
        "espn": "ESPN",
        "sleeper": "Sleeper",
        "yahoo": "Yahoo via FantasyPros consensus",
    }
    data_as_of = {}

    latest = _latest_parquet(week_dir)
    if latest is None:
        return {
            "season": season,
            "week": week,
            "scoring_format": scoring_format,
            "rows": [],
            "source_labels": source_labels,
            "data_as_of": data_as_of,
        }

    try:
        long = pd.read_parquet(latest)
    except Exception as exc:
        logger.warning("Could not read external Silver %s: %s", latest, exc)
        return {
            "season": season,
            "week": week,
            "scoring_format": scoring_format,
            "rows": [],
            "source_labels": source_labels,
            "data_as_of": data_as_of,
        }

    # Filter to scoring format
    if "scoring_format" in long.columns:
        long = long[long["scoring_format"] == scoring_format]

    # Per-source freshness for the chip (max projected_at per source)
    if "projected_at" in long.columns:
        for src, group in long.groupby("source"):
            try:
                data_as_of[str(src)] = str(group["projected_at"].max())
            except Exception:
                pass

    if long.empty:
        return {
            "season": season,
            "week": week,
            "scoring_format": scoring_format,
            "rows": [],
            "source_labels": source_labels,
            "data_as_of": data_as_of,
        }

    # Pivot wide: index = (player_id, player_name, position, team), columns = source
    # Map yahoo_proxy_fp → yahoo for the API surface (provenance preserved in source_labels).
    long = long.copy()
    long["source"] = long["source"].replace({"yahoo_proxy_fp": "yahoo"})

    # Aggregate duplicates with mean (rare — different ingest passes for same week)
    grouped = (
        long.groupby(
            ["player_id", "player_name", "position", "team", "source"],
            dropna=False,
            as_index=False,
        )["projected_points"]
        .mean()
    )

    wide = grouped.pivot_table(
        index=["player_id", "player_name", "position", "team"],
        columns="source",
        values="projected_points",
        aggfunc="first",
    ).reset_index()
    wide.columns.name = None

    # Ensure all 4 source columns exist
    for src in ("ours", "espn", "sleeper", "yahoo"):
        if src not in wide.columns:
            wide[src] = None

    wide["delta_vs_ours"] = wide.apply(_comparison_delta, axis=1)

    if position:
        wide = wide[wide["position"] == position.upper()]

    # Sort by ours desc (then by mean of externals)
    wide = wide.sort_values(by="ours", ascending=False, na_position="last").head(limit)

    rows = []
    for _, row in wide.iterrows():
        def _f(x):
            return float(x) if pd.notna(x) else None
        rows.append(
            {
                "player_id": str(row["player_id"]) if pd.notna(row["player_id"]) else "",
                "player_name": str(row.get("player_name") or ""),
                "position": str(row["position"]) if pd.notna(row.get("position")) else None,
                "team": str(row["team"]) if pd.notna(row.get("team")) else None,
                "ours": _f(row.get("ours")),
                "espn": _f(row.get("espn")),
                "sleeper": _f(row.get("sleeper")),
                "yahoo": _f(row.get("yahoo")),
                "delta_vs_ours": _f(row.get("delta_vs_ours")),
            }
        )

    return {
        "season": season,
        "week": week,
        "scoring_format": scoring_format,
        "rows": rows,
        "source_labels": source_labels,
        "data_as_of": data_as_of,
    }


def search_players(
    query: str,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Search for players whose name matches *query* (case-insensitive).

    Tries PostgreSQL first; falls back to Parquet on any DB error.

    Args:
        query: Partial player name to search for.
        season: NFL season year.
        week: Week number.

    Returns:
        DataFrame of matching players (player_id, player_name, team, position).

    Raises:
        FileNotFoundError: If no data exists.
    """
    if is_db_enabled():
        try:
            return _search_players_db(query, season, week)
        except Exception as exc:
            logger.warning(
                "PostgreSQL search failed (%s); falling back to Parquet", exc
            )
    return _search_players_parquet(query, season, week)
