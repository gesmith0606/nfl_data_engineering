"""High-wind bias-correction lever for QB/WR/TE projections (opt-in).

Mission: `.planning/WEATHER_DATA_2026_08_16.md`'s narrow-lever recommendation --
Vegas-net residual bias for pass-catchers flips from -0.503 (low wind) to
+0.409 (high wind, >=15mph) in the 2022-2024 backtest (t=3.17, p=0.0016).
This module applies a small multiplicative shrink to QB/WR/TE projections in
games with ``wind_speed_mph >= 15`` -- RB, domes, and low-wind games are
never touched (see :func:`apply_wind_shrink`'s byte-identical guarantee).

Fit + gate (full evidence: `.planning/WIND_LEVER_2026_08_16.md`):

- :data:`HIGH_WIND_SHRINK` was fit on 2022-2023 ONLY (n=342 QB/WR/TE
  high-wind rows): ``shrink = mean(error) / mean(projected_points)`` in that
  bucket, i.e. the multiplicative discount that zeros the bucket's mean bias.
- Held out on 2024 (n=108): bias -81% (0.364 -> -0.069) -- replicates.
- Held out on sealed-2025 (n=188): bias flips sign (-0.617 -> -0.935, worse)
  -- does NOT replicate. Combined 2024+2025 |bias| INCREASES ~139%, failing
  the pre-registered >=50% reduction gate.
- **Verdict: HOLD.** Kept opt-in, NOT recommended default-on. The high-wind
  bias direction found in 2022-2023 is not stable across held-out seasons --
  same failure shape as the QB_STARTER_FLOOR / RB_TAIL_CALIBRATION HOLDs.

Mirrors the ``rb_tail_calibration.py`` / ``qb_starter_floor.py`` pattern:
opt-in via a CLI flag, additive provenance flag column, never touches
non-eligible rows.
"""

import logging
from datetime import datetime
from typing import Optional, Set, Tuple

import pandas as pd
import pytz
import requests

from weather_features import (
    HIGH_WIND_THRESHOLD_MPH,
    compute_weather_features,
)

logger = logging.getLogger(__name__)

#: Positions the lever applies to -- pass-catchers, where the wind/bias
#: relationship was found and is theoretically sensible (RB is untouched).
PASS_CATCHING_POSITIONS = {"QB", "WR", "TE"}

#: Fitted multiplicative shrink -- see module docstring for the fit recipe
#: and .planning/WIND_LEVER_2026_08_16.md for the full numbers. Held-out
#: gate result is HOLD; this constant exists for callers that pass
#: --wind-adjust explicitly (opt-in), not as a default-on recommendation.
HIGH_WIND_SHRINK = 0.0539

#: Open-Meteo forecast endpoint -- same no-key pattern as the historical
#: archive used by scripts/bronze_weather_ingestion.py, different host.
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DOME_ROOFS = {"dome", "closed"}


def _kickoff_utc_hour(gameday: str, gametime: str) -> str:
    """nflverse gameday+gametime (America/New_York broadcast-slot convention) -> UTC hour key.

    Mirrors ``scripts/bronze_weather_ingestion._game_utc_hour`` exactly;
    duplicated (not imported) so src/ doesn't depend on scripts/ -- the
    dependency direction in this repo runs the other way.
    """
    dt = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M")
    eastern = pytz.timezone("America/New_York")
    localized = eastern.localize(dt)
    utc_dt = localized.astimezone(pytz.utc)
    if utc_dt.minute >= 30:
        utc_dt = utc_dt.replace(minute=0) + pd.Timedelta(hours=1)
    else:
        utc_dt = utc_dt.replace(minute=0)
    return utc_dt.strftime("%Y-%m-%dT%H:00")


def fetch_forecast_high_wind_teams(
    schedules_df: pd.DataFrame,
    season: int,
    week: int,
    threshold: float = HIGH_WIND_THRESHOLD_MPH,
) -> Tuple[Set[str], int, int]:
    """Forecast-wind fallback for weeks not yet in committed Bronze weather.

    Current-season weeks have no historical archive row yet -- the weekly
    production path needs the Open-Meteo FORECAST API instead. Verified
    2026-08-16: same no-key pattern as the archive API, just a different
    host/param shape (``forecast_days`` instead of a date range).

    FAIL-OPEN per venue: forecast-at-projection-time is legitimately
    pre-game info, but if a request fails or the kickoff hour falls outside
    the forecast horizon, that game is simply skipped (no adjustment) --
    never defaulted to high-wind. A failure for one venue does not block
    others.

    Args:
        schedules_df: Bronze schedules rows (needs game_id, season, week,
            stadium_id, roof, gameday, gametime, home_team, away_team).
        season: NFL season.
        week: Target week.
        threshold: Wind speed (mph) at/above which a game is high-wind.

    Returns:
        ``(high_wind_teams, n_covered, n_eligible)`` -- ``n_covered`` /
        ``n_eligible`` is the GATE COVERAGE line callers should log.
    """
    from config import STADIUM_ID_COORDS

    required = {"season", "week", "roof", "stadium_id", "gameday", "gametime", "home_team", "away_team"}
    if schedules_df is None or schedules_df.empty or not required.issubset(schedules_df.columns):
        return set(), 0, 0

    games = schedules_df[
        (schedules_df["season"] == season)
        & (schedules_df["week"] == week)
        & (~schedules_df["roof"].isin(DOME_ROOFS))
    ]
    high_wind_teams: Set[str] = set()
    n_covered = 0
    for _, g in games.iterrows():
        coords = STADIUM_ID_COORDS.get(g.get("stadium_id"))
        if coords is None or pd.isna(g.get("gameday")) or pd.isna(g.get("gametime")):
            continue
        lat, lon, _tz = coords
        try:
            hour_key = _kickoff_utc_hour(str(g["gameday"]), str(g["gametime"]))
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": "wind_speed_10m",
                    "wind_speed_unit": "mph",
                    "timezone": "UTC",
                    "forecast_days": 16,
                },
                timeout=30,
            )
            resp.raise_for_status()
            hourly = resp.json().get("hourly", {})
            times = hourly.get("time", [])
            winds = hourly.get("wind_speed_10m", [])
            if hour_key not in times:
                # Kickoff beyond the forecast horizon -- fail-open, skip.
                continue
            wind_mph = winds[times.index(hour_key)]
        except (requests.exceptions.RequestException, ValueError, KeyError) as exc:
            logger.warning(
                "Wind forecast fetch failed for %s (stadium %s): %s -- no adjustment for this game",
                g.get("game_id"), g.get("stadium_id"), exc,
            )
            continue
        n_covered += 1
        if wind_mph is not None and wind_mph >= threshold:
            high_wind_teams.add(g["home_team"])
            high_wind_teams.add(g["away_team"])
    return high_wind_teams, n_covered, len(games)


