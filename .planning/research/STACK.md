# Stack Research

**Domain:** NFL Prediction Data Foundation (v1.3 milestone)
**Researched:** 2026-03-15
**Confidence:** HIGH for PBP-derivable features (verified columns exist); MEDIUM for weather enrichment (new dependency)

## Executive Summary

Of the 9 new feature areas in this milestone, 7 require ZERO new dependencies -- they derive entirely from existing Bronze PBP data (370+ columns) and schedules data. Only 2 areas need attention:

1. **Weather enrichment**: The schedules table already has `temp` and `wind` columns, but they have significant NaN gaps (dome games show NaN, not "72F/0mph"). A new dependency (`meteostat`) is recommended ONLY if richer weather data (precipitation, humidity, hourly conditions) is needed beyond what schedules provides.

2. **Officials/referee data**: `nfl.import_officials()` already exists in the installed nfl-data-py 0.3.3 -- it just needs a new Bronze registry entry and adapter method.

Everything else -- special teams, penalties, turnover luck, rest/travel, red zone trips, playoff context, coaching changes -- is derivable from existing PBP columns (which have 370+ fields, though only 103 are currently curated) and schedules data.

## Recommended Stack

### Core Technologies (NO CHANGES)

| Technology | Version | Purpose | v1.3 Role |
|------------|---------|---------|-----------|
| Python | 3.9.7 | Runtime | No change |
| pandas | 1.5.3 | DataFrame processing | All Silver transforms, groupby/agg for new metrics |
| numpy | 1.26.4 | Array math | Haversine distance for travel, conditional logic |
| pyarrow | 21.0.0 | Parquet read/write | Reads Bronze PBP (full column set), writes Silver |
| nfl-data-py | 0.3.3 | NFL data source | `import_officials()` for referee data (already installed) |

### New Dependency (Conditional)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| meteostat | 1.6.8 | Historical weather data via NOAA | ONLY if precipitation/humidity/hourly data needed beyond schedules `temp`/`wind` columns |

**Recommendation: Start WITHOUT meteostat.** The schedules table provides game-level temp, wind, roof, and surface. For dome/indoor games, temp and wind are NaN -- but you can impute "72F, 0 mph" for dome games using the `roof` column. This covers 90% of weather modeling needs. Add meteostat later only if backtesting shows weather features beyond temp/wind improve prediction accuracy.

### Supporting Libraries (Already Installed, New Uses)

| Library | Version | New Purpose | Details |
|---------|---------|-------------|---------|
| scipy | 1.13.1 | Haversine approximation for travel distance | `scipy` is installed but not needed -- numpy trig is sufficient for great-circle distance |
| tqdm | 4.67.1 | Progress bars for officials backfill ingestion | Already used in batch ingestion |

## What's Already Available (Key Discovery)

### PBP Data: 370+ Columns, Only 103 Currently Curated

The nflverse PBP dataset contains ~370 columns. The project's `PBP_COLUMNS` in `config.py` curates 103 of them. The following columns exist in the full PBP but are NOT in `PBP_COLUMNS` -- they need to be added:

**Penalty columns (needed for penalty aggregation):**
- `penalty` -- ALREADY in PBP_COLUMNS (binary)
- `penalty_team` -- team abbreviation for penalized team
- `penalty_player_id`, `penalty_player_name` -- who committed it
- `penalty_yards` -- yardage assessed
- `penalty_type` -- string type (e.g., "Holding", "Pass Interference")

**Special teams columns (needed for ST metrics):**
- `punt_attempt`, `punt_blocked`, `punt_inside_twenty`, `punt_in_endzone`, `punt_out_of_bounds`, `punt_downed`, `punt_fair_catch`
- `kickoff_attempt`, `kickoff_inside_twenty`, `kickoff_in_endzone`, `kickoff_out_of_bounds`, `kickoff_downed`, `kickoff_fair_catch`
- `field_goal_attempt`, `field_goal_result` (made/missed/blocked)
- `extra_point_attempt`, `extra_point_result` (good/failed/blocked)
- `kick_distance` -- numeric yards for kicks, punts, FGs
- `punt_returner_player_id`, `punt_returner_player_name`
- `kickoff_returner_player_id`, `kickoff_returner_player_name`
- `kicker_player_id`, `kicker_player_name`
- `blocked_player_id`, `blocked_player_name`
- `own_kickoff_recovery`, `own_kickoff_recovery_td`
- `return_yards` -- if available; otherwise derive from `yards_gained` on ST plays

