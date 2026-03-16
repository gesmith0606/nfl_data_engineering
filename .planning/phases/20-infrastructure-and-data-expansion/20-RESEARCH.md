# Phase 20: Infrastructure and Data Expansion - Research

**Researched:** 2026-03-16
**Domain:** Bronze data expansion (PBP columns, officials ingestion, stadium coordinates)
**Confidence:** HIGH

## Summary

Phase 20 is a pure infrastructure phase that unblocks all subsequent v1.3 Silver feature work (Phases 21-23). It has three deliverables: (1) expand the `PBP_COLUMNS` list in `config.py` by ~25 columns to expose penalty detail, special teams, fumble recovery, and drive fields, then re-ingest PBP for 2016-2025; (2) add `officials` as a new Bronze data type using `nfl.import_officials()`; (3) add a static `STADIUM_COORDINATES` dict to `config.py` with 32 team venues plus international sites.

All three deliverables have been verified as technically feasible. The nflverse PBP dataset contains 397 columns; all 46 columns identified for expansion exist and are populated for 2024 (confirmed via live query). The `import_officials()` function in nfl-data-py 0.3.3 works and returns data for 2015-2025 with columns `game_id`, `name`, `off_pos`, `official_id`, `season` (note: column names differ from research assumptions -- `name` not `official_name`, `off_pos` not `position`). Stadium coordinates are available from multiple public sources but require manual curation for current venues (Chargers/Rams at SoFi, Raiders in Las Vegas, Commanders name).

The existing Bronze PBP files for 2016-2025 contain exactly 103 columns matching the current `PBP_COLUMNS` list. Re-ingestion will replace these with ~128-column files. The critical risk is ensuring the existing Silver pipeline (289 tests) continues to pass after expansion -- since new columns are purely additive and existing columns are unchanged, this should be safe, but must be verified.

**Primary recommendation:** Extend `PBP_COLUMNS` in-place (per CONTEXT.md decision), re-ingest all 10 seasons, add officials registry entry, add stadium coordinates dict, then run full test suite to confirm zero regressions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Extend the existing `PBP_COLUMNS` list in `config.py` by appending ~25 new columns -- do NOT create a separate `PBP_EXTENDED_COLUMNS` list
- New columns include: `penalty_type`, `penalty_yards`, `penalty_team`, `penalty_player_id`, `penalty_player_name`, `special_teams_play`, `st_play_type`, `kickoff_attempt`, `punt_attempt`, `kick_distance`, `return_yards`, `field_goal_result`, `field_goal_attempt`, `extra_point_result`, `extra_point_attempt`, `punt_blocked`, `fumble_forced`, `fumble_not_forced`, `fumble_recovery_1_team`, `fumble_recovery_1_yards`, `fumble_recovery_1_player_id`, `kickoff_returner_player_id`, `punt_returner_player_id`, `drive_play_count`, `drive_time_of_possession`
- Verify each column exists in the nflverse PBP schema before adding
- Re-ingest all PBP data for 2016-2025 with the expanded column set (full re-download, not supplement)
- Existing Silver pipeline must still pass all 289 tests after expansion
- Add `officials` as a new Bronze data type using `nfl.import_officials()` from nfl-data-py 0.3.3
- Follow the existing registry dispatch pattern in `bronze_ingestion_simple.py`
- Add corresponding entry in `DATA_TYPE_SEASON_RANGES` in `config.py` (2015-2025 based on nflverse coverage)
- Officials data joins to schedules via `game_id` -- include `game_id`, `official_name`, `official_position`, `jersey_number` columns
- Store stadium coordinates as static dict `STADIUM_COORDINATES` in `config.py` -- approximately 35 entries
- Each entry: team abbreviation -> (latitude, longitude, timezone, venue_name)
- Include timezone for time zone differential computation in Phase 22
- Haversine distance will be computed in Phase 22 -- this phase just provides the lookup data
- Sanity check: NYJ-to-LAR should compute to approximately 2,450 miles

