"""
Per-player defensive Madden-style ratings (50-99) from PFR seasonal defense stats.

Loads ``data/bronze/pfr/seasonal/def/season=YYYY/`` (walks back to the most
recent season with data — e.g. a 2026 preseason request rates players on their
2025 production) and computes a composite rating per player:

* **RUSH** (DE/DT/NT/DL) — sacks, pressures, QB knockdowns, tackles,
  missed-tackle%% (inverted).
* **LB** (LB/MLB/OLB/ILB) — tackles, coverage passer-rating allowed (inverted),
  pass-rush production, missed-tackle%% (inverted), interceptions.
* **DB** (CB/S/FS/SS/DB) — passer rating allowed (inverted), interceptions,
  yards/target allowed (inverted), completion%% allowed (inverted),
  missed-tackle%% (inverted), tackles.

Each stat becomes a percentile within the position group; the weighted
composite is shrunk toward the median by games played (small samples can't
top the board), re-ranked, and mapped to the 50-99 Madden scale used across
the matchup UI (see ``matchup-view.tsx::computeRatings`` for the offensive
equivalent).

Consumed by ``team_roster_service.load_team_roster`` which joins ratings onto
roster rows by normalized player name (+ team disambiguation on collisions).
"""

from __future__ import annotations

import glob
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..config import DATA_DIR

logger = logging.getLogger(__name__)

_PFR_DEF_ROOT = DATA_DIR / "bronze" / "pfr" / "seasonal" / "def"
_MADDEN_ROOT = DATA_DIR / "bronze" / "madden_ratings"

# Coverage stats (passer rating allowed etc.) are noise below this many targets.
_MIN_COVERAGE_TARGETS = 15
# Full credit for a composite requires this many games; fewer shrinks to median.
_FULL_CREDIT_GAMES = 10

_RUSH_POSITIONS = {"DE", "DT", "NT", "DL"}
_LB_POSITIONS = {"LB", "MLB", "OLB", "ILB"}
_DB_POSITIONS = {"CB", "DB", "S", "FS", "SS"}

_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# Roster depth_chart_position → rating groups it may legitimately draw from.
# Guards the name join: a roster DT must never inherit a same-named DB's
# rating. Edge positions (DE/OLB) are ambiguous across 3-4/4-3 schemes so
# they accept both RUSH and LB sources.
_ROSTER_POS_COMPAT = {
    "DE": {"RUSH", "LB"},
    "DT": {"RUSH"},
    "NT": {"RUSH"},
    "DL": {"RUSH", "LB"},
    "OLB": {"LB", "RUSH"},
    "ILB": {"LB"},
    "MLB": {"LB"},
    "LB": {"LB", "RUSH"},
    "CB": {"DB"},
    "DB": {"DB"},
    "S": {"DB"},
    "SAF": {"DB"},
    "FS": {"DB"},
    "SS": {"DB"},
    # Offense (EA Madden ratings cover these; PFR defense stats never will)
    "QB": {"QB"},
    "RB": {"RB"},
    "FB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "T": {"OL"},
    "OT": {"OL"},
    "G": {"OL"},
    "OL": {"OL"},
    "K": {"K"},
    "P": {"P"},
}
# Roster depth code 'C' is ambiguous: offensive center in the offense branch.
# It is resolved by the caller passing position='OL' context; map it to OL.
_ROSTER_POS_COMPAT["C"] = {"OL"}

# EA Madden position id → rating compatibility group.
_MADDEN_POS_TO_GROUP = {
    "LEDG": "RUSH",
    "REDG": "RUSH",
    "DT": "RUSH",
    "WILL": "LB",
    "MIKE": "LB",
    "SAM": "LB",
    "CB": "DB",
    "FS": "DB",
    "SS": "DB",
    "QB": "QB",
    "HB": "RB",
    "FB": "RB",
    "WR": "WR",
    "TE": "TE",
    "LT": "OL",
    "LG": "OL",
    "C": "OL",
    "RG": "OL",
    "RT": "OL",
    "LS": "OL",
    "K": "K",
    "P": "P",
}