**Fumble recovery columns (needed for turnover luck):**
- `fumble`, `fumble_lost` -- ALREADY in PBP_COLUMNS
- `fumble_forced`, `fumble_not_forced`
- `fumble_recovery_1_team`, `fumble_recovery_1_yards`, `fumble_recovery_1_player_id`
- `fumble_recovery_2_team`, `fumble_recovery_2_yards`
- `fumbled_1_team`, `fumbled_1_player_id`

**Drive columns (needed for red zone trip volume):**
- `drive` -- ALREADY in PBP_COLUMNS
- `series`, `series_success`, `series_result` -- ALREADY in PBP_COLUMNS
- (Red zone trips = count of unique drives entering yardline_100 <= 20)

### Schedules Data: Already Has Rest, Coaches, Referee, Weather

The schedules Bronze table (from `import_schedules()`) already contains:

| Column | Purpose | Status |
|--------|---------|--------|
| `away_rest`, `home_rest` | Days rest for each team | Available, integer |
| `away_coach`, `home_coach` | Head coach names per game | Available, string |
| `referee` | Head referee name | Available, string |
| `temp` | Temperature (Fahrenheit) | Available, NaN for domes |
| `wind` | Wind speed (mph) | Available, NaN for domes |
| `roof` | Roof type (outdoors/dome/closed/open) | Available, string |
| `surface` | Playing surface type | Available, string |
| `weekday` | Day of week (for prime time detection) | Available, string |
| `gametime` | Kickoff time (for time zone analysis) | Available, string |
| `stadium`, `stadium_id` | Stadium identification | Available, string |
| `div_game` | Divisional game flag | Available, integer |
| `game_type` | REG/WC/DIV/CON/SB for playoff context | Available, string |

### Officials Data: import_officials() in nfl-data-py

The installed nfl-data-py 0.3.3 has `import_officials()` which returns per-game, per-official rows from the nflverse dataset (2015+). Each row contains:
- `game_id` -- joins to schedules
- Official name, position (Referee, Umpire, etc.), jersey number
- `season` (derived from game_id)

This means referee CREW data (not just the head referee from schedules) is available for deeper analysis.

## Feature-to-Data Source Mapping

| Feature Area | Data Source | New Dependency? | New PBP Columns Needed? |
|--------------|------------|-----------------|------------------------|
| Weather data | Schedules Bronze (`temp`, `wind`, `roof`, `surface`) | NO (or meteostat if richer data needed) | NO |
| Coaching staff | Schedules Bronze (`away_coach`, `home_coach`) | NO | NO |
| Special teams metrics | PBP Bronze (full column set) | NO | YES -- ~20 ST columns |
| Penalty aggregation | PBP Bronze (full column set) | NO | YES -- 5 penalty columns |
| Rest/travel factors | Schedules Bronze (`away_rest`, `home_rest`, `weekday`, `gametime`, `stadium`) | NO | NO |
| Turnover luck | PBP Bronze (full column set) | NO | YES -- ~8 fumble recovery columns |
| Referee tendencies | Schedules Bronze (`referee`) + Officials Bronze (new) | NO (import_officials already in nfl-data-py) | NO |
| Playoff/elimination | Schedules Bronze (`game_type`) + derived standings | NO | NO |
| Red zone trip volume | PBP Bronze (`drive`, `yardline_100`) | NO (columns already in PBP_COLUMNS) | NO |

## Implementation Changes Required

### 1. Expand PBP_COLUMNS in config.py

Add ~35 columns to the curated PBP_COLUMNS list for penalty, special teams, and fumble recovery data. These columns exist in the nflverse PBP dataset but are currently excluded from the 103-column curated list.

```python
# Add to PBP_COLUMNS in config.py:
# Penalty detail (5)
"penalty_team", "penalty_player_id", "penalty_player_name",
"penalty_yards", "penalty_type",
# Special teams - punts (8)
"punt_attempt", "punt_blocked", "punt_inside_twenty",
"punt_in_endzone", "punt_out_of_bounds", "punt_downed",
"punt_fair_catch", "kick_distance",
# Special teams - kickoffs (7)
"kickoff_attempt", "kickoff_inside_twenty", "kickoff_in_endzone",
"kickoff_out_of_bounds", "kickoff_downed", "kickoff_fair_catch",
"own_kickoff_recovery",
# Special teams - FG/XP (4)
"field_goal_attempt", "field_goal_result",
"extra_point_attempt", "extra_point_result",
# Special teams - players (6)
"kicker_player_id", "kicker_player_name",
"punt_returner_player_id", "punt_returner_player_name",
"kickoff_returner_player_id", "kickoff_returner_player_name",
# Fumble recovery detail (5)
"fumble_forced", "fumble_not_forced",
"fumble_recovery_1_team", "fumble_recovery_1_yards",
"fumble_recovery_2_team",
```

