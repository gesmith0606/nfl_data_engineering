"""Bronze weather ingestion -- Open-Meteo historical archive -> per-game weather.

Fills a gap in nflverse schedules: temp/wind exist but have real holes (2022
season is 46% null, 2023 is 21% null for outdoor games) and nflverse never
carries precipitation or wind gusts at all. This script backfills/enriches
game-time-hour weather for every 2016-2025 game using the FREE Open-Meteo
historical archive API (no key required).

One API call per unique outdoor/retractable-roof venue (~36 stadium_ids),
covering the full 2016-01-01..2025-12-31 range in a single request per venue
-- far fewer calls than a per-season chunk, and polite (1s sleep between
calls, raw JSON cached to disk so reruns are free).

Dome/closed-roof games skip the API entirely (weather is not a factor
indoors) and get zeroed precip/gust with is_dome=True, mirroring the
existing convention in src/game_context.py (temp=72, wind=0 for domes).

Output: data/bronze/weather/season=YYYY/weather_<timestamp>.parquet
One row per (game_id, season, week, stadium_id) -- game-level, not yet
unpivoted to per-team. See src/weather_features.py for the per-team
(season, week, team) feature table built on top of this.

Usage:
    python scripts/bronze_weather_ingestion.py
    python scripts/bronze_weather_ingestion.py --seasons 2022 2023   # refresh subset
"""

import argparse
import glob
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from config import STADIUM_ID_COORDS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
BRONZE_SCHEDULES_GLOB = "data/bronze/schedules/season=*/**/*.parquet"
RAW_CACHE_DIR = Path("data/bronze/weather/_raw_cache")
OUTPUT_DIR = Path("data/bronze/weather")
DOME_ROOFS = {"dome", "closed"}
DEFAULT_START = "2016-01-01"
DEFAULT_END = "2025-12-31"
REQUEST_SLEEP_SEC = 1.0


def load_schedules(seasons=None) -> pd.DataFrame:
    """Load committed Bronze schedules (all seasons 2016-2025 by default)."""
    files = glob.glob(BRONZE_SCHEDULES_GLOB, recursive=True)
    if not files:
        raise FileNotFoundError(f"No schedules parquet found under {BRONZE_SCHEDULES_GLOB}")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df[(df["season"] >= 2016) & (df["season"] <= 2025)]
    if seasons:
        df = df[df["season"].isin(seasons)]
    return df.reset_index(drop=True)