### Claude's Discretion
- Exact list of ~25 PBP columns to add (verify against nflverse schema, err on the side of including more)
- Whether to add an `NFLDataAdapter.fetch_officials()` method or wire directly in the registry
- Ordering and grouping of new columns within `PBP_COLUMNS` (suggest grouping by category: penalty, ST, fumble recovery, drive)
- Whether to include `fumble_recovery_2_*` columns (rare but exists in nflverse)
- International venue list (London Tottenham, London Wembley, Munich, Mexico City, Sao Paulo, Madrid -- confirm which have hosted NFL games)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | PBP column expansion (~25 columns for penalties, special teams, fumbles, drives) with re-ingestion of historical PBP data | All 46 target columns verified present in nflverse PBP (397 total columns). Current Bronze has exactly 103 columns. Re-ingestion via existing `bronze_ingestion_simple.py --data-type pbp --seasons 2016-2025` will use expanded `PBP_COLUMNS` automatically. |
| INFRA-02 | Officials Bronze ingestion via `import_officials()` with historical coverage (2016-2025) | `import_officials()` verified working in nfl-data-py 0.3.3. Returns columns: `game_id`, `name`, `off_pos`, `official_id`, `season`. Coverage confirmed for 2015-2025. Positions: BJ, DJ, FJ, LJ, R, SJ, U (7 officials per game). |
| INFRA-03 | Stadium coordinates (~35 venues) for travel distance computation | Static dict pattern matches existing `TEAM_DIVISIONS` in config.py. 30 unique stadiums (2 shared: MetLife for NYG/NYJ, SoFi for LA/LAC). International venues: London Tottenham, London Wembley, Munich Allianz Arena, Mexico City Azteca, Sao Paulo, Madrid (all confirmed NFL game hosts through 2025). |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| nfl-data-py | 0.3.3 | `import_pbp_data()` with expanded columns, `import_officials()` | Already installed; only module that calls nflverse APIs |
| pandas | 1.5.3 | DataFrame operations for validation | No change from existing |
| pyarrow | 21.0.0 | Parquet read/write for expanded Bronze files | No change from existing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| math (stdlib) | -- | Haversine sanity check for stadium coordinates | Built-in; used only for validation in this phase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extending `PBP_COLUMNS` in-place | Creating `PBP_EXTENDED_COLUMNS` | User locked decision: extend in-place. Simpler, avoids dual-list maintenance. |
| Full re-ingestion | Supplemental join on game_id+play_id | User locked decision: full re-download. Cleaner -- one file per season with all columns. |
| Static dict for stadiums | CSV file or database table | Dict in config.py matches `TEAM_DIVISIONS` pattern; 35 entries is trivially small. |

**Installation:**
```bash
# No new dependencies needed
source venv/bin/activate
```

## Architecture Patterns

### Recommended Project Structure
```
src/
  config.py              # MODIFY: extend PBP_COLUMNS, add DATA_TYPE_SEASON_RANGES["officials"],
                         #         add STADIUM_COORDINATES dict
  nfl_data_adapter.py    # MODIFY: add fetch_officials() method
scripts/
  bronze_ingestion_simple.py  # MODIFY: add "officials" to DATA_TYPE_REGISTRY
data/bronze/
  pbp/season=YYYY/       # RE-INGEST: ~128 columns replacing 103-column files
  officials/season=YYYY/ # NEW: officials parquet files for 2016-2025
```

### Pattern 1: PBP Column Expansion (Config-Only Change)
**What:** Append ~25 new columns to the `PBP_COLUMNS` list in `config.py`. The existing `fetch_pbp()` adapter method and `bronze_ingestion_simple.py` already pass `PBP_COLUMNS` as the column filter -- expanding the list automatically flows through.
**When to use:** Always -- the column list is the single source of truth for PBP ingestion.
**Example:**
```python
# In config.py PBP_COLUMNS, append after existing columns:
# Penalty detail (5)
"penalty_type", "penalty_yards", "penalty_team",
"penalty_player_id", "penalty_player_name",
# Special teams flags (4)
"special_teams_play", "st_play_type",
"kickoff_attempt", "punt_attempt",
# Special teams results (6)
"kick_distance", "return_yards",
"field_goal_result", "field_goal_attempt",
"extra_point_result", "extra_point_attempt",
# Special teams detail (3)
"punt_blocked",
"kickoff_returner_player_id", "punt_returner_player_id",
# Fumble recovery (5)
"fumble_forced", "fumble_not_forced",
"fumble_recovery_1_team", "fumble_recovery_1_yards",
"fumble_recovery_1_player_id",
# Drive detail (2)
"drive_play_count", "drive_time_of_possession",
```

