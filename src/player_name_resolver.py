"""
Player name → player_id resolver for the sentiment pipeline.

Builds a fuzzy-match index from Bronze depth-chart and roster parquet files,
then resolves free-text player names (as they appear in RSS headlines or
Sleeper news) to the canonical nfl-data-py gsis_id format (e.g. "00-0036442").

Public API
----------
>>> resolver = PlayerNameResolver()
>>> resolver.resolve("Patrick Mahomes")
'00-0033873'
>>> resolver.resolve("Josh Allen", team="BUF", position="QB")
'00-0036442'

Notes
-----
- The resolver is intentionally stateless across calls; all state lives in the
  lookup index built at construction time.
- When multiple candidates share an identical normalised name, team and
  position are used as tiebreakers.  If ambiguity remains after tiebreaking,
  None is returned so callers can skip or escalate.
- The index is rebuilt from parquet files each time a new resolver is
  instantiated.  For long-running processes, instantiate once and reuse.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Root of the local Bronze layer relative to the project root.
_BRONZE_ROOT = Path("data/bronze")

# Parquet glob patterns used to build the lookup index (most-recent first).
# depth_charts is preferred because it covers active rosters week-by-week.
_PARQUET_PATTERNS: List[str] = [
    "depth_charts/season=*/depth_charts_*.parquet",
    "players/weekly/season=*/weekly_*.parquet",
    "players/seasonal/season=*/seasonal_*.parquet",
]

# Column aliases across parquet schemas → normalised names used internally.
_COLUMN_ALIASES: Dict[str, str] = {
    "full_name": "full_name",
    "player_name": "full_name",
    "display_name": "full_name",
    "football_name": "football_name",
    "gsis_id": "player_id",
    "player_id": "player_id",
    "club_code": "team",
    "recent_team": "team",
    "team": "team",
    "position": "position",
}

# Common English suffixes to strip for matching ("Jr", "Sr", "II", "III", "IV").
_SUFFIX_PATTERN = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.IGNORECASE)

# Nickname / display-name overrides.  Maps normalised display name → canonical
# full name for cases where beat reporters use nicknames consistently.
_NICKNAME_MAP: Dict[str, str] = {
    "cmac": "christian mccaffrey",
    "aj brown": "a.j. brown",
    "dj moore": "d.j. moore",
    "dj chark": "d.j. chark",
    "tk": "travis kelce",
    "deebo": "deebo samuel",
    "hollywood": "marquise brown",
    "metcalf": "dk metcalf",
    "dk": "dk metcalf",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise(name: str) -> str:
    """Return a lowercase ASCII string stripped of punctuation and suffixes.

    Args:
        name: Raw player name string (any casing, unicode, punctuation).

    Returns:
        Normalised string suitable for fuzzy comparison.

    Examples:
        >>> _normalise("A.J. Brown Jr.")
        'aj brown'
        >>> _normalise("DK Metcalf")
        'dk metcalf'
    """
    # Decompose unicode (handles accented characters like é → e)
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    # Lower-case, strip surrounding whitespace
    name = name.lower().strip()
    # Remove dots used in initials (A.J. → AJ)
    name = name.replace(".", "")
    # Remove suffixes
    name = _SUFFIX_PATTERN.sub("", name)
    # Collapse internal whitespace
    name = re.sub(r"\s+", " ", name)
    return name


def _token_overlap(a: str, b: str) -> float:
    """Return Jaccard similarity between the token sets of two strings.

    Args:
        a: First normalised name string.
        b: Second normalised name string.

    Returns:
        Float in [0.0, 1.0]; 1.0 means identical token sets.
    """
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Index entry dataclass
# ---------------------------------------------------------------------------


class _PlayerEntry:
    """Lightweight container for a single player in the lookup index."""

    __slots__ = ("player_id", "full_name", "norm_name", "team", "position", "season")

    def __init__(
        self,
        player_id: str,
        full_name: str,
        norm_name: str,
        team: str,
        position: str,
        season: int,
    ) -> None:
        self.player_id = player_id
        self.full_name = full_name
        self.norm_name = norm_name
        self.team = team
        self.position = position
        self.season = season


# ---------------------------------------------------------------------------
# PlayerNameResolver
# ---------------------------------------------------------------------------


class PlayerNameResolver:
    """Fuzzy name-to-player_id resolver backed by local Bronze parquet files.

    Attributes:
        index: List of _PlayerEntry objects built from all available parquet
            files under data/bronze/.
        _norm_to_entries: Mapping from exact normalised name → list of entries
            (used for O(1) exact-match lookups before fuzzy fallback).

    Example:
        >>> resolver = PlayerNameResolver()
        >>> pid = resolver.resolve("Patrick Mahomes", team="KC")
        >>> print(pid)  # "00-0033873"
    """

    def __init__(self, bronze_root: Optional[Path] = None) -> None:
        """Initialise the resolver and build the lookup index.

        Args:
            bronze_root: Path to the local Bronze data directory.  Defaults to
                ``data/bronze`` relative to the current working directory.
        """
        self._root = Path(bronze_root) if bronze_root else _BRONZE_ROOT
        self.index: List[_PlayerEntry] = []
        self._norm_to_entries: Dict[str, List[_PlayerEntry]] = {}
        self._build_index()

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Scan Bronze parquet files and populate self.index.

        Reads the most-recent parquet file for each season/pattern found
        under ``self._root``.  Entries from more recent seasons are added
        first so that current rosters take precedence.

        Logs a warning if no parquet files are found (e.g. cold start before
        any Bronze ingestion has run).
        """
        seen_player_ids: set = set()
        frames: List[pd.DataFrame] = []

        for pattern in _PARQUET_PATTERNS:
            matched = sorted(self._root.glob(pattern), reverse=True)
            if not matched:
                continue
            # Group by season directory and take the latest file per season
            by_season: Dict[str, Path] = {}
            for path in matched:
                season_key = path.parent.name  # e.g. "season=2024"
                if season_key not in by_season:
                    by_season[season_key] = path
            for path in by_season.values():
                try:
                    df = pd.read_parquet(path)
                    frames.append(df)
                except Exception as exc:
                    logger.warning("Could not read %s: %s", path, exc)

        if not frames:
            logger.warning(
                "PlayerNameResolver: no parquet files found under %s. "
                "Run bronze ingestion first.  Resolver will return no matches.",
                self._root,
            )
            return

        combined = pd.concat(frames, ignore_index=True)
        combined = self._normalise_columns(combined)

        if "player_id" not in combined.columns or "full_name" not in combined.columns:
            logger.warning(
                "PlayerNameResolver: required columns missing after normalisation. "
                "Columns present: %s",
                list(combined.columns),
            )
            return

        combined = combined.dropna(subset=["player_id", "full_name"])
        # Sort newest season first so recent entries win de-dup
        if "season" in combined.columns:
            combined = combined.sort_values("season", ascending=False)

        for _, row in combined.iterrows():
            pid = str(row["player_id"]).strip()
            if not pid or pid in seen_player_ids:
                continue
            seen_player_ids.add(pid)

            full = str(row.get("full_name", "")).strip()
            # Prefer football_name (e.g. "DK" instead of "Dontavius") if present
            display = str(row.get("football_name", "")).strip()
            norm = _normalise(display if display and display != "nan" else full)

            team = str(row.get("team", "")).strip().upper()
            position = str(row.get("position", "")).strip().upper()
            season_val = row["season"] if "season" in row.index else None
            try:
                season = int(season_val) if season_val is not None and season_val == season_val else 0
            except (TypeError, ValueError):
                season = 0

            entry = _PlayerEntry(
                player_id=pid,
                full_name=full,
                norm_name=norm,
                team=team if team != "NAN" else "",
                position=position if position != "NAN" else "",
                season=season,
            )
            self.index.append(entry)
            self._norm_to_entries.setdefault(norm, []).append(entry)

        logger.info(
            "PlayerNameResolver: index built with %d unique players.", len(self.index)
        )

    def _normalise_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rename raw parquet columns to the internal schema.

        Builds a rename map that avoids duplicate target column names.  Two
        scenarios cause duplicates and are both handled:

        1. Multiple source columns map to the same target (e.g. both ``team``
           and ``club_code`` → ``team``): only the first source column is
           renamed; subsequent ones are skipped.
        2. A source column would be renamed to a target that already exists
           verbatim in the dataframe (e.g. ``player_name`` → ``full_name``
           when ``full_name`` is already a column): the existing column is
           dropped first so the renamed column becomes the sole ``full_name``.
           This preserves the alias-priority order defined in
           ``_COLUMN_ALIASES``.

        Args:
            df: DataFrame with arbitrary column names from parquet files.

        Returns:
            DataFrame with normalised column names where mappings exist,
            with no duplicate column names introduced.
        """
        existing_cols: set = set(df.columns)
        rename_map: Dict[str, str] = {}
        used_targets: set = set()
        cols_to_drop: List[str] = []

        for col in list(df.columns):
            if col not in _COLUMN_ALIASES:
                continue
            target = _COLUMN_ALIASES[col]
            if target in used_targets:
                # A prior source column already claimed this target; skip.
                continue
            if target in existing_cols and target != col:
                # The target column already exists under its canonical name.
                # Drop it so the aliased source column can take the name.
                cols_to_drop.append(target)
                existing_cols.discard(target)
            rename_map[col] = target
            used_targets.add(target)

        if cols_to_drop:
            df = df.drop(columns=cols_to_drop, errors="ignore")
        return df.rename(columns=rename_map)

    # ------------------------------------------------------------------
    # Public resolution API
    # ------------------------------------------------------------------

    def resolve(
        self,
        name: str,
        team: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a player name to a canonical player_id (gsis_id format).

        Resolution strategy (ordered by confidence):
        1. Nickname override map → normalise → exact index lookup.
        2. Exact normalised match — if one candidate, return immediately.
        3. Exact normalised match with team/position tiebreaker.
        4. Token-overlap fuzzy match (Jaccard ≥ 0.80) with tiebreakers.
        5. Return None if unresolved.

        Args:
            name: Player name as it appears in a headline or news item.
                May contain punctuation, suffixes, or nicknames.
            team: Optional 2-5 character NFL team abbreviation (e.g. "BUF").
                Used to break ties when multiple players share the same name.
            position: Optional position string (e.g. "QB", "WR").  Used as a
                secondary tiebreaker after team.

        Returns:
            The canonical player_id string if resolved, else None.

        Examples:
            >>> resolver.resolve("Josh Allen", team="BUF")
            '00-0036442'
            >>> resolver.resolve("Josh Allen", team="JAX", position="DE")
            '00-0034720'
        """
        if not name or not name.strip():
            return None

        # 1. Apply nickname overrides
        norm = _normalise(name)
        norm = _NICKNAME_MAP.get(norm, norm)

        # 2. Exact match
        candidates = self._norm_to_entries.get(norm, [])

        if not candidates:
            # 4. Fuzzy fallback — scan full index
            candidates = self._fuzzy_candidates(norm, threshold=0.80)

        if not candidates:
            logger.debug("PlayerNameResolver: no match for '%s' (norm='%s')", name, norm)
            return None

        if len(candidates) == 1:
            return candidates[0].player_id

        # 3/4. Tiebreaker: team, then position, then most recent season
        return self._break_tie(candidates, team=team, position=position)

    def resolve_batch(
        self,
        names: List[str],
        team: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Dict[str, Optional[str]]:
        """Resolve a list of names, returning a name → player_id mapping.

        Args:
            names: List of raw player name strings.
            team: Optional team hint applied to all names in the batch.
            position: Optional position hint applied to all names.

        Returns:
            Dict mapping each input name to its resolved player_id or None.
        """
        return {n: self.resolve(n, team=team, position=position) for n in names}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fuzzy_candidates(
        self, norm: str, threshold: float = 0.80
    ) -> List[_PlayerEntry]:
        """Return all index entries whose token overlap with norm ≥ threshold.

        Args:
            norm: Normalised query string.
            threshold: Minimum Jaccard similarity to consider a match.

        Returns:
            List of matching _PlayerEntry objects sorted by descending score.
        """
        results: List[Tuple[float, _PlayerEntry]] = []
        for entry in self.index:
            score = _token_overlap(norm, entry.norm_name)
            if score >= threshold:
                results.append((score, entry))
        results.sort(key=lambda t: (-t[0], -t[1].season))
        return [entry for _, entry in results]

    def _break_tie(
        self,
        candidates: List[_PlayerEntry],
        team: Optional[str],
        position: Optional[str],
    ) -> Optional[str]:
        """Disambiguate multiple candidates using team and position context.

        Priority order:
        1. Exact team match + exact position match
        2. Exact team match only
        3. Exact position match only
        4. Most recent season (highest season number)
        5. Ambiguous → return None and log a warning

        Args:
            candidates: Non-empty list of _PlayerEntry objects.
            team: Optional team abbreviation hint.
            position: Optional position hint.

        Returns:
            The best candidate's player_id, or None if still ambiguous.
        """
        team_upper = team.upper() if team else None
        pos_upper = position.upper() if position else None

        # Filter to team+position match
        if team_upper and pos_upper:
            both = [
                c for c in candidates
                if c.team == team_upper and c.position == pos_upper
            ]
            if len(both) == 1:
                return both[0].player_id
            if len(both) > 1:
                candidates = both

        # Filter to team only
        if team_upper:
            team_match = [c for c in candidates if c.team == team_upper]
            if len(team_match) == 1:
                return team_match[0].player_id
            if len(team_match) > 1:
                candidates = team_match

        # Filter to position only
        if pos_upper:
            pos_match = [c for c in candidates if c.position == pos_upper]
            if len(pos_match) == 1:
                return pos_match[0].player_id
            if len(pos_match) > 1:
                candidates = pos_match

        # Fall back to most recent season
        best = max(candidates, key=lambda c: c.season)
        if sum(1 for c in candidates if c.season == best.season) == 1:
            return best.player_id

        # Genuinely ambiguous
        names = [c.full_name for c in candidates[:3]]
        logger.warning(
            "PlayerNameResolver: ambiguous name — candidates: %s. "
            "Provide team/position hint to resolve.",
            names,
        )
        return None


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

_default_resolver: Optional[PlayerNameResolver] = None


def resolve_player_name(
    name: str,
    team: Optional[str] = None,
    position: Optional[str] = None,
) -> Optional[str]:
    """Resolve a player name using the module-level singleton resolver.

    Lazily builds the resolver on first call, then reuses it for subsequent
    calls within the same process.

    Args:
        name: Raw player name string (e.g. "Patrick Mahomes").
        team: Optional NFL team abbreviation to aid disambiguation.
        position: Optional position string to aid disambiguation.

    Returns:
        Canonical player_id (gsis_id format) or None if unresolvable.

    Examples:
        >>> resolve_player_name("Tyreek Hill", team="MIA")
        '00-0033899'
    """
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = PlayerNameResolver()
    return _default_resolver.resolve(name, team=team, position=position)
