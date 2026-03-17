# Phase 22: Schedule-Derived Context - Research

**Researched:** 2026-03-16
**Domain:** NFL schedules data transformation (weather, rest/travel, coaching)
**Confidence:** HIGH

## Summary

Phase 22 extracts weather, rest/travel, and coaching features from the existing schedules Bronze data (2016-2025) into a new `game_context` Silver module. The core technical challenge is unpivoting home/away game rows into per-team per-week rows, then computing derived features. The schedules Bronze data is well-structured with `temp`, `wind`, `roof`, `surface`, `home_rest`/`away_rest`, `home_coach`/`away_coach` already present -- most work is reshaping and deriving flags.

The key complexity areas are: (1) mapping `stadium_id` codes from nflverse to `STADIUM_COORDINATES` for travel distance, since the codes differ (e.g., `KAN00` vs `KC`, `GNB00` vs `GB`); (2) handling international/neutral-site games for travel distance; (3) timezone offset computation accounting for DST via `pytz`; and (4) coaching tenure tracking across seasons with proper edge case handling.

**Primary recommendation:** Build a `STADIUM_ID_TO_COORDS` mapping dict in `config.py` that maps nflverse `stadium_id` codes to `(lat, lon, timezone)` tuples, covering all 42 unique stadium IDs found in the data. Use Python `math` module for haversine (no external dependency needed). Follow the Phase 21 orchestrator pattern for module structure.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Dome games (`roof` in `['dome', 'closed']`): set temp=72, wind=0; `is_dome=True`
- `is_high_wind`: wind > 15 mph; `is_cold`: temp <= 32F
- Outdoor games with missing temp/wind: leave as NaN; derived flags become False for NaN
- Surface type passed through as-is
- Use existing `away_rest`/`home_rest` from schedules directly -- no recomputation
- Rest days capped at 14; `is_short_rest` <= 6 days; `is_post_bye` >= 13 days
- `rest_advantage` = team_rest - opponent_rest
- Travel distance: haversine miles using `STADIUM_COORDINATES`; home games = 0 miles
- Time zone differential: absolute hours between team home TZ and game venue TZ
- Coaching: unpivot `home_coach`/`away_coach` to `head_coach`; detect mid-season (week-over-week) and off-season (vs prior season final week) changes
- First season of data (2016): `coaching_change=False` for all teams
- `coaching_tenure`: consecutive weeks with same coach; resets on change; Week 1 of new coach = 1
- No interim vs permanent distinction
- Output: single combined parquet per season under `teams/game_context/season=YYYY/`
- New module: `src/game_context.py` with `_unpivot_schedules()` helper
- New script: `scripts/silver_game_context_transformation.py`
- Add `game_context` key to `SILVER_TEAM_S3_KEYS`
- All output joinable on `[team, season, week]`

### Claude's Discretion
- Exact column naming conventions (follow existing off_/def_ patterns where applicable)
- Handling rare edge cases (COVID-rescheduled games)
- Whether to include `is_home` flag in game_context output
- Haversine implementation approach (math module vs scipy)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SCHED-01 | Weather features (temp, wind, roof, surface) from schedules Bronze as Silver columns | Schedules Bronze confirmed to have `temp`, `wind`, `roof`, `surface` columns. ~36% NaN for temp/wind (103/285 in 2024) corresponding to dome/closed roof games. Roof values: `outdoors`, `closed`, `dome`. Surface values: `grass`, `fieldturf`, `a_turf`, `sportturf`, `matrixturf`, `astroturf`, `None`. |
| SCHED-02 | Rest days per team/week with bye timing and short week flag | `home_rest`/`away_rest` pre-computed by nflverse (integer, range 4-14 in 2024). Unpivot to per-team `rest_days`. Capping at 14 already natural in data. |
| SCHED-03 | Travel distance between venues using stadium coordinates | Requires `STADIUM_ID_TO_COORDS` mapping (42 unique stadium_ids across 2016-2025). `STADIUM_COORDINATES` already has 35 entries by team abbreviation. International venues partially covered. Haversine via `math` module. |
| SCHED-04 | Time zone differential for cross-country games | `STADIUM_COORDINATES` includes timezone strings. `pytz` available (verified). Must use game date for DST-aware offset computation. |
| SCHED-05 | Head coach per game with coaching change detection | `home_coach`/`away_coach` strings in schedules. Off-season changes confirmed working (7 changes 2023->2024). No mid-season changes found in 2024 but algorithm must handle them. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | (project standard) | DataFrame operations, unpivot, merge | Already used throughout pipeline |
| numpy | (project standard) | NaN handling, numeric operations | Already used throughout pipeline |
| math | stdlib | Haversine distance calculation | No external dependency needed; `radians`, `sin`, `cos`, `sqrt`, `atan2` |
| pytz | (installed) | Timezone-aware offset computation | Required for DST-correct timezone differentials |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| logging | stdlib | Structured logging | Follow `logger = logging.getLogger(__name__)` pattern from team_analytics |
| argparse | stdlib | CLI argument parsing | Script CLI (--season/--seasons/--no-s3) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| math haversine | scipy.spatial.distance | scipy available but overkill; math module is simpler and has zero import cost |
| pytz | zoneinfo (3.9+) | zoneinfo is stdlib in 3.9+ but pytz is already in the project and more battle-tested |

