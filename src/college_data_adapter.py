"""
Adapter for college football data from the CFBD (CollegeFootballData.com) API.

Uses direct HTTP requests to the CFBD REST API (v1) to avoid dependency
conflicts with the ``cfbd`` Python package (which requires pydantic v1).

Requires a free API key from collegefootballdata.com, set as the
``CFBD_API_KEY`` environment variable.

When the key is absent or the API is unreachable, every public method
returns an empty DataFrame so downstream callers degrade gracefully.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.collegefootballdata.com"

# Positions we care about for NFL fantasy purposes
_NFL_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}


def _get_api_key() -> Optional[str]:
    """Return the CFBD API key from the environment, or None."""
    key = os.getenv("CFBD_API_KEY")
    if not key:
        logger.warning(
            "CFBD_API_KEY not set — college data unavailable. "
            "Get a free key at https://collegefootballdata.com/key"
        )
    return key


def _cfbd_get(endpoint: str, params: Dict[str, Any], api_key: str) -> Any:
    """Make a GET request to the CFBD API and return parsed JSON.

    Args:
        endpoint: API path (e.g. "/stats/player/season").
        params: Query parameters.
        api_key: Bearer token for the CFBD API.

    Returns:
        Parsed JSON (list or dict).

    Raises:
        HTTPError, URLError on network failures.
    """
    query_parts = []
    for k, v in params.items():
        if v is not None:
            query_parts.append(f"{k}={v}")
    query_string = "&".join(query_parts)
    url = (
        f"{_BASE_URL}{endpoint}?{query_string}"
        if query_string
        else f"{_BASE_URL}{endpoint}"
    )

    req = Request(url)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")

    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CollegeDataAdapter:
    """Adapter for college football data from the CFBD API.

    All public methods return a ``pd.DataFrame`` (empty when the API is
    unavailable or returns an error).
    """

    def __init__(self) -> None:
        self._api_key = _get_api_key()
        self._available = self._api_key is not None

    @property
    def is_available(self) -> bool:
        """Whether the adapter has a valid API key configured."""
        return self._available

    # ------------------------------------------------------------------
    # Public fetch methods
    # ------------------------------------------------------------------

    def fetch_player_season_stats(
        self,
        season: int,
        position: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch college player seasonal statistics.

        Args:
            season: College football season year (e.g. 2024).
            position: Optional position filter (QB, RB, WR, TE).

        Returns:
            DataFrame with columns: player_name, college_team, conference,
            position, season, category, stat_type, stat_value.
            Empty DataFrame if API unavailable.
        """
        if not self._available:
            return pd.DataFrame()

        try:
            params: Dict[str, Any] = {"year": season, "seasonType": "regular"}
            data = _cfbd_get("/stats/player/season", params, self._api_key)

            all_rows: List[Dict[str, Any]] = []
            for entry in data:
                player_name = entry.get("player")
                college_team = entry.get("team")
                conference = entry.get("conference")
                category = entry.get("category")
                stat_type = entry.get("statType")
                stat_value = entry.get("stat")

                all_rows.append(
                    {
                        "player_name": player_name,
                        "college_team": college_team,
                        "conference": conference,
                        "position": position or "UNKNOWN",
                        "season": season,
                        "category": category,
                        "stat_type": stat_type,
                        "stat_value": stat_value,
                    }
                )

            if not all_rows:
                logger.info("No player season stats returned for %d", season)
                return pd.DataFrame()

            df = pd.DataFrame(all_rows)
            logger.info("Fetched %d college stat rows for season %d", len(df), season)
            return df

        except (HTTPError, URLError) as e:
            logger.error("CFBD player stats fetch failed for %d: %s", season, e)
            return pd.DataFrame()
        except Exception as e:
            logger.error("CFBD player stats fetch failed for %d: %s", season, e)
            return pd.DataFrame()

    def fetch_player_usage(self, season: int) -> pd.DataFrame:
        """Fetch player usage/participation rates.

        Args:
            season: College football season year.

        Returns:
            DataFrame with player usage metrics (overall, pass, rush,
            first-down usage rates). Empty if API unavailable.
        """
        if not self._available:
            return pd.DataFrame()

        try:
            params: Dict[str, Any] = {"year": season}
            data = _cfbd_get("/player/usage", params, self._api_key)

            rows: List[Dict[str, Any]] = []
            for item in data:
                usage = item.get("usage", {}) or {}
                rows.append(
                    {
                        "player_name": item.get("name"),
                        "player_id_cfbd": item.get("id"),
                        "college_team": item.get("team"),
                        "conference": item.get("conference"),
                        "position": item.get("position"),
                        "season": season,
                        "overall_usage": usage.get("overall"),
                        "pass_usage": usage.get("pass"),
                        "rush_usage": usage.get("rush"),
                        "first_down_usage": usage.get("firstDown"),
                    }
                )

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            # Filter to NFL-relevant positions
            df = df[df["position"].isin(_NFL_FANTASY_POSITIONS)].copy()
            logger.info("Fetched %d player usage rows for %d", len(df), season)
            return df

        except (HTTPError, URLError) as e:
            logger.error("CFBD player usage fetch failed for %d: %s", season, e)
            return pd.DataFrame()
        except Exception as e:
            logger.error("CFBD player usage fetch failed for %d: %s", season, e)
            return pd.DataFrame()

    def fetch_team_info(self, season: Optional[int] = None) -> pd.DataFrame:
        """Fetch college team info with conference affiliations.

        Args:
            season: Optional season for historical conference realignment.

        Returns:
            DataFrame with school, conference, abbreviation, mascot.
        """
        if not self._available:
            return pd.DataFrame()

        try:
            params: Dict[str, Any] = {}
            if season:
                params["year"] = season
            data = _cfbd_get("/teams", params, self._api_key)

            rows: List[Dict[str, Any]] = []
            for team in data:
                rows.append(
                    {
                        "school": team.get("school"),
                        "conference": team.get("conference"),
                        "abbreviation": team.get("abbreviation"),
                        "mascot": team.get("mascot"),
                        "classification": team.get("classification"),
                    }
                )

            df = pd.DataFrame(rows)
            logger.info("Fetched %d college teams", len(df))
            return df

        except (HTTPError, URLError) as e:
            logger.error("CFBD team info fetch failed: %s", e)
            return pd.DataFrame()
        except Exception as e:
            logger.error("CFBD team info fetch failed: %s", e)
            return pd.DataFrame()

    def fetch_draft_picks(self, nfl_year: int) -> pd.DataFrame:
        """Fetch NFL draft picks with college information from CFBD.

        Args:
            nfl_year: NFL draft year (e.g. 2024 for the April 2024 draft).

        Returns:
            DataFrame with pick, round, nfl_team, player_name, college_team,
            conference, position, height, weight.
        """
        if not self._available:
            return pd.DataFrame()

        try:
            params: Dict[str, Any] = {"year": nfl_year}
            data = _cfbd_get("/draft/picks", params, self._api_key)

            rows: List[Dict[str, Any]] = []
            for pick in data:
                pos_obj = pick.get("position") or {}
                rows.append(
                    {
                        "nfl_year": nfl_year,
                        "round": pick.get("round"),
                        "pick": pick.get("overall"),
                        "nfl_team": pick.get("nflTeam"),
                        "player_name": pick.get("name"),
                        "college_team": pick.get("collegeTeam"),
                        "conference": pick.get("collegeConference"),
                        "position": (
                            pos_obj.get("abbreviation")
                            if isinstance(pos_obj, dict)
                            else None
                        ),
                        "height": pick.get("height"),
                        "weight": pick.get("weight"),
                    }
                )

            df = pd.DataFrame(rows)
            logger.info("Fetched %d draft picks for NFL %d draft", len(df), nfl_year)
            return df

        except (HTTPError, URLError) as e:
            logger.error("CFBD draft picks fetch failed for %d: %s", nfl_year, e)
            return pd.DataFrame()
        except Exception as e:
            logger.error("CFBD draft picks fetch failed for %d: %s", nfl_year, e)
            return pd.DataFrame()