### Pattern 2: Registry Dispatch for New Bronze Type
**What:** Add `officials` to `DATA_TYPE_REGISTRY` in `bronze_ingestion_simple.py` and `DATA_TYPE_SEASON_RANGES` in `config.py`. Follow the exact pattern used by all 15 existing data types.
**When to use:** Always when adding a new Bronze data type.
**Example:**
```python
# In bronze_ingestion_simple.py DATA_TYPE_REGISTRY:
"officials": {
    "adapter_method": "fetch_officials",
    "bronze_path": "officials/season={season}",
    "requires_week": False,
    "requires_season": True,
},

# In config.py DATA_TYPE_SEASON_RANGES:
"officials": (2015, get_max_season),
```

### Pattern 3: Adapter Fetch Method for Officials
**What:** Add `fetch_officials()` to `NFLDataAdapter` following the same pattern as other fetch methods.
**When to use:** Recommended (per Claude's discretion) -- keeps all nfl-data-py calls in the adapter.
**Example:**
```python
# In nfl_data_adapter.py:
def fetch_officials(self, seasons: List[int]) -> pd.DataFrame:
    """Fetch officials data for the given seasons.

    Args:
        seasons: List of season years.

    Returns:
        DataFrame with columns: game_id, name, off_pos, official_id, season.
    """
    seasons = self._filter_seasons("officials", seasons)
    if not seasons:
        return pd.DataFrame()
    nfl = self._import_nfl()
    return self._safe_call("fetch_officials", nfl.import_officials, seasons)
```

### Pattern 4: Static Configuration Dict
**What:** Add `STADIUM_COORDINATES` dict to `config.py` following the same pattern as `TEAM_DIVISIONS`.
**When to use:** For small, rarely-changing reference data.
**Example:**
```python
# In config.py:
STADIUM_COORDINATES = {
    # team_abbr: (latitude, longitude, timezone, venue_name)
    "ARI": (33.5277, -112.2626, "America/Phoenix", "State Farm Stadium"),
    "ATL": (33.7554, -84.4010, "America/New_York", "Mercedes-Benz Stadium"),
    "BAL": (39.2780, -76.6228, "America/New_York", "M&T Bank Stadium"),
    # ... 29 more teams
    "NYG": (40.8128, -74.0742, "America/New_York", "MetLife Stadium"),
    "NYJ": (40.8128, -74.0742, "America/New_York", "MetLife Stadium"),
    "LA":  (33.9534, -118.3390, "America/Los_Angeles", "SoFi Stadium"),
    "LAC": (33.9534, -118.3390, "America/Los_Angeles", "SoFi Stadium"),
    # International venues
    "LON_TOT": (51.6043, -0.0662, "Europe/London", "Tottenham Hotspur Stadium"),
    "LON_WEM": (51.5560, -0.2795, "Europe/London", "Wembley Stadium"),
    "MUN": (48.2188, 11.6247, "Europe/Berlin", "Allianz Arena"),
    "MEX": (19.3029, -99.1505, "America/Mexico_City", "Estadio Azteca"),
    "SAO": (-23.5275, -46.6780, "America/Sao_Paulo", "Neo Quimica Arena"),
    "MAD": (40.4530, -3.6883, "Europe/Madrid", "Santiago Bernabeu"),
}
```

### Anti-Patterns to Avoid
- **Creating PBP_EXTENDED_COLUMNS as a separate list:** User decision locks this -- extend PBP_COLUMNS in-place.
- **Wiring officials ingestion directly without an adapter method:** While technically possible via the registry, adding a `fetch_officials()` method maintains the adapter's role as the sole nfl-data-py interface.
- **Hardcoding stadium coordinates with team names instead of abbreviations:** Use the same abbreviations as `TEAM_DIVISIONS` for consistency.
- **Including all 397 PBP columns:** Only add the ~25 columns needed for v1.3 features. Adding unnecessary columns wastes disk space and memory.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PBP column filtering | Custom column selection logic | `PBP_COLUMNS` list passed to `import_pbp_data(columns=...)` | nfl-data-py handles column projection natively; the list is the single config point |
| Officials data parsing | Custom CSV download/parse from nflverse GitHub | `nfl.import_officials(years)` | Function handles URL resolution, caching, column types |
| Season validation | Manual range checks for officials | `DATA_TYPE_SEASON_RANGES` + `validate_season_for_type()` | Existing validation framework handles all data types uniformly |
| Parquet file management | Custom file naming/path logic | `save_local()` in `bronze_ingestion_simple.py` | Existing function handles directory creation, timestamp suffixing |

**Key insight:** This phase is almost entirely configuration changes. The ingestion infrastructure already handles everything -- we are just expanding what it knows about.

## Common Pitfalls

### Pitfall 1: Officials Column Names Differ from Research Assumptions
**What goes wrong:** CONTEXT.md references `official_name`, `official_position`, `jersey_number` columns. The actual columns returned by `import_officials()` are `name`, `off_pos`, `official_id`, `season`, `game_id`.
**Why it happens:** Research documentation used the nflverse data dictionary names; the Python function uses abbreviated column names.
**How to avoid:** Use the verified column names: `name`, `off_pos`, `official_id`. If downstream phases expect `official_name` / `official_position`, rename during ingestion or document the mapping.
**Warning signs:** KeyError when accessing `official_name` or `position` on the officials DataFrame.

### Pitfall 2: Existing PBP Bronze Files Must Be Replaced, Not Augmented
**What goes wrong:** Running re-ingestion creates a new timestamped file alongside the old 103-column file. `download_latest_parquet()` reads the newest file (128 columns), but if Silver code accidentally reads the old file, columns will be missing.
**Why it happens:** The timestamped file pattern preserves history by design. Old files are not automatically deleted.
**How to avoid:** After successful re-ingestion and validation, remove or archive old PBP files. Or accept that `download_latest_parquet()` always returns the newest file and old files are harmless (just wasted disk space).
**Warning signs:** Two PBP files per season with different column counts.

### Pitfall 3: PBP Re-Ingestion Takes Time -- One Season at a Time
**What goes wrong:** Attempting to ingest all 10 seasons at once can fail due to memory or network timeouts. Each season is ~50-100 MB of PBP data.
**Why it happens:** nfl-data-py downloads from GitHub releases; large batch downloads can timeout.
**How to avoid:** Use `--seasons 2016-2025` which the existing batch mode handles one season at a time (see `bronze_ingestion_simple.py` line 360). Monitor progress via the per-season print output.
**Warning signs:** Script hanging or returning empty DataFrames for some seasons.

### Pitfall 4: Stadium Coordinate Accuracy Matters for Haversine
**What goes wrong:** Using outdated coordinates (e.g., Raiders in Oakland, Rams in St. Louis, Chargers in San Diego) produces wrong travel distances.
**Why it happens:** Many online NFL stadium coordinate datasets are from pre-2020 and reflect old locations.
**How to avoid:** Verify each coordinate against current venue. Key relocations to catch: Raiders to Las Vegas (Allegiant Stadium, 2020), Rams/Chargers to Inglewood (SoFi Stadium, 2020). Bills new Highmark Stadium opens 2026 -- use current Highmark Stadium coordinates for now.
**Warning signs:** NYJ-to-LAR haversine not approximately 2,450 miles. LV distance to Oakland being 0.

### Pitfall 5: International Venue Keys Must Not Collide with Team Abbreviations
**What goes wrong:** Using a team abbreviation like "LA" for an international venue would overwrite the Rams entry.
**Why it happens:** International venues are not teams -- they need a separate key namespace.
**How to avoid:** Use descriptive keys for international venues: `LON_TOT`, `LON_WEM`, `MUN`, `MEX`, `SAO`, `MAD`. Phase 22's game_context module will look up the away team's home stadium and the game venue separately.
**Warning signs:** `STADIUM_COORDINATES["LA"]` returning London coordinates.

## Code Examples

### Verified: PBP Column Availability (Live Query, 2026-03-16)
```python
# All 46 target columns confirmed present in nflverse PBP (397 total columns)
# Tested against 2024 season data via import_pbp_data([2024], columns=None)
# Penalty columns: penalty_type, penalty_yards, penalty_team, penalty_player_id, penalty_player_name
# ST columns: special_teams_play, st_play_type, kickoff_attempt, punt_attempt, kick_distance,
#   return_yards, field_goal_result, field_goal_attempt, extra_point_result, extra_point_attempt,
#   punt_blocked, kickoff_returner_player_id, punt_returner_player_id
# Fumble columns: fumble_forced, fumble_not_forced, fumble_recovery_1_team,
#   fumble_recovery_1_yards, fumble_recovery_1_player_id, fumble_recovery_2_team
# Drive columns: drive_play_count, drive_time_of_possession
# Also available: punt_inside_twenty, punt_in_endzone, punt_out_of_bounds, punt_downed,
#   punt_fair_catch, kickoff_inside_twenty, kickoff_in_endzone, kickoff_out_of_bounds,
#   kickoff_downed, kickoff_fair_catch, own_kickoff_recovery, kicker_player_id,
#   kicker_player_name, punt_returner_player_name, kickoff_returner_player_name,
#   fumbled_1_team, fumbled_1_player_id, fumble_recovery_2_yards, blocked_player_id,
#   blocked_player_name, own_kickoff_recovery_td, fumble_recovery_1_player_name
```

### Verified: Officials Data Schema (Live Query, 2026-03-16)
```python
# nfl.import_officials([2024]) returns:
# Rows: 1995, Columns: 5
# Columns: ['game_id', 'name', 'off_pos', 'official_id', 'season']
# Positions: BJ (Back Judge), DJ (Down Judge), FJ (Field Judge),
#            LJ (Line Judge), R (Referee), SJ (Side Judge), U (Umpire)
# Coverage: 2015-2025 confirmed
# Join key: game_id (matches schedules Bronze)
```

### Haversine Sanity Check
```python
import math

def haversine_miles(lat1, lon1, lat2, lon2):
    """Compute great-circle distance in miles between two points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

# NYJ (MetLife) to LA (SoFi): expect ~2,450 miles
dist = haversine_miles(40.8128, -74.0742, 33.9534, -118.3390)
# Result: ~2,445 miles -- within expected range
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 103-column curated PBP | ~128-column expanded PBP | This phase | Enables penalty, ST, fumble recovery, drive analysis in Phases 21-23 |
| No officials data | Officials Bronze type | This phase | Enables referee crew analysis in Phase 23 |
| No stadium coordinates | Static STADIUM_COORDINATES dict | This phase | Enables travel distance in Phase 22 |

**Deprecated/outdated:**
- The nfl-data-py package was archived September 2025 (read-only). Still functional on Python 3.9. No impact on this phase -- `import_pbp_data()` and `import_officials()` both work. Flag for future migration to nflreadpy (requires Python 3.10+).

## Open Questions

1. **Column count: 25 vs more?**
   - What we know: CONTEXT.md specifies ~25 columns. Verification found all 25 plus ~21 additional useful columns (punt_inside_twenty, kickoff_inside_twenty, kicker_player_id, etc.)
   - What's unclear: Should we include all verified columns (~46 total new) or stick to the ~25 specified?
   - Recommendation: Include additional columns that downstream phases will use (punt_inside_twenty for ST metrics, kicker_player_id for kicker tracking). Err on the side of including more per CONTEXT.md discretion guidance. Target ~30-35 new columns.

2. **Officials column renaming**
   - What we know: Actual columns are `name`, `off_pos`, `official_id`, not `official_name`, `official_position`, `jersey_number`
   - What's unclear: Should we rename during ingestion to match CONTEXT.md expectations, or document the actual names?
   - Recommendation: Rename during ingestion (`name` -> `official_name`, `off_pos` -> `official_position`) for clarity. Keep `official_id` as-is. Note: there is no `jersey_number` column -- it does not exist in the data.

3. **Old PBP file cleanup**
   - What we know: Re-ingestion creates new timestamped files; old 103-column files remain
   - What's unclear: Should old files be deleted or kept for rollback?
   - Recommendation: Keep old files temporarily. `download_latest_parquet()` always reads the newest. Clean up in a later maintenance pass if disk space is a concern.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (latest via pip) |
| Config file | None (default discovery) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01a | PBP_COLUMNS expanded to ~128 columns | unit | `python -m pytest tests/test_infrastructure.py -x -k "pbp_columns"` | Wave 0 |
| INFRA-01b | PBP Bronze files for 2016-2025 contain expanded columns | smoke | `python -c "import pandas as pd; df = pd.read_parquet('data/bronze/pbp/season=2024/...'); assert 'penalty_type' in df.columns"` | Wave 0 |
| INFRA-01c | Existing 289 tests pass with no regressions | regression | `python -m pytest tests/ -v` | Existing (289 tests) |
| INFRA-02a | Officials registry entry and adapter method exist | unit | `python -m pytest tests/test_infrastructure.py -x -k "officials"` | Wave 0 |
| INFRA-02b | Officials Bronze data exists for 2016-2025 | smoke | `python -c "import pandas as pd; df = pd.read_parquet('data/bronze/officials/season=2024/...'); assert len(df) > 0"` | Wave 0 |
| INFRA-03a | STADIUM_COORDINATES has all 32 teams + international venues | unit | `python -m pytest tests/test_infrastructure.py -x -k "stadium"` | Wave 0 |
| INFRA-03b | Haversine sanity check NYJ-to-LAR ~2450 miles | unit | `python -m pytest tests/test_infrastructure.py -x -k "haversine"` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green (289+ tests) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_infrastructure.py` -- new test file for INFRA-01/02/03 validations (PBP column count, officials schema, stadium coordinates, haversine check)
- [ ] No new fixtures needed -- tests can import from `src/config.py` directly and read Bronze parquet files

## Sources

### Primary (HIGH confidence)
- Live query of nfl-data-py `import_pbp_data([2024], columns=None)` -- 397 columns, all 46 target columns present (2026-03-16)
- Live query of nfl-data-py `import_officials([2024])` -- 1995 rows, 5 columns: `game_id`, `name`, `off_pos`, `official_id`, `season` (2026-03-16)
- Live query of nfl-data-py `import_officials([2015, 2016])` -- 3772 rows, confirmed 2015+ coverage (2026-03-16)
- Direct inspection of `src/config.py` PBP_COLUMNS (103 columns, lines 156-203)
- Direct inspection of `scripts/bronze_ingestion_simple.py` DATA_TYPE_REGISTRY (15 data types)
- Direct inspection of `src/nfl_data_adapter.py` fetch method pattern (15 methods)
- Existing Bronze PBP files: `data/bronze/pbp/season=2016` through `season=2025` (10 seasons present)
- Full test suite: 289 tests collected, all passing

### Secondary (MEDIUM confidence)
- nflverse PBP Data Dictionary: https://nflreadr.nflverse.com/articles/dictionary_pbp.html
- NFL international games: confirmed London (Tottenham + Wembley), Munich, Mexico City, Sao Paulo, Madrid through 2025 season
- GitHub NFL stadium coordinates CSV (outdated -- used for cross-reference only, not as source of truth): https://github.com/Sinbad311/CloudProject/blob/master/NFL%20Stadium%20Latitude%20and%20Longtitude.csv
- Kaggle NFL stadium coordinates dataset: https://www.kaggle.com/datasets/teaspice/nfl-home-stadium-coordinates

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all capabilities verified via live queries
- Architecture: HIGH -- pure config changes following established patterns; code paths verified
- Pitfalls: HIGH -- officials column names verified live (caught discrepancy with CONTEXT.md assumptions); PBP column existence verified; stadium coordinate sourcing challenges identified

**Research date:** 2026-03-16
**Valid until:** 2026-04-16 (stable -- nflverse data schema changes only at season boundaries)