def _fetch_range(lat: float, lon: float, start: str, end: str) -> dict:
    """Single Open-Meteo call for one venue/date-range, with one retry."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "UTC",
    }
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=120)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            logger.warning("Open-Meteo request failed (attempt %d) for %s..%s: %s", attempt + 1, start, end, exc)
            time.sleep(3)
    raise last_exc


def fetch_venue_weather(stadium_id: str, lat: float, lon: float) -> dict:
    """Fetch (or load cached) hourly weather for one venue, full date range.

    Chunked per-season (10 requests/venue) rather than one 10-year request --
    the full-range single call reliably times out server-side.

    Returns a dict mapping ISO-hour string ('YYYY-MM-DDTHH:00') -> dict of
    temperature_2m (F), precipitation (mm), wind_speed_10m (mph),
    wind_gusts_10m (mph). All hours are UTC.
    """
    cache_path = RAW_CACHE_DIR / f"{stadium_id}.json"
    if cache_path.exists():
        merged = json.loads(cache_path.read_text())
        logger.info("Cache hit: %s", stadium_id)
    else:
        merged = {"time": [], "temperature_2m": [], "precipitation": [], "wind_speed_10m": [], "wind_gusts_10m": []}
        start_year = int(DEFAULT_START[:4])
        end_year = int(DEFAULT_END[:4])
        for year in range(start_year, end_year + 1):
            # Season spans Aug (preseason) through Feb of the following
            # calendar year (playoffs) -- including for the final season,
            # since e.g. the 2025 season's playoffs fall in Jan/Feb 2026.
            start = f"{year}-08-01"
            end = f"{year + 1}-02-15"
            raw = _fetch_range(lat, lon, start, end)
            hourly = raw.get("hourly", {})
            for key in merged:
                merged[key].extend(hourly.get(key, []))
            time.sleep(REQUEST_SLEEP_SEC)
        logger.info("Fetched: %s (%d hourly rows across seasons)", stadium_id, len(merged["time"]))
        RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(merged))

    times = merged.get("time", [])
    out = {}
    for i, t in enumerate(times):
        out[t] = {
            "temp_f": merged["temperature_2m"][i],
            "precip_mm": merged["precipitation"][i],
            "wind_mph": merged["wind_speed_10m"][i],
            "gust_mph": merged["wind_gusts_10m"][i],
        }
    return out


def _game_utc_hour(gameday: str, gametime: str) -> str:
    """Convert nflverse gameday+gametime (America/New_York local) to UTC hour key.

    nflverse `gametime` is posted in ET broadcast-slot convention regardless
    of the actual venue's local timezone (verified: Denver 4:05pm ET slot
    games show gametime='16:05', not their 2:05pm MT local kickoff).
    """
    dt = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M")
    eastern = pytz.timezone("America/New_York")
    localized = eastern.localize(dt)
    utc_dt = localized.astimezone(pytz.utc)
    # Round to nearest hour
    if utc_dt.minute >= 30:
        utc_dt = utc_dt.replace(minute=0) + pd.Timedelta(hours=1)
    else:
        utc_dt = utc_dt.replace(minute=0)
    return utc_dt.strftime("%Y-%m-%dT%H:00")


def build_game_weather(schedules: pd.DataFrame) -> pd.DataFrame:
    """Build one weather row per game, joining Open-Meteo hourly to kickoff hour."""
    outdoor_stadium_ids = sorted(
        schedules.loc[~schedules["roof"].isin(DOME_ROOFS), "stadium_id"].dropna().unique()
    )
    logger.info("Fetching weather for %d outdoor/retractable venues", len(outdoor_stadium_ids))

    venue_weather = {}
    missing_coords = []
    for stadium_id in outdoor_stadium_ids:
        coords = STADIUM_ID_COORDS.get(stadium_id)
        if coords is None:
            missing_coords.append(stadium_id)
            continue
        lat, lon, _tz = coords
        venue_weather[stadium_id] = fetch_venue_weather(stadium_id, lat, lon)

    if missing_coords:
        logger.warning("No STADIUM_ID_COORDS entry for: %s (weather skipped for these games)", missing_coords)

    rows = []
    matched, unmatched, domed = 0, 0, 0
    for _, g in schedules.iterrows():
        is_dome = g["roof"] in DOME_ROOFS
        row = {
            "game_id": g["game_id"],
            "season": g["season"],
            "week": g["week"],
            "stadium_id": g["stadium_id"],
            "is_dome": is_dome,
            "temp_f": None,
            "precip_in": 0.0,
            "wind_mph": None,
            "wind_gust_mph": 0.0,
            "weather_hour_utc": None,
            "weather_source": "dome_default" if is_dome else "open_meteo",
        }
        if is_dome:
            domed += 1
            rows.append(row)
            continue

        hourly = venue_weather.get(g["stadium_id"])
        if hourly is None or pd.isna(g.get("gametime")) or pd.isna(g.get("gameday")):
            unmatched += 1
            row["weather_source"] = "unavailable"
            rows.append(row)
            continue

        hour_key = _game_utc_hour(str(g["gameday"]), str(g["gametime"]))
        obs = hourly.get(hour_key)
        if obs is None:
            unmatched += 1
            row["weather_source"] = "unavailable"
            rows.append(row)
            continue

        matched += 1
        row["temp_f"] = obs["temp_f"]
        row["precip_in"] = round(obs["precip_mm"] / 25.4, 4) if obs["precip_mm"] is not None else 0.0
        row["wind_mph"] = obs["wind_mph"]
        row["wind_gust_mph"] = obs["gust_mph"] if obs["gust_mph"] is not None else 0.0
        row["weather_hour_utc"] = hour_key
        rows.append(row)

    logger.info("Matched %d games, %d dome defaults, %d unavailable", matched, domed, unmatched)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Bronze weather ingestion (Open-Meteo)")
    parser.add_argument("--seasons", type=int, nargs="*", default=None, help="Subset of seasons (default: 2016-2025)")
    args = parser.parse_args()

    schedules = load_schedules(args.seasons)
    logger.info("Loaded %d scheduled games across seasons %s", len(schedules), sorted(schedules["season"].unique()))

    weather_df = build_game_weather(schedules)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for season, group in weather_df.groupby("season"):
        season_dir = OUTPUT_DIR / f"season={season}"
        season_dir.mkdir(parents=True, exist_ok=True)
        out_path = season_dir / f"weather_{timestamp}.parquet"
        group.to_parquet(out_path, index=False)
        logger.info("Wrote %s (%d rows)", out_path, len(group))

    total_size = sum(f.stat().st_size for f in OUTPUT_DIR.rglob("*.parquet"))
    logger.info("Total weather bronze size: %.2f MB", total_size / 1e6)


if __name__ == "__main__":
    main()
