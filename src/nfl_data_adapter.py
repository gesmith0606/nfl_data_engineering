"""
Adapter module isolating all nfl-data-py import_* calls.

This is the ONLY module in the project that should ``import nfl_data_py``.
All other code fetches NFL data through :class:`NFLDataAdapter`.
"""

import io
import logging
import os
import urllib.request
from typing import Dict, List, Optional

import pandas as pd

from src.config import (
    STATS_PLAYER_COLUMN_MAP,
    STATS_PLAYER_MIN_SEASON,
    validate_season_for_type,
)

logger = logging.getLogger(__name__)


def format_validation_output(result: Dict[str, any]) -> Optional[str]:
    """Format a validation result dict into human-readable output lines.

    Args:
        result: Dict returned by ``NFLDataFetcher.validate_data()``, containing
            ``is_valid``, ``row_count``, ``column_count``, and ``issues``.

    Returns:
        A formatted string suitable for printing, or ``None`` if *result*
        is falsy.
    """
    if not result:
        return None

    issues = result.get("issues", [])
    if issues:
        lines = [f"  \u26a0 Validation: {issue}" for issue in issues]
        return "\n".join(lines)

    col_count = result.get("column_count", 0)
    return f"  \u2713 Validation passed: {col_count}/{col_count} columns valid"