def normalize_player_name(name: str) -> str:
    """Lowercase, strip punctuation and generational suffixes for join keys."""
    cleaned = re.sub(r"[^a-z\s]", "", str(name).lower())
    parts = [p for p in cleaned.split() if p not in _NAME_SUFFIXES]
    return " ".join(parts)


def _position_group(pos: str) -> Optional[str]:
    """Map a PFR ``pos`` value (first segment of combos like 'DE/OLB') to a group."""
    primary = str(pos).split("/")[0].strip().upper()
    if primary in _RUSH_POSITIONS:
        return "RUSH"
    if primary in _LB_POSITIONS:
        return "LB"
    if primary in _DB_POSITIONS:
        return "DB"
    return None


def _available_seasons() -> List[int]:
    if not _PFR_DEF_ROOT.exists():
        return []
    seasons = []
    for entry in _PFR_DEF_ROOT.iterdir():
        if entry.is_dir() and entry.name.startswith("season="):
            try:
                seasons.append(int(entry.name.split("=", 1)[1]))
            except ValueError:
                continue
    return sorted(seasons)


def _resolve_pfr_def_path(season: int) -> Tuple[Optional[Path], Optional[int]]:
    """Latest PFR seasonal-def parquet path for *season*, walking back when absent."""
    seasons = _available_seasons()
    ordered = [s for s in seasons if s <= season][::-1] + [
        s for s in seasons if s > season
    ]
    for candidate in ordered:
        pattern = str(_PFR_DEF_ROOT / f"season={candidate}" / "*.parquet")
        matches = sorted(glob.glob(pattern))
        if matches:
            return Path(matches[-1]), candidate
    return None, None


def _pct(series: pd.Series) -> pd.Series:
    """Percentile rank (0-1) with NaN → neutral 0.5."""
    return series.rank(pct=True).fillna(0.5)


# Composite weights per group. Keys are column names created in
# _compute_ratings; "_inv" columns are pre-inverted so higher = better.
_GROUP_WEIGHTS: Dict[str, Dict[str, float]] = {
    "RUSH": {
        "sk_pg": 0.30,
        "prss_pg": 0.30,
        "qbkd_pg": 0.10,
        "comb_pg": 0.15,
        "m_tkl_inv": 0.15,
    },
    "LB": {
        "comb_pg": 0.30,
        "rat_inv": 0.20,
        "sk_pg": 0.10,
        "prss_pg": 0.10,
        "m_tkl_inv": 0.15,
        "int_pg": 0.15,
    },
    "DB": {
        "rat_inv": 0.30,
        "int_pg": 0.20,
        "yds_tgt_inv": 0.15,
        "cmp_inv": 0.10,
        "m_tkl_inv": 0.10,
        "comb_pg": 0.15,
    },
}


def _stat(row: pd.Series, col: str, fmt: str = "{:.0f}", scale: float = 1.0) -> str:
    """NaN-safe stat formatter for tooltip strings — '—' when missing.

    PFR leaves coverage columns (rat, cmp_percent, yds_tgt) null for
    low-target players; ``"{:.0f}".format(nan)`` renders the literal string
    'nan' and ``int(nan)`` raises, so every column access must be guarded.
    """
    val = row.get(col)
    if val is None or pd.isna(val):
        return "—"
    return fmt.format(float(val) * scale)