## Architecture Patterns

### Recommended Project Structure
```
src/
  game_context.py           # New module: _unpivot_schedules(), compute_weather_features(),
                            #   compute_rest_features(), compute_travel_features(),
                            #   compute_coaching_features(), compute_game_context()
scripts/
  silver_game_context_transformation.py  # CLI script following silver_team_transformation.py pattern
tests/
  test_game_context.py      # Unit tests for all compute functions
```

### Pattern 1: Unpivot (Home/Away to Per-Team Rows)
**What:** Convert one row per game into two rows per game (one per team)
**When to use:** Whenever schedules data needs per-team granularity
**Example:**
```python
def _unpivot_schedules(schedules_df: pd.DataFrame) -> pd.DataFrame:
    """Convert home/away game rows to per-team rows.

    Each game produces two rows: one for home team, one for away team.
    Renames home_coach/away_coach -> head_coach, home_rest/away_rest -> rest_days, etc.
    Adds is_home flag.
    """
    home = schedules_df.rename(columns={
        'home_team': 'team', 'away_team': 'opponent',
        'home_coach': 'head_coach', 'away_coach': 'opponent_coach',
        'home_rest': 'rest_days', 'away_rest': 'opponent_rest',
    }).assign(is_home=True)

    away = schedules_df.rename(columns={
        'away_team': 'team', 'home_team': 'opponent',
        'away_coach': 'head_coach', 'home_coach': 'opponent_coach',
        'away_rest': 'rest_days', 'home_rest': 'opponent_rest',
    }).assign(is_home=False)

    cols = ['game_id', 'season', 'week', 'team', 'opponent', 'head_coach',
            'opponent_coach', 'rest_days', 'opponent_rest', 'is_home',
            'temp', 'wind', 'roof', 'surface', 'stadium_id', 'stadium',
            'game_type', 'gameday']

    result = pd.concat([home[cols], away[cols]], ignore_index=True)
    return result.sort_values(['team', 'season', 'week']).reset_index(drop=True)
```

### Pattern 2: Orchestrator (from Phase 21)
**What:** Single top-level function calls individual compute functions, merges on `(team, season, week)`
**When to use:** Combining weather + rest + travel + coaching into single output
**Example:**
```python
def compute_game_context(schedules_df: pd.DataFrame, prior_season_df: pd.DataFrame = None) -> pd.DataFrame:
    """Compute all game context features from schedules data."""
    unpivoted = _unpivot_schedules(schedules_df)

    weather = compute_weather_features(unpivoted)
    rest = compute_rest_features(unpivoted)
    travel = compute_travel_features(unpivoted)
    coaching = compute_coaching_features(unpivoted, prior_season_df)

    # Merge all on (team, season, week)
    result = unpivoted[['team', 'season', 'week', 'game_id', 'is_home']].copy()
    for features_df in [weather, rest, travel, coaching]:
        result = result.merge(features_df, on=['team', 'season', 'week'], how='left')

    return result
```

### Pattern 3: Script Wiring (from silver_team_transformation.py)
**What:** CLI script reads Bronze, calls compute functions, saves Silver with timestamp
**When to use:** The standalone transformation script