def pivot_player_stats(raw_stats_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long-form CFBD stats into a wide player-level DataFrame.

    The raw CFBD output has one row per (player, category, stat_type).
    This pivots to one row per player with columns for each relevant stat.

    Args:
        raw_stats_df: Long-form DataFrame from ``fetch_player_season_stats``.

    Returns:
        Wide DataFrame with columns: player_name, college_team, conference,
        position, season, passing_yards, passing_tds, rushing_yards,
        rushing_tds, receptions, receiving_yards, receiving_tds, games.
    """
    if raw_stats_df.empty:
        return pd.DataFrame()

    # Build (category, stat_type) -> output column mapping
    stat_mapping = {
        ("passing", "YDS"): "passing_yards",
        ("passing", "TD"): "passing_tds",
        ("passing", "INT"): "passing_ints",
        ("passing", "COMPLETIONS"): "completions",
        ("passing", "ATT"): "pass_attempts",
        ("rushing", "YDS"): "rushing_yards",
        ("rushing", "TD"): "rushing_tds",
        ("rushing", "CAR"): "carries",
        ("receiving", "YDS"): "receiving_yards",
        ("receiving", "TD"): "receiving_tds",
        ("receiving", "REC"): "receptions",
        ("receiving", "LONG"): "receiving_long",
    }

    df = raw_stats_df.copy()

    # Normalise stat_value to float
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")

    # Create a lookup key
    df["_key"] = list(zip(df["category"].str.lower(), df["stat_type"].str.upper()))

    # Map to output column
    df["_out_col"] = df["_key"].map(stat_mapping)
    df = df.dropna(subset=["_out_col"])

    if df.empty:
        return pd.DataFrame()

    # Pivot: one row per player-season, columns = output stat names
    group_cols = ["player_name", "college_team", "conference", "position", "season"]
    available_groups = [c for c in group_cols if c in df.columns]

    pivoted = df.pivot_table(
        index=available_groups,
        columns="_out_col",
        values="stat_value",
        aggfunc="sum",
    ).reset_index()

    # Flatten column index
    pivoted.columns.name = None

    return pivoted