class NFLDataAdapter:
    """Thin wrapper around every ``nfl_data_py`` function used in the project.

    Each ``fetch_*`` method:
    1. Validates seasons against ``DATA_TYPE_SEASON_RANGES`` in config.
    2. Calls the underlying ``nfl_data_py`` function inside a try/except.
    3. Returns a ``pd.DataFrame`` (empty on failure).
    """

    def __init__(self) -> None:
        try:
            import nfl_data_py as nfl  # noqa: F401 – verify availability
        except ImportError:
            logger.warning(
                "nfl_data_py is not installed. "
                "All fetch methods will return empty DataFrames."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _import_nfl():
        """Lazily import nfl_data_py so the rest of the project never does."""
        import nfl_data_py as nfl
        return nfl

    def _filter_seasons(
        self, data_type: str, seasons: List[int]
    ) -> List[int]:
        """Return only seasons valid for *data_type*, logging any skipped."""
        valid = [s for s in seasons if validate_season_for_type(data_type, s)]
        skipped = set(seasons) - set(valid)
        if skipped:
            logger.warning(
                "Skipping invalid seasons for %s: %s", data_type, sorted(skipped)
            )
        return valid

    def _safe_call(self, label: str, fn, *args, **kwargs) -> pd.DataFrame:
        """Execute *fn* and return its DataFrame, or empty on error."""
        try:
            df = fn(*args, **kwargs)
            logger.info("%s returned %d rows", label, len(df))
            return df
        except ImportError:
            logger.error("nfl_data_py is not installed – cannot run %s", label)
            return pd.DataFrame()
        except Exception:
            logger.exception("Error in %s", label)
            return pd.DataFrame()

    # ------------------------------------------------------------------
    # stats_player helpers (2025+ data)
    # ------------------------------------------------------------------

    _STATS_PLAYER_URL = (
        "https://github.com/nflverse/nflverse-data/releases/download/"
        "stats_player/stats_player_week_{season}.parquet"
    )

    # Columns to sum when aggregating weekly -> seasonal.
    _SUM_COLS = [
        "attempts", "completions", "passing_yards", "passing_tds",
        "interceptions", "sacks", "sack_yards",
        "sack_fumbles", "sack_fumbles_lost",
        "passing_air_yards", "passing_yards_after_catch",
        "passing_first_downs", "passing_epa", "passing_2pt_conversions",
        "carries", "rushing_yards", "rushing_tds",
        "rushing_fumbles", "rushing_fumbles_lost",
        "rushing_first_downs", "rushing_epa", "rushing_2pt_conversions",
        "receptions", "targets", "receiving_yards", "receiving_tds",
        "receiving_fumbles", "receiving_fumbles_lost",
        "receiving_air_yards", "receiving_yards_after_catch",
        "receiving_first_downs", "receiving_epa", "receiving_2pt_conversions",
        "special_teams_tds", "fantasy_points", "fantasy_points_ppr",
    ]

    def _fetch_stats_player(self, season: int) -> pd.DataFrame:
        """Download player stats from nflverse ``stats_player`` release tag.

        Args:
            season: NFL season year (must be >= STATS_PLAYER_MIN_SEASON).

        Returns:
            DataFrame with columns renamed via STATS_PLAYER_COLUMN_MAP,
            or empty DataFrame on failure.
        """
        url = self._STATS_PLAYER_URL.format(season=season)
        headers: Dict[str, str] = {}
        token = os.getenv("GITHUB_TOKEN") or os.getenv(
            "GITHUB_PERSONAL_ACCESS_TOKEN"
        )
        if token:
            headers["Authorization"] = f"token {token}"
        else:
            logger.warning(
                "No GITHUB_TOKEN found. Using unauthenticated GitHub API "
                "(60 req/hr limit)."
            )

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            df = pd.read_parquet(io.BytesIO(data))
            logger.info(
                "stats_player %d: %d rows, %d columns",
                season, len(df), len(df.columns),
            )

            # Apply column mapping for backward compatibility
            mapped = df.rename(columns=STATS_PLAYER_COLUMN_MAP)

            # Log schema diff
            mapped_count = sum(
                1 for c in STATS_PLAYER_COLUMN_MAP if c in df.columns
            )
            logger.info(
                "stats_player %d schema: %d columns mapped, %d total",
                season, mapped_count, len(mapped.columns),
            )
            return mapped
        except Exception:
            logger.exception(
                "Failed to download stats_player for season %d", season
            )
            return pd.DataFrame()

    def _aggregate_seasonal_from_weekly(
        self, weekly_df: pd.DataFrame
    ) -> pd.DataFrame:
        """Aggregate weekly player stats into a seasonal summary.

        Filters to regular season, groups by player, sums counting stats,
        and recalculates team-share columns (tgt_sh, ay_sh, etc.).

        Args:
            weekly_df: Weekly DataFrame with mapped (old-schema) column names.

        Returns:
            Seasonal DataFrame with ``games``, ``season_type``, and share columns.
        """
        if weekly_df.empty:
            return pd.DataFrame()

        # Filter to regular season only
        reg = weekly_df[weekly_df["season_type"] == "REG"].copy()
        if reg.empty:
            return pd.DataFrame()

        group_cols = [
            "player_id", "player_name", "player_display_name",
            "position", "position_group", "headshot_url", "season",
        ]
        # Keep only group cols that exist in the DataFrame
        group_cols = [c for c in group_cols if c in reg.columns]

        # Sum columns -- filter to those present
        sum_cols = [c for c in self._SUM_COLS if c in reg.columns]

        # Build aggregation dict
        agg_dict: Dict[str, any] = {}
        for col in sum_cols:
            agg_dict[col] = "sum"
        agg_dict["week"] = "nunique"
        agg_dict["recent_team"] = "last"

        # Weighted average for dakota (weight by attempts)
        if "dakota" in reg.columns and "attempts" in reg.columns:
            # Pre-compute weighted dakota
            reg["_dakota_weighted"] = (
                reg["dakota"].fillna(0) * reg["attempts"].fillna(0)
            )
            agg_dict["_dakota_weighted"] = "sum"

        seasonal = reg.groupby(group_cols, as_index=False).agg(agg_dict)

        # Rename week count -> games
        seasonal = seasonal.rename(columns={"week": "games"})

        # Compute weighted average dakota
        if "_dakota_weighted" in seasonal.columns:
            mask = seasonal["attempts"] > 0
            seasonal.loc[mask, "dakota"] = (
                seasonal.loc[mask, "_dakota_weighted"]
                / seasonal.loc[mask, "attempts"]
            )
            seasonal.loc[~mask, "dakota"] = None
            seasonal = seasonal.drop(columns=["_dakota_weighted"])

        # Add season_type
        seasonal["season_type"] = "REG"

        # ----- Recalculate team-share columns -----
        # Compute team totals for share denominators
        team_totals = reg.groupby(
            ["season", "recent_team"], as_index=False
        ).agg(
            team_targets=("targets", "sum"),
            team_receiving_air_yards=("receiving_air_yards", "sum"),
            team_receiving_yards=("receiving_yards", "sum"),
            team_receiving_yards_after_catch=("receiving_yards_after_catch", "sum"),
            team_receptions=("receptions", "sum"),
            team_receiving_first_downs=("receiving_first_downs", "sum"),
            team_receiving_tds=("receiving_tds", "sum"),
        )

        seasonal = seasonal.merge(
            team_totals, on=["season", "recent_team"], how="left"
        )

        def _safe_div(num, denom):
            """Element-wise division, returning 0.0 where denom is 0."""
            return num.where(denom > 0, 0.0) / denom.where(denom > 0, 1.0)

        # tgt_sh: target share
        seasonal["tgt_sh"] = _safe_div(
            seasonal["targets"], seasonal["team_targets"]
        )
        # ay_sh: air yards share
        seasonal["ay_sh"] = _safe_div(
            seasonal["receiving_air_yards"],
            seasonal["team_receiving_air_yards"],
        )
        # yac_sh: yards after catch share
        seasonal["yac_sh"] = _safe_div(
            seasonal["receiving_yards_after_catch"],
            seasonal["team_receiving_yards_after_catch"],
        )
        # ry_sh: receiving yards share
        seasonal["ry_sh"] = _safe_div(
            seasonal["receiving_yards"], seasonal["team_receiving_yards"]
        )
        # wopr_x: 1.5*tgt_sh + 0.7*ay_sh (Weighted Opportunity Rating)
        seasonal["wopr_x"] = 1.5 * seasonal["tgt_sh"] + 0.7 * seasonal["ay_sh"]
        # wopr_y: similar weight variant
        seasonal["wopr_y"] = seasonal["tgt_sh"] + seasonal["ay_sh"]
        # dom: dominance = receiving yards share (alias)
        seasonal["dom"] = seasonal["ry_sh"]
        # w8dom: reception-weighted dominance
        seasonal["w8dom"] = _safe_div(
            seasonal["receptions"], seasonal["team_receptions"]
        ) * seasonal["ry_sh"]
        # ppr_sh: PPR points share (use fantasy_points_ppr / team total)
        if "fantasy_points_ppr" in seasonal.columns:
            team_ppr = reg.groupby(
                ["season", "recent_team"], as_index=False
            ).agg(team_ppr=("fantasy_points_ppr", "sum"))
            seasonal = seasonal.merge(
                team_ppr, on=["season", "recent_team"], how="left"
            )
            seasonal["ppr_sh"] = _safe_div(
                seasonal["fantasy_points_ppr"], seasonal["team_ppr"]
            )
            seasonal = seasonal.drop(columns=["team_ppr"], errors="ignore")
        else:
            seasonal["ppr_sh"] = 0.0

        # rfd_sh: receiving first down share
        seasonal["rfd_sh"] = _safe_div(
            seasonal["receiving_first_downs"],
            seasonal["team_receiving_first_downs"],
        )
        # rtd_sh: receiving TD share
        seasonal["rtd_sh"] = _safe_div(
            seasonal["receiving_tds"], seasonal["team_receiving_tds"]
        )
        # rtdfd_sh: combined receiving TD + first down share
        team_rtdfd = (
            seasonal["team_receiving_tds"]
            + seasonal["team_receiving_first_downs"]
        )
        player_rtdfd = (
            seasonal["receiving_tds"] + seasonal["receiving_first_downs"]
        )
        seasonal["rtdfd_sh"] = _safe_div(player_rtdfd, team_rtdfd)

        # yptmpa: yards per team pass attempt (receiving yards / team attempts)
        team_att = reg.groupby(
            ["season", "recent_team"], as_index=False
        ).agg(team_attempts=("attempts", "sum"))
        seasonal = seasonal.merge(
            team_att, on=["season", "recent_team"], how="left"
        )
        seasonal["yptmpa"] = _safe_div(
            seasonal["receiving_yards"], seasonal["team_attempts"]
        )

        # Drop intermediate team total columns
        team_cols = [
            c for c in seasonal.columns if c.startswith("team_")
        ]
        seasonal = seasonal.drop(columns=team_cols, errors="ignore")

        return seasonal

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_data(self, df: pd.DataFrame, data_type: str) -> Dict[str, any]:
        """Validate a DataFrame against schema rules for *data_type*.

        Delegates to ``NFLDataFetcher.validate_data()`` which checks required
        columns, null percentages, and type-specific rules.

        Args:
            df: DataFrame to validate.
            data_type: Bronze data type key (e.g. ``'schedules'``, ``'pbp'``).

        Returns:
            Dict with ``is_valid``, ``row_count``, ``column_count``, and
            ``issues`` (list of warning strings).
        """
        from src.nfl_data_integration import NFLDataFetcher

        fetcher = NFLDataFetcher()
        return fetcher.validate_data(df, data_type)

    # ------------------------------------------------------------------
    # Fetch methods (one per data type)
    # ------------------------------------------------------------------

    def fetch_schedules(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch NFL schedules.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of schedule data.
        """
        seasons = self._filter_seasons("schedules", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call("fetch_schedules", nfl.import_schedules, seasons)

    def fetch_weekly_data(
        self, seasons: List[int], columns: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Fetch weekly player stats.

        For seasons < STATS_PLAYER_MIN_SEASON, uses ``nfl.import_weekly_data``.
        For seasons >= STATS_PLAYER_MIN_SEASON, downloads directly from the
        nflverse ``stats_player`` release tag.

        Args:
            seasons: List of season years.
            columns: Optional list of columns to select.

        Returns:
            DataFrame of weekly player data.
        """
        seasons = self._filter_seasons("player_weekly", seasons)
        if not seasons:
            return pd.DataFrame()

        old_seasons = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new_seasons = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]

        frames: List[pd.DataFrame] = []

        if old_seasons:
            nfl = self._import_nfl()
            df = self._safe_call(
                "fetch_weekly_data", nfl.import_weekly_data, old_seasons, columns
            )
            if not df.empty:
                frames.append(df)

        for s in new_seasons:
            df = self._fetch_stats_player(s)
            if not df.empty:
                if columns:
                    available = [c for c in columns if c in df.columns]
                    df = df[available]
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_seasonal_data(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch seasonal player stats.

        For seasons < STATS_PLAYER_MIN_SEASON, uses ``nfl.import_seasonal_data``.
        For seasons >= STATS_PLAYER_MIN_SEASON, downloads weekly data from the
        ``stats_player`` tag and aggregates it into a seasonal summary.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of seasonal player data.
        """
        seasons = self._filter_seasons("player_seasonal", seasons)
        if not seasons:
            return pd.DataFrame()

        old_seasons = [s for s in seasons if s < STATS_PLAYER_MIN_SEASON]
        new_seasons = [s for s in seasons if s >= STATS_PLAYER_MIN_SEASON]

        frames: List[pd.DataFrame] = []

        if old_seasons:
            nfl = self._import_nfl()
            df = self._safe_call(
                "fetch_seasonal_data", nfl.import_seasonal_data, old_seasons
            )
            if not df.empty:
                frames.append(df)

        for s in new_seasons:
            weekly = self._fetch_stats_player(s)
            if not weekly.empty:
                seasonal = self._aggregate_seasonal_from_weekly(weekly)
                if not seasonal.empty:
                    frames.append(seasonal)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_snap_counts(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch snap count data for one or more seasons.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of snap counts (all weeks included).
        """
        seasons = self._filter_seasons("snap_counts", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_snap_counts", nfl.import_snap_counts, seasons
        )

    def fetch_injuries(
        self, seasons: List[int], weeks: Optional[List[int]] = None
    ) -> pd.DataFrame:
        """Fetch injury report data.

        Args:
            seasons: List of season years.
            weeks: Optional list of weeks (currently unused by nfl-data-py).

        Returns:
            DataFrame of injury data.
        """
        seasons = self._filter_seasons("injuries", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call("fetch_injuries", nfl.import_injuries, seasons)

    def fetch_rosters(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch seasonal rosters (uses import_seasonal_rosters, NOT import_rosters).

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of roster data.
        """
        seasons = self._filter_seasons("rosters", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_rosters", nfl.import_seasonal_rosters, seasons
        )

    def fetch_team_descriptions(self) -> pd.DataFrame:
        """Fetch team descriptions/metadata.

        Returns:
            DataFrame of team info.
        """
        nfl = self._import_nfl()
        return self._safe_call("fetch_team_descriptions", nfl.import_team_desc)

    def fetch_pbp(
        self,
        seasons: List[int],
        columns: Optional[List[str]] = None,
        downcast: bool = True,
        include_participation: bool = False,
    ) -> pd.DataFrame:
        """Fetch play-by-play data.

        Args:
            seasons: List of season years.
            columns: Optional column filter.
            downcast: Whether to downcast numeric types for memory savings.
            include_participation: Whether to merge participation data.
                Defaults to False to avoid column merge issues with
                curated column lists.

        Returns:
            DataFrame of play-by-play data.
        """
        seasons = self._filter_seasons("pbp", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_pbp",
            nfl.import_pbp_data,
            seasons,
            columns=columns,
            downcast=downcast,
            include_participation=include_participation,
        )

    def fetch_ngs(
        self, seasons: List[int], stat_type: str
    ) -> pd.DataFrame:
        """Fetch Next Gen Stats data.

        Args:
            seasons: List of season years.
            stat_type: One of 'passing', 'rushing', 'receiving'.

        Returns:
            DataFrame of NGS data.
        """
        seasons = self._filter_seasons("ngs", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_ngs", nfl.import_ngs_data, stat_type=stat_type, years=seasons
        )

    def fetch_pfr_weekly(
        self, seasons: List[int], s_type: str
    ) -> pd.DataFrame:
        """Fetch Pro Football Reference weekly data.

        Args:
            seasons: List of season years.
            s_type: Stat type ('pass', 'rush', 'rec', 'def').

        Returns:
            DataFrame of PFR weekly data.
        """
        seasons = self._filter_seasons("pfr_weekly", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_pfr_weekly",
            nfl.import_weekly_pfr,
            s_type=s_type,
            years=seasons,
        )

    def fetch_pfr_seasonal(
        self, seasons: List[int], s_type: str
    ) -> pd.DataFrame:
        """Fetch Pro Football Reference seasonal data.

        Args:
            seasons: List of season years.
            s_type: Stat type ('pass', 'rush', 'rec', 'def').

        Returns:
            DataFrame of PFR seasonal data.
        """
        seasons = self._filter_seasons("pfr_seasonal", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_pfr_seasonal",
            nfl.import_seasonal_pfr,
            s_type=s_type,
            years=seasons,
        )

    def fetch_qbr(
        self, seasons: List[int], frequency: str = "weekly"
    ) -> pd.DataFrame:
        """Fetch ESPN QBR data.

        Args:
            seasons: List of season years.
            frequency: 'weekly' or 'season'.

        Returns:
            DataFrame of QBR data.
        """
        seasons = self._filter_seasons("qbr", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_qbr",
            nfl.import_qbr,
            years=seasons,
            frequency=frequency,
        )

    def fetch_depth_charts(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch team depth charts.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of depth chart data.
        """
        seasons = self._filter_seasons("depth_charts", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_depth_charts", nfl.import_depth_charts, seasons
        )

    def fetch_draft_picks(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch NFL draft pick data.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of draft picks.
        """
        seasons = self._filter_seasons("draft_picks", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_draft_picks", nfl.import_draft_picks, seasons
        )

    def fetch_combine(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch NFL combine results.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of combine data.
        """
        seasons = self._filter_seasons("combine", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_combine", nfl.import_combine_data, seasons
        )

    def fetch_officials(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch officials/referee crew data for the given seasons.

        Returns game-level official assignments with columns:
        game_id, official_name, official_position, official_id, season.

        Note: Raw nfl-data-py columns are renamed for clarity:
        name -> official_name, off_pos -> official_position.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of officials data.
        """
        seasons = self._filter_seasons("officials", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        df = self._safe_call(
            "fetch_officials", nfl.import_officials, seasons
        )
        if not df.empty:
            df = df.rename(columns={
                "name": "official_name",
                "off_pos": "official_position",
            })
        return df