This brings PBP_COLUMNS from 103 to ~138 columns. Memory impact is minimal (~2 MB more per season due to added columns being mostly binary/sparse).

### 2. Add Officials to Bronze Registry

Add `officials` as a new Bronze data type in `DATA_TYPE_REGISTRY` and `DATA_TYPE_SEASON_RANGES`:

```python
# In config.py DATA_TYPE_SEASON_RANGES:
"officials": (2015, get_max_season),

# In bronze_ingestion_simple.py DATA_TYPE_REGISTRY:
"officials": {
    "adapter_method": "fetch_officials",
    "bronze_path": "officials/season={season}",
    "requires_week": False,
    "requires_season": True,
},
```

### 3. Add fetch_officials to NFLDataAdapter

A thin wrapper calling `nfl.import_officials(years)` -- follows the exact same pattern as existing adapter methods.

### 4. Stadium Coordinates (for Travel Distance)

The `import_team_desc()` function (already used, data type `teams`) returns team metadata. Stadium lat/lon coordinates are NOT in the nflverse team data. For travel distance calculation, use a static lookup dict of 32 stadium coordinates (hardcoded, since stadiums rarely change). This is standard practice in NFL analytics -- no API needed.

```python
# Static lookup -- add to config.py or a new reference module
STADIUM_COORDS = {
    "ARI": (33.5276, -112.2626),  # State Farm Stadium
    "ATL": (33.7554, -84.4010),   # Mercedes-Benz Stadium
    # ... 30 more teams
}
```

## Installation

### If proceeding without meteostat (recommended initial approach):

```bash
# No changes to requirements.txt
pip install -r requirements.txt
```

### If adding meteostat later for enhanced weather:

```bash
pip install meteostat==1.6.8
```

**meteostat dependencies:** matplotlib (already not installed -- would add ~30 MB if pulled in). Use `pip install meteostat --no-deps` and manually install only `pandas` (already have it). Meteostat itself is lightweight (~50 KB) but matplotlib is a heavy transitive dependency.

**Alternative:** Use meteostat's underlying data source directly via HTTP (NOAA Global Summary of the Day) to avoid the dependency entirely. This is more work but keeps the dependency tree clean.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Schedules temp/wind columns | meteostat API | Only if precipitation/humidity data proves valuable in backtesting |
| Schedules temp/wind columns | Open-Meteo API | Free, no key needed, but requires HTTP calls -- adds complexity vs using existing data |
| Schedules temp/wind columns | Tom Bliss NFL Weather dataset (Kaggle) | Static CSV covering 2000-2020 -- good for historical backfill but stops at 2020 |
| Static stadium coordinate dict | Google Maps API | Overkill; 32 stadiums change once every few years |
| nfl-data-py import_officials | Web scraping nflpenalties.com | Fragile; nflverse data is structured and maintained |
| Deriving ST metrics from PBP | Pro-Football-Reference scraping | Unnecessary; all ST play-level data is in PBP |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| meteostat (initially) | Schedules already has temp/wind/roof; adding a dependency for marginal gain is premature | Use schedules `temp`/`wind` + impute domes |
| nflscraPy | Overlaps heavily with nfl-data-py; repo is less maintained | Existing nfl-data-py 0.3.3 |
| nflreadpy | Python 3.10+ required; would force runtime upgrade | Stay on nfl-data-py 0.3.3 for now |
| requests/beautifulsoup for coaching data | Schedules already has `home_coach`/`away_coach` per game | Use schedules data directly |
| Any standings API | Standings/playoff context can be derived from schedules win/loss data | Compute cumulative W-L from schedules results |
| geopy for distance | Heavyweight dependency for a simple haversine formula | numpy cos/sin/arctan2 (6 lines of code) |

## Stack Patterns by Feature Area

**Weather features (from schedules):**
- Read schedules Bronze, extract `temp`, `wind`, `roof`, `surface`
- Impute dome games: where `roof in ('dome', 'closed')`, set `temp=72, wind=0`
- Create binary features: `is_cold` (temp < 35), `is_windy` (wind > 15), `is_dome` (roof != 'outdoors')
- Join to game_id for per-game weather context