### Anti-Patterns to Avoid
- **Reading all seasons into memory at once for coaching changes:** Process season-by-season, pass only the prior season's final-week coaches as context
- **Using stadium_id strings without a mapping dict:** Always go through `STADIUM_ID_TO_COORDS` -- never assume stadium_id matches team abbreviation
- **Computing timezone offsets without game date:** DST shifts UTC offsets; must use `pytz.localize()` with actual game date

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Haversine formula | Custom approximation | Standard haversine with `math` module | Well-known formula; 6 lines of code; exact enough for NFL distances |
| Timezone offsets | Manual UTC offset table | `pytz` timezone localization | DST transitions vary by year and timezone; Arizona has no DST |
| Rest days computation | Gameday date subtraction | nflverse `home_rest`/`away_rest` columns | Already computed correctly including bye weeks |

## Common Pitfalls

### Pitfall 1: Stadium ID Mapping Gaps
**What goes wrong:** `stadium_id` codes in schedules (e.g., `KAN00`, `GNB00`, `NYC01`, `OAK00`, `SDG00`) don't match `STADIUM_COORDINATES` team keys (`KC`, `GB`, `NYG`/`NYJ`, `OAK`->now `LV`, `SD`->now `LAC`)
**Why it happens:** nflverse uses PFR-style stadium IDs, not team abbreviations
**How to avoid:** Build a `STADIUM_ID_TO_COORDS` dict mapping all 42 unique stadium_ids to `(lat, lon, timezone)`. Shared stadiums (`NYC01` for NYG/NYJ, `LAX01` for LA/LAC) map to one coordinate. Legacy stadiums (`OAK00`, `SDG00`, `LAX97`, `LAX99`, `ATL00`) need coordinates too.
**Warning signs:** KeyError on stadium_id lookup; NaN travel distances

