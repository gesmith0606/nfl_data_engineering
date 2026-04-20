"""
Service layer for the team defense-metrics API
(``GET /api/teams/{team}/defense-metrics``).

Reads two silver paths:

* ``data/silver/defense/positional/season=YYYY/opp_rankings_*.parquet`` — per
  (team, week, position) average points allowed and positional rank.
* ``data/silver/teams/sos/season=YYYY/sos_*.parquet`` — per (team, week)
  opponent-adjusted EPA and strength-of-schedule ranks.

Responsibilities:

* ``load_defense_metrics(team, season, week)`` — join positional ranks and
  team-level SOS into a dict matching
  :class:`web.api.models.schemas.TeamDefenseMetricsResponse`.
* Multi-tier fallback: missing season → walk back; missing week → walk back;
  missing position → league-median 72 rating so the 4-entry positional
  contract never breaks.

Every field traces to a silver parquet column — no fabricated numbers. The
rating formula matches the phase 64-01 API-CONTRACT (corrected from the
earlier plan text which inverted the rank mapping):

    rating = round((1 - (rank - 1) / 31) * 49 + 50)  clipped to [50, 99]

so rank 1 → 99 and rank 32 → 50.
"""

from __future__ import annotations

import glob
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Ensure project src/ is importable for any utilities we might reuse later
_SRC = str(Path(__file__).resolve().parent.parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from ..config import DATA_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POSITIONAL_ROOT = DATA_DIR / "silver" / "defense" / "positional"
_SOS_ROOT = DATA_DIR / "silver" / "teams" / "sos"

# League-median rating used when a rank is unavailable. 72 sits at roughly the
# midpoint of [50, 99] and is explicitly documented in the API-CONTRACT
# fallback matrix so the frontend treats it as a "neutral" signal.
_NEUTRAL_RATING = 72

_POSITIONS: Tuple[str, ...] = ("QB", "RB", "WR", "TE")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nan_to_none(val: Any) -> Any:
    """Convert NaN / NaT / pd.NA to None for Pydantic / JSON serialisation."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _latest_parquet(pattern: str) -> Optional[Path]:
    """Return the newest parquet matching *pattern* (timestamped filenames sort
    chronologically) or ``None`` if no match exists."""
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    return Path(matches[-1])


def _available_seasons(root: Path) -> List[int]:
    """Return sorted list of integer seasons under *root* (empty if missing)."""
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


def _rank_to_rating(rank: Optional[int]) -> int:
    """Map a 1..32 defensive rank to a 50..99 rating.

    ``rank == 1`` (best defense) → 99.
    ``rank == 32`` (worst defense) → 50.
    ``rank is None / NaN`` → :data:`_NEUTRAL_RATING` (league median).

    Formula: ``round((1 - (rank - 1) / 31) * 49 + 50)`` clipped to ``[50, 99]``.
    """
    if rank is None:
        return _NEUTRAL_RATING
    try:
        if pd.isna(rank):
            return _NEUTRAL_RATING
    except (TypeError, ValueError):
        pass
    rank_int = int(rank)
    raw = round((1 - (rank_int - 1) / 31) * 49 + 50)
    return int(max(50, min(99, raw)))


# ---------------------------------------------------------------------------
# Low-level parquet loaders with season fallback
# ---------------------------------------------------------------------------


def _load_positional(season: int) -> Tuple[pd.DataFrame, int]:
    """Load the latest positional parquet for *season* with season-walk-back.

    Returns:
        (df, effective_season) — effective_season may differ from the requested
        one when a fallback occurred.

    Raises:
        FileNotFoundError: no positional parquet exists for any season.
    """
    seasons = _available_seasons(_POSITIONAL_ROOT)
    if not seasons:
        raise FileNotFoundError(f"No positional parquet found under {_POSITIONAL_ROOT}")

    # Candidates: requested season first (if present), then newest <= requested,
    # then any remaining newer seasons. This matches the roster service pattern.
    ordered: List[int] = []
    if season in seasons:
        ordered.append(season)
    ordered.extend(sorted((s for s in seasons if s < season), reverse=True))
    ordered.extend(sorted((s for s in seasons if s > season), reverse=True))

    tried: List[int] = []
    for candidate in ordered:
        pattern = str(
            _POSITIONAL_ROOT / f"season={candidate}" / "opp_rankings_*.parquet"
        )
        latest = _latest_parquet(pattern)
        if latest is None:
            tried.append(candidate)
            continue
        df = pd.read_parquet(latest)
        logger.info(
            "Loaded %d positional rows from %s (requested=%s, effective=%s)",
            len(df),
            latest,
            season,
            candidate,
        )
        return df, candidate

    raise FileNotFoundError(
        f"No positional parquet available for season {season} (tried {tried})"
    )


def _load_sos(season: int) -> Tuple[Optional[pd.DataFrame], Optional[int]]:
    """Load the latest SOS parquet for *season* with season-walk-back.

    Returns ``(df, effective_season)`` on success or ``(None, None)`` when no
    SOS parquet exists anywhere. SOS is optional — absence leaves the SOS
    fields ``None`` but does not block the response.
    """
    seasons = _available_seasons(_SOS_ROOT)
    if not seasons:
        return None, None

    ordered: List[int] = []
    if season in seasons:
        ordered.append(season)
    ordered.extend(sorted((s for s in seasons if s < season), reverse=True))
    ordered.extend(sorted((s for s in seasons if s > season), reverse=True))

    for candidate in ordered:
        pattern = str(_SOS_ROOT / f"season={candidate}" / "sos_*.parquet")
        latest = _latest_parquet(pattern)
        if latest is None:
            continue
        df = pd.read_parquet(latest)
        logger.info(
            "Loaded %d SOS rows from %s (requested=%s, effective=%s)",
            len(df),
            latest,
            season,
            candidate,
        )
        return df, candidate

    return None, None


# ---------------------------------------------------------------------------
# Core assembly logic
# ---------------------------------------------------------------------------


def _pick_positional_week(
    team_df: pd.DataFrame, requested_week: int
) -> Tuple[pd.DataFrame, int]:
    """Return the subset of *team_df* rows for the best-matching week plus the
    week number actually used.

    Prefers ``requested_week`` when rows exist; otherwise walks backward to the
    highest week <= requested; if none, walks forward to the lowest week >
    requested. Raises ``ValueError`` if *team_df* itself is empty.
    """
    if team_df.empty:
        raise ValueError("empty positional frame")

    weeks_available = sorted(int(w) for w in team_df["week"].dropna().unique())
    if not weeks_available:
        raise ValueError("team positional frame has no week values")

    # Exact match
    if requested_week in weeks_available:
        source_week = requested_week
    else:
        # Walk back: highest week <= requested
        earlier = [w for w in weeks_available if w <= requested_week]
        if earlier:
            source_week = max(earlier)
        else:
            # Walk forward: lowest available
            source_week = min(weeks_available)

    subset = team_df[team_df["week"] == source_week]
    return subset, source_week


def _build_positional_entries(
    team_week_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """Return a list of 4 entries (QB/RB/WR/TE) from a single team-week slice.

    Missing positions contribute an entry with ``avg_pts_allowed=None``,
    ``rank=None``, ``rating=_NEUTRAL_RATING`` so the frontend always receives
    the full 4-position contract.
    """
    entries: List[Dict[str, Any]] = []
    for position in _POSITIONS:
        row = team_week_df[team_week_df["position"] == position]
        if row.empty:
            entries.append(
                {
                    "position": position,
                    "avg_pts_allowed": None,
                    "rank": None,
                    "rating": _NEUTRAL_RATING,
                }
            )
            continue
        # If multiple rows somehow exist for the same position, take the first
        # deterministically.
        first = row.iloc[0]
        avg = _nan_to_none(first.get("avg_pts_allowed"))
        rank_val = _nan_to_none(first.get("rank"))
        rank_int: Optional[int]
        if rank_val is None:
            rank_int = None
        else:
            try:
                rank_int = int(rank_val)
            except (TypeError, ValueError):
                rank_int = None
        rating = _rank_to_rating(rank_int)
        entries.append(
            {
                "position": position,
                "avg_pts_allowed": (float(avg) if avg is not None else None),
                "rank": rank_int,
                "rating": rating,
            }
        )
    return entries


def _extract_sos_fields(
    sos_df: Optional[pd.DataFrame],
    team: str,
    source_week: int,
) -> Dict[str, Any]:
    """Pull (def_sos_score, def_sos_rank, adj_def_epa) for *team* at
    *source_week* from *sos_df*.

    Week fallback: walk back to the highest week <= source_week for the same
    team when the exact week has no row. Returns a dict with ``None`` values
    when SOS data is entirely absent.
    """
    result: Dict[str, Any] = {
        "def_sos_score": None,
        "def_sos_rank": None,
        "adj_def_epa": None,
    }
    if sos_df is None or sos_df.empty:
        return result

    team_rows = sos_df[sos_df["team"].astype(str).str.upper() == team.upper()]
    if team_rows.empty:
        return result

    # Try exact week first, then walk back
    chosen = team_rows[team_rows["week"] == source_week]
    if chosen.empty:
        earlier = team_rows[team_rows["week"] <= source_week]
        if not earlier.empty:
            chosen = earlier[earlier["week"] == earlier["week"].max()]
    if chosen.empty:
        # Walk forward as a last resort (e.g. requested week 0 / 1 with no prior)
        later = team_rows[team_rows["week"] >= source_week]
        if not later.empty:
            chosen = later[later["week"] == later["week"].min()]
    if chosen.empty:
        return result

    row = chosen.iloc[0]
    rank_val = _nan_to_none(row.get("def_sos_rank"))
    if rank_val is not None:
        try:
            rank_val = int(rank_val)
        except (TypeError, ValueError):
            rank_val = None
    result["def_sos_score"] = (
        float(row["def_sos_score"])
        if _nan_to_none(row.get("def_sos_score")) is not None
        else None
    )
    result["def_sos_rank"] = rank_val
    result["adj_def_epa"] = (
        float(row["adj_def_epa"])
        if _nan_to_none(row.get("adj_def_epa")) is not None
        else None
    )
    return result


def load_defense_metrics(
    team: str,
    season: int,
    week: int,
) -> Dict[str, Any]:
    """Return the defense-metrics payload for a team-week.

    Joins silver/defense/positional (per-position avg points allowed and rank)
    with silver/teams/sos (team-level SOS). Multi-tier fallback:

    * Missing season on positional → walk to latest available; ``fallback=True``.
    * Missing week on positional for the team → walk back within the season;
      ``source_week`` reflects the actual week used.
    * Missing SOS season / row → SOS fields remain ``None`` but the positional
      payload still ships (the 4-entry contract is preserved).

    Args:
        team: 3-letter NFL team code (case-insensitive).
        season: NFL season (e.g., 2024).
        week: NFL week (1..22 incl. postseason).

    Returns:
        Dict matching the :class:`TeamDefenseMetricsResponse` shape.

    Raises:
        ValueError: when *team* has no rows in the loaded positional frame.
        FileNotFoundError: when no positional parquet exists for any season.
    """
    team_upper = team.upper()

    # 1. Positional frame (required). Raises FileNotFoundError if truly absent.
    pos_df, effective_season = _load_positional(season)
    fallback = effective_season != season
    fallback_season = effective_season if fallback else None

    # 2. Resolve team. ValueError if unknown.
    known_teams = set(pos_df["team"].dropna().astype(str).str.upper().unique())
    if team_upper not in known_teams:
        raise ValueError(f"team {team_upper!r} not present in positional silver data")

    team_df = pos_df[pos_df["team"].astype(str).str.upper() == team_upper].copy()
    team_week_df, source_week = _pick_positional_week(team_df, week)

    positional_entries = _build_positional_entries(team_week_df)

    # 3. SOS frame (optional). Walk the same season logic independently so
    #    positional and SOS fallbacks don't couple.
    sos_df, _sos_effective = _load_sos(effective_season)
    sos_fields = _extract_sos_fields(sos_df, team_upper, source_week)

    overall_rating = _rank_to_rating(sos_fields["def_sos_rank"])

    return {
        "team": team_upper,
        "season": season,
        "requested_week": week,
        "source_week": source_week,
        "fallback": fallback,
        "fallback_season": fallback_season,
        "overall_def_rating": overall_rating,
        "def_sos_score": sos_fields["def_sos_score"],
        "def_sos_rank": sos_fields["def_sos_rank"],
        "adj_def_epa": sos_fields["adj_def_epa"],
        "positional": positional_entries,
    }