def compute_high_wind_teams(
    season: int,
    week: int,
    schedules_df: Optional[pd.DataFrame] = None,
) -> Tuple[Set[str], str, int, int]:
    """Resolve this week's high-wind teams: committed Bronze first, forecast fallback.

    Prefers the committed historical archive (``src/weather_features.py``,
    seasons 2016-2025). Falls back to :func:`fetch_forecast_high_wind_teams`
    when the season/week isn't in Bronze yet (current-season weekly runs).
    Fail-open: if neither source has data, returns an empty set with
    ``source="unavailable"`` -- no adjustment applied rather than a guess.

    Returns:
        ``(high_wind_teams, source, n_covered, n_eligible)`` where
        ``source`` is one of ``"bronze"``, ``"forecast"``, ``"unavailable"``.
    """
    try:
        feats = compute_weather_features(seasons=[season])
    except FileNotFoundError:
        feats = pd.DataFrame()
    wk = feats[feats["week"] == week] if not feats.empty else feats
    if not wk.empty:
        high = wk[wk["is_high_wind"]]
        return set(high["team"]), "bronze", len(high), len(wk)

    if schedules_df is not None and not schedules_df.empty:
        teams, n_covered, n_eligible = fetch_forecast_high_wind_teams(schedules_df, season, week)
        return teams, "forecast", n_covered, n_eligible

    return set(), "unavailable", 0, 0


def apply_wind_shrink(
    proj_df: pd.DataFrame,
    high_wind_teams: Set[str],
    shrink: float = HIGH_WIND_SHRINK,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Pure shrink application -- no I/O, no wind lookup.

    Multiplies ``points_col`` by ``(1 - shrink)`` for QB/WR/TE rows whose
    ``recent_team`` is in ``high_wind_teams``. Every other row (wrong
    position, non-wind team, or an empty ``high_wind_teams``) is returned
    byte-identical -- this is the scoping guarantee the gate depends on
    (RB untouched, domes untouched, low-wind untouched).

    Args:
        proj_df: Projections with ``position``, ``recent_team``, ``points_col``.
        high_wind_teams: Team abbreviations flagged high-wind this week.
        shrink: Multiplicative discount (default :data:`HIGH_WIND_SHRINK`).
        points_col: Points column to adjust in place.

    Returns:
        ``proj_df`` with ``points_col`` updated and a new ``wind_adjust_flag``
        provenance column (bool, default False).
    """
    proj = proj_df.copy()
    proj["wind_adjust_flag"] = False
    if (
        proj.empty
        or not high_wind_teams
        or "position" not in proj.columns
        or "recent_team" not in proj.columns
    ):
        return proj

    mask = proj["position"].isin(PASS_CATCHING_POSITIONS) & proj["recent_team"].isin(high_wind_teams)
    if mask.any():
        proj.loc[mask, points_col] = (
            proj.loc[mask, points_col] * (1.0 - shrink)
        ).clip(lower=0).round(2)
        proj.loc[mask, "wind_adjust_flag"] = True
    return proj


def apply_wind_adjust(
    proj_df: pd.DataFrame,
    season: int,
    week: int,
    schedules_df: Optional[pd.DataFrame] = None,
    shrink: float = HIGH_WIND_SHRINK,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Orchestrator: resolve high-wind teams (Bronze or forecast) then shrink.

    See :func:`compute_high_wind_teams` for source resolution and
    :func:`apply_wind_shrink` for the pure application. Logs the GATE
    COVERAGE line when the forecast fallback fires.
    """
    teams, source, n_covered, n_eligible = compute_high_wind_teams(
        season, week, schedules_df=schedules_df
    )
    if source == "forecast":
        logger.info(
            "Wind forecast GATE COVERAGE: %d/%d eligible outdoor games covered "
            "(season=%s week=%s)", n_covered, n_eligible, season, week,
        )
    elif source == "unavailable":
        logger.info(
            "Wind adjust: no historical or forecast wind data for season=%s "
            "week=%s -- skipping (fail-open)", season, week,
        )
    return apply_wind_shrink(proj_df, teams, shrink=shrink, points_col=points_col)