### Pitfall 2: Neutral/International Game Travel
**What goes wrong:** For neutral-site games (London, Munich, Sao Paulo, Mexico City), both teams are "away" -- travel distance should be from each team's home stadium to the neutral venue
**Why it happens:** `location == 'Neutral'` means neither team is truly home
**How to avoid:** Travel distance = haversine(team's home stadium, game venue). For home games (`location == 'Home'`), the home team gets 0 miles. For neutral games, both teams compute distance from their home.
**Warning signs:** Home team showing non-zero travel distance at neutral sites should be correct (they traveled too)

### Pitfall 3: Week 1 Coaching Tenure Across Seasons
**What goes wrong:** Coaching tenure resets incorrectly or doesn't carry across season boundaries
**Why it happens:** Same coach continuing from prior season should accumulate tenure
**How to avoid:** For each team's Week 1, check if coach matches prior season's final coach. If same coach, tenure = prior season final tenure + off-season gap. If different, tenure = 1.
**Warning signs:** All Week 1 tenures showing 1 even for returning coaches

### Pitfall 4: Timezone DST Edge Cases
**What goes wrong:** Timezone differential is wrong for early-season games (September, before fall DST change)
**Why it happens:** Arizona doesn't observe DST; some games played in different DST periods
**How to avoid:** Use `pytz.localize()` with actual `gameday` date to compute UTC offsets, then diff
**Warning signs:** ARI timezone diff showing 1 hour in November (should be 0 vs Pacific since both are UTC-7/UTC-8)

### Pitfall 5: Relocated Teams in Historical Data
**What goes wrong:** `OAK` (Oakland Raiders, pre-2020) and `SD` (San Diego Chargers, pre-2017) appear in older seasons with different stadium_ids
**Why it happens:** Teams relocated: OAK->LV (2020), SD->LAC (2017), STL->LA (2016)
**How to avoid:** `STADIUM_ID_TO_COORDS` must include legacy stadiums (`OAK00`, `SDG00`, `LAX97`/`LAX99`). Team abbreviations change but stadium_id is venue-specific so coordinates stay correct.
**Warning signs:** Missing coordinates for games before 2020

### Pitfall 6: NaN Surface Values
**What goes wrong:** `surface` is `None`/NaN for some games (seen in 2024 data -- e.g., Sao Paulo game)
**Why it happens:** International venues sometimes lack surface metadata in nflverse
**How to avoid:** Pass through as-is per user decision; downstream consumers handle NaN

## Code Examples

### Haversine Distance
```python
from math import radians, sin, cos, sqrt, atan2

def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in miles between two points."""
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))
```

### Timezone Differential
```python
import pytz
from datetime import datetime

def _timezone_diff_hours(tz_name1: str, tz_name2: str, game_date: str) -> float:
    """Compute absolute timezone difference in hours on a specific date."""
    dt = datetime.strptime(game_date, "%Y-%m-%d").replace(hour=12)
    tz1 = pytz.timezone(tz_name1)
    tz2 = pytz.timezone(tz_name2)
    offset1 = tz1.localize(dt).utcoffset().total_seconds() / 3600
    offset2 = tz2.localize(dt).utcoffset().total_seconds() / 3600
    return abs(offset1 - offset2)
```

### Weather Feature Computation
```python
def compute_weather_features(unpivoted_df: pd.DataFrame) -> pd.DataFrame:
    """Derive weather flags from raw temp/wind/roof/surface."""
    df = unpivoted_df[['team', 'season', 'week']].copy()

    # Dome detection
    df['is_dome'] = unpivoted_df['roof'].isin(['dome', 'closed'])

    # Neutral values for dome games
    df['temperature'] = unpivoted_df['temp'].copy()
    df['wind_speed'] = unpivoted_df['wind'].copy()
    df.loc[df['is_dome'], 'temperature'] = 72.0
    df.loc[df['is_dome'], 'wind_speed'] = 0.0

    # Derived flags (NaN -> False)
    df['is_high_wind'] = (df['wind_speed'] > 15).fillna(False)
    df['is_cold'] = (df['temperature'] <= 32).fillna(False)

    # Surface pass-through
    df['surface'] = unpivoted_df['surface'].values

    return df
```

### Stadium ID Mapping Approach
```python
# In config.py -- maps nflverse stadium_id to (lat, lon, timezone)
STADIUM_ID_COORDS = {
    # Current NFL stadiums
    'PHO00': (33.5277, -112.2626, 'America/Phoenix'),      # State Farm Stadium (ARI)
    'ATL97': (33.7554, -84.4010, 'America/New_York'),       # Mercedes-Benz Stadium
    'BAL00': (39.2780, -76.6228, 'America/New_York'),       # M&T Bank Stadium
    'BUF00': (42.7738, -78.7870, 'America/New_York'),       # Highmark Stadium
    'KAN00': (39.0489, -94.4839, 'America/Chicago'),        # Arrowhead
    'GNB00': (44.5013, -88.0622, 'America/Chicago'),        # Lambeau
    'NYC01': (40.8128, -74.0742, 'America/New_York'),       # MetLife (NYG/NYJ)
    'LAX01': (33.9534, -118.3390, 'America/Los_Angeles'),   # SoFi (LA/LAC)
    'VEG00': (36.0909, -115.1833, 'America/Los_Angeles'),   # Allegiant (LV)
    # ... (all 42 entries)
    # Legacy stadiums
    'OAK00': (37.7516, -122.2006, 'America/Los_Angeles'),   # Oakland Coliseum
    'SDG00': (32.7831, -117.1196, 'America/Los_Angeles'),   # Qualcomm Stadium
    'LAX97': (33.8644, -118.2611, 'America/Los_Angeles'),   # LA Memorial Coliseum (LAC temp)
    'LAX99': (33.8644, -118.2611, 'America/Los_Angeles'),   # LA Memorial Coliseum (LA temp)
    'ATL00': (33.7573, -84.4009, 'America/New_York'),       # Georgia Dome
    # International venues
    'LON00': (51.5560, -0.2795, 'Europe/London'),           # Wembley
    'LON01': (51.5560, -0.2795, 'Europe/London'),           # Wembley (alt ID)
    'LON02': (51.6043, -0.0662, 'Europe/London'),           # Tottenham
    'GER00': (48.2188, 11.6247, 'Europe/Berlin'),           # Allianz Arena
    'MEX00': (19.3029, -99.1505, 'America/Mexico_City'),    # Estadio Azteca
    'SAO00': (-23.5275, -46.6780, 'America/Sao_Paulo'),     # Neo Quimica Arena
    'FRA00': (50.0688, 8.6453, 'Europe/Berlin'),            # Deutsche Bank Park (Frankfurt)
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Compute rest from gameday dates | Use nflverse pre-computed `home_rest`/`away_rest` | nflverse standard | Eliminates date arithmetic edge cases |
| Hard-coded UTC offsets | `pytz` localized offsets | Standard practice | Correct DST handling year-round |

**Key data facts verified from Bronze:**
- 285 rows per season (2024) = regular + playoff games
- `game_type` values: `REG`, `WC`, `DIV`, `CON`, `SB`
- `location` values: `Home`, `Neutral` (no `Away` -- away is implicit)
- Rest range: 4-14 days (already within cap)
- Temp range: 14-93F when present; NaN for dome/international
- Wind range: 0-20 mph when present
- 42 unique `stadium_id` values across 2016-2025

## Open Questions

1. **Regular season only or include playoffs?**
   - What we know: Schedules include `game_type` in (`REG`, `WC`, `DIV`, `CON`, `SB`). Success criteria says "per-team per-week" which covers all weeks.
   - What's unclear: Whether downstream consumers want playoff game context or just regular season
   - Recommendation: Include all game types (filter downstream if needed); add `game_type` column to output. Regular season filter is trivially `game_type == 'REG'`.

2. **Include `is_home` in output?**
   - What we know: CONTEXT.md lists this as Claude's discretion; `is_home` naturally falls out of the unpivot
   - Recommendation: YES -- include `is_home` flag. It's free from the unpivot and highly useful for downstream prediction models (home-field advantage is one of the strongest NFL predictors).

3. **Frankfurt stadium (`FRA00`) missing from `STADIUM_COORDINATES`**
   - What we know: Frankfurt hosted 2 games in 2023; not in current `STADIUM_COORDINATES` dict
   - Recommendation: Add to `STADIUM_ID_COORDS` with coords `(50.0688, 8.6453, 'Europe/Berlin')`

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pytest runs from project root |
| Quick run command | `python -m pytest tests/test_game_context.py -v -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCHED-01 | Weather features: dome -> temp=72/wind=0, is_dome, is_high_wind, is_cold flags | unit | `python -m pytest tests/test_game_context.py::test_weather_features -x` | Wave 0 |
| SCHED-01 | NaN temp/wind -> False flags | unit | `python -m pytest tests/test_game_context.py::test_weather_nan_handling -x` | Wave 0 |
| SCHED-02 | Rest days unpivot, capping at 14, is_short_rest, is_post_bye, rest_advantage | unit | `python -m pytest tests/test_game_context.py::test_rest_features -x` | Wave 0 |
| SCHED-03 | Haversine distance computation, home=0 miles, neutral site both teams travel | unit | `python -m pytest tests/test_game_context.py::test_travel_distance -x` | Wave 0 |
| SCHED-04 | Timezone differential with DST awareness | unit | `python -m pytest tests/test_game_context.py::test_timezone_diff -x` | Wave 0 |
| SCHED-05 | Coaching change detection (off-season + mid-season), tenure tracking | unit | `python -m pytest tests/test_game_context.py::test_coaching_features -x` | Wave 0 |
| ALL | Unpivot produces 2x rows, joinable on [team, season, week] | unit | `python -m pytest tests/test_game_context.py::test_unpivot -x` | Wave 0 |
| ALL | End-to-end: compute_game_context produces correct shape and columns | integration | `python -m pytest tests/test_game_context.py::test_game_context_e2e -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_game_context.py -v -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_game_context.py` -- all unit tests for SCHED-01 through SCHED-05
- [ ] No framework install needed (pytest already configured)

## Sources

### Primary (HIGH confidence)
- Local Bronze data inspection: `data/bronze/schedules/season=2024/` -- schema, value ranges, NaN patterns
- `src/config.py` -- `STADIUM_COORDINATES` dict (35 entries with lat/lon/timezone)
- `src/team_analytics.py` -- `_build_opponent_schedule()` unpivot reference, `apply_team_rolling()` pattern
- `scripts/silver_team_transformation.py` -- Script wiring pattern for Silver output

### Secondary (MEDIUM confidence)
- Cross-season data inspection (2016-2025): 42 unique stadium_ids, coaching change patterns, relocated teams
- `pytz` timezone offset computation verified locally with known NFL city pairs

### Tertiary (LOW confidence)
- Legacy stadium coordinates (OAK00, SDG00, LAX97/99, ATL00) -- approximate from known addresses; verify exact lat/lon before implementation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies
- Architecture: HIGH -- follows established Phase 21 orchestrator pattern exactly
- Data schema: HIGH -- verified directly from Bronze parquet files
- Stadium mapping: MEDIUM -- 42 IDs identified; coordinates for current stadiums from STADIUM_COORDINATES; legacy/international need some new entries
- Pitfalls: HIGH -- derived from actual data inspection (NaN patterns, value ranges, relocated teams)

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable domain; nflverse schema unlikely to change mid-season)
