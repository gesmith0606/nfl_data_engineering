"""
Adapter module isolating all nfl-data-py import_* calls.

This is the ONLY module in the project that should ``import nfl_data_py``.
All other code fetches NFL data through :class:`NFLDataAdapter`.
"""

import logging
from typing import List, Optional

import pandas as pd

from src.config import validate_season_for_type

logger = logging.getLogger(__name__)


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

        Args:
            seasons: List of season years.
            columns: Optional list of columns to select.

        Returns:
            DataFrame of weekly player data.
        """
        seasons = self._filter_seasons("player_weekly", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_weekly_data", nfl.import_weekly_data, seasons, columns
        )

    def fetch_seasonal_data(self, seasons: List[int]) -> pd.DataFrame:
        """Fetch seasonal player stats.

        Args:
            seasons: List of season years.

        Returns:
            DataFrame of seasonal player data.
        """
        seasons = self._filter_seasons("player_seasonal", seasons)
        if not seasons:
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_seasonal_data", nfl.import_seasonal_data, seasons
        )

    def fetch_snap_counts(self, season: int, week: int) -> pd.DataFrame:
        """Fetch snap count data for a single season/week.

        Args:
            season: Season year.
            week: Week number.

        Returns:
            DataFrame of snap counts.
        """
        if not validate_season_for_type("snap_counts", season):
            logger.warning("Season %d not valid for snap_counts", season)
            return pd.DataFrame()
        nfl = self._import_nfl()
        return self._safe_call(
            "fetch_snap_counts", nfl.import_snap_counts, season, week
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
    ) -> pd.DataFrame:
        """Fetch play-by-play data.

        Args:
            seasons: List of season years.
            columns: Optional column filter.
            downcast: Whether to downcast numeric types for memory savings.

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