**Coaching staff tracking (from schedules):**
- Extract `home_coach`, `away_coach` per game from schedules
- Detect mid-season coaching changes: where coach name changes between consecutive weeks for same team
- Compute coach tenure: games since coach's first appearance with team
- OC/DC not available in nflverse data -- HC only (document as limitation)

**Special teams metrics (from expanded PBP):**
- Filter PBP to `play_type in ('punt', 'field_goal', 'kickoff', 'extra_point')`
- Aggregate per team-week: FG%, punt distance, punt inside-20 rate, kickoff touchback rate, return yards allowed
- Use `kick_distance` for FG distance buckets, punt average

**Penalty aggregation (from expanded PBP):**
- Filter to `penalty == 1`
- Group by `penalty_team` for committed penalties; group by opposing team for drawn penalties
- Aggregate: penalty count, total penalty yards, penalties per play
- Break down by `penalty_type` for type-specific rates

**Rest and travel factors (from schedules):**
- `away_rest`, `home_rest` already in schedules -- compute `rest_differential = home_rest - away_rest`
- Travel distance: lookup home team stadium coords, away team stadium coords, compute haversine
- Time zone differential: derive from stadium coords (or static timezone lookup)
- Bye week detection: `home_rest >= 10` or missing from schedule for a week
- Short week (Thursday): `weekday == 'Thursday'` and `home_rest < 7`

**Turnover luck / fumble recovery regression (from expanded PBP):**
- Total fumbles: count `fumble == 1` per team (as offense)
- Fumbles lost: count `fumble_lost == 1` per team
- Recovery rate: `fumbles_lost / total_fumbles` -- league average is ~50%
- Deviation from 50%: indicates luck; teams far from 50% tend to regress
- Also compute interception rate from existing `interception` column

**Referee tendencies (from schedules + officials):**
- Schedules `referee` column gives head referee per game
- Officials Bronze gives full crew (7 officials per game, 2015+)
- Join to penalty data: aggregate penalty rates per referee/crew
- Compute referee-specific flags/game, yards/game averages

**Playoff/elimination context (derived from schedules):**
- Compute cumulative W-L record from schedules `result` column per team per season
- Division standings: group by division, rank by wins
- Clinch/elimination: simplified model using games remaining + win differential
- `game_type` column distinguishes REG/WC/DIV/CON/SB directly

**Red zone trip volume (from existing PBP columns):**
- Already have `drive`, `yardline_100` in PBP_COLUMNS
- Count unique drives where any play has `yardline_100 <= 20` per team-week
- This gives trip COUNT (not just efficiency, which already exists in team_analytics.py)

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pandas 1.5.3 | numpy 1.26.4 | No change -- verified in v1.2 |
| nfl-data-py 0.3.3 | import_officials() | Function exists, verified in source code; returns CSV from nflverse GitHub |
| meteostat 1.6.8 | pandas 1.5.3 | Compatible; meteostat returns pandas DataFrames |
| Python 3.9.7 | All packages above | No upgrade needed |

## Sources

- [nflverse PBP Data Dictionary](https://nflreadr.nflverse.com/articles/dictionary_pbp.html) -- full column reference for 370+ PBP columns including penalty, ST, fumble recovery (HIGH confidence)
- [nfl-data-py source code](https://github.com/nflverse/nfl_data_py) -- verified `import_officials()` exists in installed v0.3.3 (HIGH confidence)
- [Meteostat Python library](https://dev.meteostat.net/python) -- NOAA-based historical weather, CC BY 4.0 license (MEDIUM confidence -- not yet tested in project)
- [Tom Bliss NFL Weather Data](https://www.datawithbliss.com/weather-data/) -- historical NFL weather using meteostat, covers 2000-2020 (MEDIUM confidence)
- [nflverse officials data](https://raw.githubusercontent.com/nflverse/nfldata/master/data/officials.csv) -- raw CSV source for import_officials, 2015+ (HIGH confidence)
- Local project inspection (2026-03-15) -- verified schedules columns (temp, wind, roof, coach, referee, rest), PBP_COLUMNS curated list, DATA_TYPE_REGISTRY, NFLDataAdapter patterns (HIGH confidence)
- [NFL Penalty Stats Tracker](https://www.nflpenalties.com/) -- independent verification of referee/penalty data availability (LOW confidence -- used for concept validation only)

---
*Stack research for: NFL Data Engineering v1.3 Prediction Data Foundation*
*Researched: 2026-03-15*