def _detail_for_row(row: pd.Series, group: str) -> str:
    """Compact human-readable basis for the rating (surfaces in UI tooltips)."""
    g = int(row["g"]) if pd.notna(row.get("g")) else 0
    if group == "RUSH":
        return (
            f"{_stat(row, 'sk', '{:.1f}')} sacks, {_stat(row, 'prss')} pressures, "
            f"{_stat(row, 'comb')} tackles in {g} games"
        )
    if group == "LB":
        return (
            f"{_stat(row, 'comb')} tackles, {_stat(row, 'sk', '{:.1f}')} sacks, "
            f"{_stat(row, 'rat')} rating allowed in {g} games"
        )
    return (
        f"{_stat(row, 'rat')} rating allowed, {_stat(row, 'int')} INT, "
        f"{_stat(row, 'cmp_percent', '{:.0f}%', scale=100)} completions in {g} games"
    )


def _compute_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per rated player: name_key, team, group, rating, detail."""
    df = df.copy()
    df["group"] = df["pos"].map(_position_group)
    df = df[df["group"].notna()].copy()

    # Multi-team players carry per-stint rows plus a season-total '2TM' row.
    # Keep only the row with the most games per pfr_id (the aggregate) so
    # partial stints don't pollute the percentile pool — but remember every
    # real stint team so name-fallback lookups still resolve traded players.
    stint_teams: Dict[str, List[str]] = {}
    if "pfr_id" in df.columns:
        teams_upper = df["tm"].astype(str).str.upper()
        real_team_rows = df[~teams_upper.str.endswith("TM")]
        stint_teams = (
            real_team_rows.groupby("pfr_id")["tm"]
            .apply(lambda s: sorted(set(s.astype(str).str.upper())))
            .to_dict()
        )
        df = df.sort_values("g", ascending=False).drop_duplicates(
            subset=["pfr_id"], keep="first"
        )

    numeric_cols = [
        "g",
        "int",
        "tgt",
        "cmp_percent",
        "yds_tgt",
        "rat",
        "qbkd",
        "sk",
        "prss",
        "comb",
        "m_tkl_percent",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    games = df["g"].fillna(0).clip(lower=1)
    df["sk_pg"] = df["sk"].fillna(0) / games
    df["prss_pg"] = df["prss"].fillna(0) / games
    df["qbkd_pg"] = df["qbkd"].fillna(0) / games
    df["comb_pg"] = df["comb"].fillna(0) / games
    df["int_pg"] = df["int"].fillna(0) / games

    # Inverted metrics: lower raw value = better defense.
    df["m_tkl_inv"] = -df["m_tkl_percent"]
    low_sample_cov = df["tgt"].fillna(0) < _MIN_COVERAGE_TARGETS
    for src, dst in (("rat", "rat_inv"), ("yds_tgt", "yds_tgt_inv"), ("cmp_percent", "cmp_inv")):
        inv = -df[src]
        inv[low_sample_cov] = np.nan  # neutral percentile via _pct fillna
        df[dst] = inv

    rated_frames = []
    for group, weights in _GROUP_WEIGHTS.items():
        sub = df[df["group"] == group].copy()
        if sub.empty:
            continue
        composite = pd.Series(0.0, index=sub.index)
        for col, weight in weights.items():
            composite += weight * _pct(sub[col])
        # Small-sample shrink toward the median before final ranking.
        credit = (sub["g"].fillna(0) / _FULL_CREDIT_GAMES).clip(upper=1.0)
        composite = 0.5 + (composite - 0.5) * credit
        final_pct = composite.rank(pct=True)
        sub["rating"] = (50 + 49 * final_pct).round().astype(int)
        sub["rating_detail"] = sub.apply(_detail_for_row, axis=1, args=(group,))
        rated_frames.append(sub)

    if not rated_frames:
        return pd.DataFrame(
            columns=["name_key", "team", "all_teams", "group", "rating", "rating_detail"]
        )

    rated = pd.concat(rated_frames)
    rated["name_key"] = rated["player"].map(normalize_player_name)
    rated["team"] = rated["tm"].astype(str).str.upper()
    if "pfr_id" in rated.columns:
        rated["all_teams"] = rated.apply(
            lambda row: stint_teams.get(row["pfr_id"]) or [row["team"]], axis=1
        )
    else:
        rated["all_teams"] = rated["team"].map(lambda t: [t])
    return rated[["name_key", "team", "all_teams", "group", "rating", "rating_detail"]]


def load_defense_ratings(
    season: int,
) -> Tuple["DefenseRatingLookup", Optional[int]]:
    """Return ``(lookup, effective_season)`` for *season*.

    ``lookup`` resolves roster players to ratings by full normalized name,
    with a last-name + team fallback for nickname mismatches (roster "Foye
    Oluokun" vs PFR "Foyesade Oluokun").
    Returns an empty lookup when no PFR defense parquet exists anywhere.

    Cached per (file, mtime) — a fresh PFR ingest is picked up on the next
    request without a server restart.
    """
    path, effective_season = _resolve_pfr_def_path(season)
    if path is None:
        logger.warning("No PFR defense parquet under %s", _PFR_DEF_ROOT)
        return DefenseRatingLookup({}, {}), None
    return _load_defense_ratings_cached(
        str(path), path.stat().st_mtime, effective_season, season
    )


@lru_cache(maxsize=8)
def _load_defense_ratings_cached(
    path_str: str, _mtime: float, effective_season: Optional[int], season: int
) -> Tuple["DefenseRatingLookup", Optional[int]]:
    df = pd.read_parquet(path_str)
    if df.empty:
        return DefenseRatingLookup({}, {}), None

    rated = _compute_ratings(df)
    by_name: Dict[str, List[dict]] = {}
    by_last_team: Dict[Tuple[str, str], List[dict]] = {}
    for row in rated.itertuples(index=False):
        record = {
            "team": row.team,
            "group": row.group,
            "rating": int(row.rating),
            "rating_detail": row.rating_detail,
        }
        by_name.setdefault(row.name_key, []).append(record)
        last = row.name_key.rsplit(" ", 1)[-1]
        for stint_team in row.all_teams:
            by_last_team.setdefault((last, stint_team), []).append(record)
    logger.info(
        "Loaded %d defensive player ratings (season=%s, effective=%s)",
        len(rated),
        season,
        effective_season,
    )
    return DefenseRatingLookup(by_name, by_last_team), effective_season


class DefenseRatingLookup:
    """Name → rating resolution with team disambiguation and last-name fallback."""

    def __init__(
        self,
        by_name: Dict[str, List[dict]],
        by_last_team: Dict[Tuple[str, str], List[dict]],
    ) -> None:
        self._by_name = by_name
        self._by_last_team = by_last_team

    def __bool__(self) -> bool:
        return bool(self._by_name)

    @staticmethod
    def _compatible(records: List[dict], depth_position: Optional[str]) -> List[dict]:
        """Filter records to rating groups compatible with a roster position."""
        allowed = _ROSTER_POS_COMPAT.get((depth_position or "").upper())
        if not allowed:
            return records
        return [r for r in records if r["group"] in allowed]

    def rating_for(
        self,
        player_name: str,
        team: Optional[str] = None,
        depth_position: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Resolve ``(rating, rating_detail)`` or ``(None, None)``.

        Full-name match first (team-preferred on collisions; ``2TM``/``3TM``
        aggregate rows match any team). Falls back to unique last-name + team.
        When *depth_position* is provided, only position-compatible records
        match — a roster DT never inherits a same-named DB's rating.
        """
        name_key = normalize_player_name(player_name)
        records = self._compatible(self._by_name.get(name_key) or [], depth_position)
        team_upper = (team or "").upper()
        if records:
            if len(records) == 1:
                return records[0]["rating"], records[0]["rating_detail"]
            for record in records:
                if record["team"] == team_upper:
                    return record["rating"], record["rating_detail"]
            for record in records:
                if record["team"].endswith("TM"):
                    return record["rating"], record["rating_detail"]
            return None, None
        # Nickname fallback: unique last name on the same team.
        last = name_key.rsplit(" ", 1)[-1] if name_key else ""
        fallback = self._compatible(
            self._by_last_team.get((last, team_upper)) or [], depth_position
        )
        if len(fallback) == 1:
            return fallback[0]["rating"], fallback[0]["rating_detail"]
        return None, None


# ---------------------------------------------------------------------------
# EA Madden live ratings (primary source when present)
# ---------------------------------------------------------------------------


def load_madden_lookup() -> "DefenseRatingLookup":
    """Build a name → EA Madden OVR lookup from the latest Bronze parquet.

    Ratings come from ``scripts/refresh_madden_ratings.py`` (EA's live
    ratings hub — re-rated weekly during the season). Empty lookup when no
    parquet exists so callers degrade to the PFR-derived ratings.

    Cached per (file, mtime) — running the refresh script against a live
    server is picked up on the next request without a restart.
    """
    matches = sorted(glob.glob(str(_MADDEN_ROOT / "madden_ratings_*.parquet")))
    if not matches:
        logger.warning("No Madden ratings parquet under %s", _MADDEN_ROOT)
        return DefenseRatingLookup({}, {})
    path = Path(matches[-1])
    return _load_madden_lookup_cached(str(path), path.stat().st_mtime)


@lru_cache(maxsize=2)
def _load_madden_lookup_cached(path_str: str, _mtime: float) -> "DefenseRatingLookup":
    df = pd.read_parquet(path_str)
    if df.empty:
        return DefenseRatingLookup({}, {})

    by_name: Dict[str, List[dict]] = {}
    by_last_team: Dict[Tuple[str, str], List[dict]] = {}
    label = str(df["iteration_label"].mode().iloc[0]) if "iteration_label" in df else ""
    for row in df.itertuples(index=False):
        group = _MADDEN_POS_TO_GROUP.get(str(row.position))
        if group is None:
            continue
        # Clamp to the API schema's 50-99 band (EA OVRs occasionally dip
        # into the 40s for deep specialists).
        rating = max(50, min(99, int(row.overall_rating)))
        record = {
            "team": str(row.team),
            "group": group,
            "rating": rating,
            "rating_detail": f"Madden {int(row.overall_rating)} OVR ({label})",
        }
        name_key = normalize_player_name(str(row.player_name))
        by_name.setdefault(name_key, []).append(record)
        last = name_key.rsplit(" ", 1)[-1]
        by_last_team.setdefault((last, record["team"]), []).append(record)
    logger.info("Loaded %d Madden ratings (%s)", len(df), label)
    return DefenseRatingLookup(by_name, by_last_team)


class CombinedRatingLookup:
    """EA Madden OVR first; PFR stat-percentile rating as fallback.

    When both exist the EA rating wins and the PFR stat line is appended to
    the detail so the UI tooltip shows the production behind the number.
    """

    def __init__(
        self, madden: "DefenseRatingLookup", pfr: "DefenseRatingLookup"
    ) -> None:
        self._madden = madden
        self._pfr = pfr

    def __bool__(self) -> bool:
        return bool(self._madden) or bool(self._pfr)

    def rating_for(
        self,
        player_name: str,
        team: Optional[str] = None,
        depth_position: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        m_rating, m_detail = self._madden.rating_for(player_name, team, depth_position)
        p_rating, p_detail = self._pfr.rating_for(player_name, team, depth_position)
        if m_rating is not None:
            detail = m_detail or ""
            if p_detail:
                detail = f"{detail} · {p_detail}" if detail else p_detail
            return m_rating, detail or None
        return p_rating, p_detail


def load_combined_ratings(season: int) -> CombinedRatingLookup:
    """EA-Madden-first rating lookup with PFR fallback for *season*.

    Not cached itself — composition is cheap and both children are cached
    per (file, mtime), so fresh ingests are picked up without a restart.
    """
    pfr_lookup, _ = load_defense_ratings(season)
    return CombinedRatingLookup(load_madden_lookup(), pfr_lookup)
