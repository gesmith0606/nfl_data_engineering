# Architecture Patterns

**Domain:** NFL Data Platform - Bronze Layer Expansion
**Researched:** 2026-03-08

## Recommended Architecture

### Overview

The existing Medallion Architecture (Bronze/Silver/Gold) is sound and does not need structural changes. The expansion adds 12 new data types to the Bronze layer, each fitting into one of three categories based on their temporal granularity: **weekly**, **seasonal**, or **static/reference**. The architecture recommendation is to extend the existing patterns rather than introduce new ones.

### New Data Type Classification

| Data Type | nfl-data-py Function | Granularity | Partition Strategy | Earliest Year |
|-----------|---------------------|-------------|-------------------|---------------|
| **Full PBP** | `import_pbp_data(years)` | Weekly | `plays/season=YYYY/` (season-level files, filter by week at read) | 1999 |
| **NGS Passing** | `import_ngs_data('passing', years)` | Seasonal | `ngs/passing/season=YYYY/` | 2016 |
| **NGS Rushing** | `import_ngs_data('rushing', years)` | Seasonal | `ngs/rushing/season=YYYY/` | 2016 |
| **NGS Receiving** | `import_ngs_data('receiving', years)` | Seasonal | `ngs/receiving/season=YYYY/` | 2016 |
| **PFR Seasonal** | `import_seasonal_pfr(s_type, years)` | Seasonal (x4 s_types) | `pfr/seasonal/{s_type}/season=YYYY/` | 2018 |
| **PFR Weekly** | `import_weekly_pfr(s_type, years)` | Weekly (x4 s_types) | `pfr/weekly/{s_type}/season=YYYY/` | 2018 |
| **Draft Picks** | `import_draft_picks(years)` | Annual | `draft/picks/season=YYYY/` | All time |
| **Draft Values** | `import_draft_values()` | Static | `draft/values/` (no partition) | N/A |
| **Combine** | `import_combine_data(years)` | Annual | `combine/season=YYYY/` | All time |
| **Depth Charts** | `import_depth_charts(years)` | Weekly | `depth_charts/season=YYYY/` | 2001 |
| **QBR** | `import_qbr(years, frequency)` | Weekly or Seasonal | `qbr/{frequency}/season=YYYY/` | 2006 |
| **Win Totals** | `import_win_totals(years)` | Seasonal | `betting/win_totals/season=YYYY/` | Variable |
| **SC Lines** | `import_sc_lines(years)` | Weekly | `betting/sc_lines/season=YYYY/` | Variable |
| **Officials** | `import_officials(years)` | Per-game | `officials/season=YYYY/` | Variable |
| **FTN Charting** | `import_ftn_data(years)` | Weekly | `ftn/season=YYYY/` | 2022 |
| **Contracts** | `import_contracts()` | Static | `contracts/` (no partition) | All time |
| **Players** | `import_players()` | Static | `players/reference/` (no partition) | N/A |
| **Player IDs** | `import_ids()` | Static | `players/ids/` (no partition) | N/A |

### Recommended Directory Structure

```
data/bronze/
├── games/season=YYYY/                          # (existing) schedules
├── plays/season=YYYY/                          # (EXPAND) full PBP with all 300+ cols
├── players/
│   ├── weekly/season=YYYY/                     # (existing) player weekly stats
│   ├── seasonal/season=YYYY/                   # (existing) player seasonal stats
│   ├── snap_counts/season=YYYY/                # (existing) snap counts
│   ├── injuries/season=YYYY/                   # (existing) injury reports
│   ├── rosters/season=YYYY/                    # (existing) seasonal rosters
│   ├── reference/                              # (NEW) import_players() - static
│   └── ids/                                    # (NEW) import_ids() - static
├── ngs/                                        # (NEW) Next Gen Stats
│   ├── passing/season=YYYY/
│   ├── rushing/season=YYYY/
│   └── receiving/season=YYYY/
├── pfr/                                        # (NEW) Pro Football Reference
│   ├── seasonal/
│   │   ├── pass/season=YYYY/
│   │   ├── rec/season=YYYY/
│   │   ├── rush/season=YYYY/
│   │   └── def/season=YYYY/
│   └── weekly/
│       ├── pass/season=YYYY/
│       ├── rec/season=YYYY/
│       ├── rush/season=YYYY/
│       └── def/season=YYYY/
├── draft/                                      # (NEW) Draft data
│   ├── picks/season=YYYY/
│   └── values/                                 # Static - no partition
├── combine/season=YYYY/                        # (NEW) Combine measurables
├── depth_charts/season=YYYY/                   # (NEW) Weekly depth charts
├── qbr/                                        # (NEW) ESPN QBR
│   ├── season/season=YYYY/
│   └── weekly/season=YYYY/
├── betting/                                    # (NEW) Betting lines
│   ├── win_totals/season=YYYY/
│   └── sc_lines/season=YYYY/
├── officials/season=YYYY/                      # (NEW) Game officials
├── ftn/season=YYYY/                            # (NEW) FTN charting data
├── contracts/                                  # (NEW) Contract history - static
└── teams/season=YYYY/                          # (existing but underused)
```

## Component Boundaries

### NFLDataFetcher Expansion

The `NFLDataFetcher` class in `src/nfl_data_integration.py` currently has 8 `fetch_*` methods. Adding 12+ new data types to a single class is acceptable given the class's role as a thin wrapper. Each method follows the same pattern: validate seasons, call nfl-data-py, add metadata columns, return DataFrame.

| New Method | nfl-data-py Call | Parameters | Notes |
|-----------|-----------------|------------|-------|
| `fetch_pbp_full(seasons, columns)` | `import_pbp_data(seasons, columns)` | seasons, optional columns list | Replaces limited 10-column fetch; 300+ cols available |
| `fetch_ngs(stat_type, seasons)` | `import_ngs_data(stat_type, seasons)` | stat_type: passing/rushing/receiving | Three separate calls for three stat types |
| `fetch_seasonal_pfr(s_type, seasons)` | `import_seasonal_pfr(s_type, seasons)` | s_type: pass/rec/rush/def | Four sub-types |
| `fetch_weekly_pfr(s_type, seasons)` | `import_weekly_pfr(s_type, seasons)` | s_type: pass/rec/rush/def | Four sub-types |
| `fetch_draft_picks(seasons)` | `import_draft_picks(seasons)` | seasons (optional) | Historical data |
| `fetch_draft_values()` | `import_draft_values()` | None | Static reference |
| `fetch_combine(seasons)` | `import_combine_data(seasons)` | seasons (optional) | Annual data |
| `fetch_depth_charts(seasons)` | `import_depth_charts(seasons)` | seasons | Available from 2001 |
| `fetch_qbr(seasons, frequency)` | `import_qbr(seasons, frequency=)` | seasons, frequency: season/weekly | Available from 2006 |
| `fetch_win_totals(seasons)` | `import_win_totals(seasons)` | seasons (optional) | Betting lines |
| `fetch_sc_lines(seasons)` | `import_sc_lines(seasons)` | seasons (optional) | Weekly betting |
| `fetch_officials(seasons)` | `import_officials(seasons)` | seasons (optional) | Per-game data |
| `fetch_ftn_data(seasons)` | `import_ftn_data(seasons)` | seasons | Available from 2022 only |
| `fetch_contracts()` | `import_contracts()` | None | Static historical data |
| `fetch_players_reference()` | `import_players()` | None | Static player descriptors |
| `fetch_player_ids()` | `import_ids()` | None | Cross-platform ID mapping |

### bronze_ingestion_simple.py Expansion

The existing script uses a flat `if/elif` chain for 8 data types. With 20+ total data types, refactor to a **registry pattern**:

```python
# Recommended pattern: data type registry
DATA_TYPE_REGISTRY = {
    # Existing
    'schedules':        {'fetch': 'fetch_game_schedules', 'key': 'games/season={season}/week={week}/schedules_{ts}.parquet', 'needs_week': True},
    'player_weekly':    {'fetch': 'fetch_player_weekly',  'key': 'players/weekly/season={season}/player_weekly_{ts}.parquet', 'needs_week': False},
    # ...existing types...

    # New - NGS (3 sub-types exposed as separate CLI data types)
    'ngs_passing':      {'fetch': 'fetch_ngs', 'args': {'stat_type': 'passing'},  'key': 'ngs/passing/season={season}/ngs_passing_{ts}.parquet', 'needs_week': False},
    'ngs_rushing':      {'fetch': 'fetch_ngs', 'args': {'stat_type': 'rushing'},  'key': 'ngs/rushing/season={season}/ngs_rushing_{ts}.parquet', 'needs_week': False},
    'ngs_receiving':    {'fetch': 'fetch_ngs', 'args': {'stat_type': 'receiving'},'key': 'ngs/receiving/season={season}/ngs_receiving_{ts}.parquet', 'needs_week': False},

    # New - PFR (8 sub-types: 4 seasonal + 4 weekly)
    'pfr_pass_season':  {'fetch': 'fetch_seasonal_pfr', 'args': {'s_type': 'pass'}, 'key': 'pfr/seasonal/pass/season={season}/pfr_pass_{ts}.parquet', 'needs_week': False},
    # ... etc for rec, rush, def x seasonal/weekly ...

    # New - simple types
    'draft_picks':      {'fetch': 'fetch_draft_picks',    'key': 'draft/picks/season={season}/draft_picks_{ts}.parquet', 'needs_week': False},
    'combine':          {'fetch': 'fetch_combine',        'key': 'combine/season={season}/combine_{ts}.parquet', 'needs_week': False},
    'depth_charts':     {'fetch': 'fetch_depth_charts',   'key': 'depth_charts/season={season}/depth_charts_{ts}.parquet', 'needs_week': False},
    'qbr_season':       {'fetch': 'fetch_qbr', 'args': {'frequency': 'season'}, 'key': 'qbr/season/season={season}/qbr_{ts}.parquet', 'needs_week': False},
    'qbr_weekly':       {'fetch': 'fetch_qbr', 'args': {'frequency': 'weekly'}, 'key': 'qbr/weekly/season={season}/qbr_{ts}.parquet', 'needs_week': False},
    'officials':        {'fetch': 'fetch_officials',      'key': 'officials/season={season}/officials_{ts}.parquet', 'needs_week': False},
    'win_totals':       {'fetch': 'fetch_win_totals',     'key': 'betting/win_totals/season={season}/win_totals_{ts}.parquet', 'needs_week': False},
    'sc_lines':         {'fetch': 'fetch_sc_lines',       'key': 'betting/sc_lines/season={season}/sc_lines_{ts}.parquet', 'needs_week': False},
    'ftn':              {'fetch': 'fetch_ftn_data',       'key': 'ftn/season={season}/ftn_{ts}.parquet', 'needs_week': False},

    # Static (no season partition)
    'contracts':        {'fetch': 'fetch_contracts',       'key': 'contracts/contracts_{ts}.parquet', 'needs_week': False, 'static': True},
    'draft_values':     {'fetch': 'fetch_draft_values',    'key': 'draft/values/draft_values_{ts}.parquet', 'needs_week': False, 'static': True},
    'players_ref':      {'fetch': 'fetch_players_reference','key': 'players/reference/players_{ts}.parquet', 'needs_week': False, 'static': True},
    'player_ids':       {'fetch': 'fetch_player_ids',      'key': 'players/ids/player_ids_{ts}.parquet', 'needs_week': False, 'static': True},
}
```

This replaces the `if/elif` chain with a single dispatch loop, making adding new types a one-line config change.

### config.py Expansion

Add new S3 key templates to `PLAYER_S3_KEYS` (rename to `BRONZE_S3_KEYS` since not all are player data):

```python
BRONZE_S3_KEYS = {
    # Existing (keep as-is for backward compat)
    **PLAYER_S3_KEYS,

    # NGS
    "ngs_passing": "ngs/passing/season={season}/ngs_passing_{ts}.parquet",
    "ngs_rushing": "ngs/rushing/season={season}/ngs_rushing_{ts}.parquet",
    "ngs_receiving": "ngs/receiving/season={season}/ngs_receiving_{ts}.parquet",

    # PFR
    "pfr_pass_season": "pfr/seasonal/pass/season={season}/pfr_pass_{ts}.parquet",
    "pfr_rec_season": "pfr/seasonal/rec/season={season}/pfr_rec_{ts}.parquet",
    "pfr_rush_season": "pfr/seasonal/rush/season={season}/pfr_rush_{ts}.parquet",
    "pfr_def_season": "pfr/seasonal/def/season={season}/pfr_def_{ts}.parquet",
    "pfr_pass_weekly": "pfr/weekly/pass/season={season}/pfr_pass_{ts}.parquet",
    "pfr_rec_weekly": "pfr/weekly/rec/season={season}/pfr_rec_{ts}.parquet",
    "pfr_rush_weekly": "pfr/weekly/rush/season={season}/pfr_rush_{ts}.parquet",
    "pfr_def_weekly": "pfr/weekly/def/season={season}/pfr_def_{ts}.parquet",

    # Draft & Combine
    "draft_picks": "draft/picks/season={season}/draft_picks_{ts}.parquet",
    "draft_values": "draft/values/draft_values_{ts}.parquet",
    "combine": "combine/season={season}/combine_{ts}.parquet",

    # Other
    "depth_charts": "depth_charts/season={season}/depth_charts_{ts}.parquet",
    "qbr_season": "qbr/season/season={season}/qbr_{ts}.parquet",
    "qbr_weekly": "qbr/weekly/season={season}/qbr_{ts}.parquet",
    "officials": "officials/season={season}/officials_{ts}.parquet",
    "win_totals": "betting/win_totals/season={season}/win_totals_{ts}.parquet",
    "sc_lines": "betting/sc_lines/season={season}/sc_lines_{ts}.parquet",
    "ftn": "ftn/season={season}/ftn_{ts}.parquet",
    "contracts": "contracts/contracts_{ts}.parquet",
    "players_ref": "players/reference/players_{ts}.parquet",
    "player_ids": "players/ids/player_ids_{ts}.parquet",
}
```

### validate_data() Expansion

Add required columns for each new data type. Key columns per type (verified from nfl-data-py source code):

| Data Type | Required Columns | Validation Rules |
|-----------|-----------------|------------------|
| ngs_* | `player_display_name`, `season`, `week` | season >= 2016 |
| pfr_* | `player`, `season` (weekly adds `week`) | season >= 2018 |
| draft_picks | `season`, `round`, `pick` | round 1-7 |
| combine | `season`, `pos` | standard positions |
| depth_charts | `season`, `week`, `club_code` | season >= 2001 |
| qbr | `season`, `name_display` | season >= 2006 |
| officials | `game_id`, `season` | game_id format check |
| win_totals | `season` | minimal validation |
| sc_lines | `season` | minimal validation |
| ftn | `nflverse_game_id`, `season` | season >= 2022 |

## Partitioning Strategy

### Decision: Season-Level Files, Not Week-Level

For the new data types, use **season-level partitioning** (`season=YYYY/`), not week-level. Rationale:

1. **nfl-data-py returns full-season data** - Most functions load an entire season's parquet file from GitHub. Splitting by week at ingestion means re-downloading the full dataset each week, wasting bandwidth.

2. **Existing pattern mismatch** - The current Bronze layer stores weekly-granularity data (player_weekly, snap_counts, injuries) at season level without week sub-partitions in the actual file layout. Weekly filtering happens at read time, not at storage level.

3. **New data types are bulk-loaded** - NGS, PFR, combine, draft picks, depth charts are all bulk-loaded per season. There is no per-week API endpoint.

4. **Exception: Full PBP** - PBP data is huge (50-100 MB per season, 300+ columns). Consider using nfl-data-py's built-in `cache_pbp()` for local caching, or ingesting per-season files and filtering at read time. Do NOT partition PBP by week at storage -- the source data is season-level parquet files.

### File Naming Convention

Maintain existing pattern: `{type}_{YYYYMMDD_HHMMSS}.parquet`

For sub-typed data (NGS, PFR), embed the sub-type in the filename:
- `ngs_passing_20260308_120000.parquet`
- `pfr_pass_20260308_120000.parquet`

### Static/Reference Data

Data with no season dimension (draft_values, contracts, players_ref, player_ids) should be stored without partitioning, using only the timestamp for versioning:
- `contracts/contracts_20260308_120000.parquet`
- `draft/values/draft_values_20260308_120000.parquet`

## Data Flow

### Ingestion Ordering (Dependencies)

There are no hard dependencies between Bronze data types -- they all come from independent nfl-data-py endpoints. However, ingestion **should be ordered by priority** for the downstream game prediction model:

**Tier 1 - Core (ingest first, highest value for predictions):**
1. `pbp_full` - Full play-by-play with EPA, WPA, CPOE (foundation for advanced analytics)
2. `ngs_passing` / `ngs_rushing` / `ngs_receiving` - Next Gen Stats (separation, RYOE, time-to-throw)
3. `sc_lines` - Weekly betting lines (spread, total, moneyline)

**Tier 2 - Enrichment (high value, ingest second):**
4. `pfr_pass_season` / `pfr_rec_season` / `pfr_rush_season` / `pfr_def_season` - PFR advanced stats
5. `pfr_pass_weekly` / `pfr_rec_weekly` / `pfr_rush_weekly` / `pfr_def_weekly` - PFR weekly
6. `depth_charts` - Starter/backup status
7. `qbr_weekly` / `qbr_season` - QB-specific ratings

**Tier 3 - Context (supporting data, ingest third):**
8. `draft_picks` - Draft capital (rookie evaluation)
9. `combine` - Athleticism measurables
10. `officials` - Referee tendencies
11. `win_totals` - Preseason expectations
12. `ftn` - FTN charting (2022+ only)

**Tier 4 - Reference (ingest once, refresh rarely):**
13. `draft_values` - Static pick value models
14. `contracts` - Player contract history
15. `players_ref` - Player descriptive data
16. `player_ids` - Cross-platform ID mapping

### Batch Ingestion Script

Add a `--batch` mode to `bronze_ingestion_simple.py` that ingests all data types for a given season:

```bash
# Ingest all new data types for a season
python scripts/bronze_ingestion_simple.py --season 2024 --batch all

# Ingest by tier
python scripts/bronze_ingestion_simple.py --season 2024 --batch tier1

# Ingest static/reference data (no season needed)
python scripts/bronze_ingestion_simple.py --data-type contracts
python scripts/bronze_ingestion_simple.py --data-type draft_values
```

## Storage Volume Estimates

| Data Type | Per Season | 6 Seasons (2020-2025) | Notes |
|-----------|-----------|----------------------|-------|
| Full PBP | 50-100 MB | 300-600 MB | 300+ columns, 40K+ plays/season |
| NGS (3 types) | ~2 MB each | ~36 MB | Aggregated stats |
| PFR Seasonal (4 types) | ~500 KB each | ~12 MB | |
| PFR Weekly (4 types) | ~2 MB each | ~48 MB | |
| Depth Charts | ~3 MB | ~18 MB | Weekly roster depth |
| QBR (2 types) | ~200 KB each | ~2.4 MB | |
| Draft Picks | ~200 KB | ~1.2 MB | |
| Combine | ~100 KB | ~600 KB | |
| Officials | ~500 KB | ~3 MB | |
| Win Totals | ~100 KB | ~600 KB | |
| SC Lines | ~1 MB | ~6 MB | |
| FTN | ~5 MB | ~20 MB (2022-2025 only) | |
| Contracts | ~5 MB | ~5 MB (static) | |
| Draft Values | ~50 KB | ~50 KB (static) | |
| Players Ref | ~3 MB | ~3 MB (static) | |
| Player IDs | ~1 MB | ~1 MB (static) | |
| **TOTAL NEW** | | **~460-760 MB** | PBP dominates |
| **Existing Bronze** | | **7 MB** | Current 31 files |

**Key insight:** Full PBP data represents 80%+ of new storage. Consider using `cache_pbp()` built into nfl-data-py for PBP, and ingesting column subsets if full columns are not needed for initial Silver/Gold work. For 2020-2025 (6 seasons), expect ~500 MB total new Bronze data, with PBP being the vast majority.

## Patterns to Follow

### Pattern 1: Thin Fetch Wrapper

Every new `fetch_*` method should follow this exact pattern (already established):

```python
def fetch_ngs(self, stat_type: str, seasons: List[int]) -> pd.DataFrame:
    """Fetch Next Gen Stats data.

    Args:
        stat_type: One of 'passing', 'rushing', 'receiving'
        seasons: List of seasons to fetch

    Returns:
        DataFrame with NGS data
    """
    try:
        logger.info(f"Fetching NGS {stat_type} for seasons: {seasons}")
        valid_seasons = [s for s in seasons if s in self.available_seasons and s >= 2016]
        if not valid_seasons:
            raise ValueError("No valid seasons provided (NGS available from 2016)")

        df = nfl.import_ngs_data(stat_type, valid_seasons)
        logger.info(f"Fetched {len(df)} NGS {stat_type} rows")

        df['data_source'] = 'nfl-data-py'
        df['ingestion_timestamp'] = datetime.now()
        return df

    except Exception as e:
        logger.error(f"Error fetching NGS {stat_type}: {str(e)}")
        raise
```

### Pattern 2: Local-First Write (Existing Pattern)

All new data types must write locally first, with optional S3 upload. This matches the current local-first architecture since AWS credentials are expired.

```python
# Write to local
local_path = f"data/bronze/{directory}/season={season}/{filename}_{ts}.parquet"
os.makedirs(os.path.dirname(local_path), exist_ok=True)
df.to_parquet(local_path, index=False)

# Optional S3 upload
if s3_enabled:
    upload_to_s3(df, bronze_bucket, s3_key, aws_credentials)
```

### Pattern 3: Year-Range Awareness

Each data type has a different availability window. Encode this in the registry:

```python
DATA_TYPE_AVAILABILITY = {
    'pbp_full': {'min_year': 1999},
    'ngs_passing': {'min_year': 2016},
    'ngs_rushing': {'min_year': 2016},
    'ngs_receiving': {'min_year': 2016},
    'pfr_pass_season': {'min_year': 2018},
    'depth_charts': {'min_year': 2001},
    'qbr_season': {'min_year': 2006},
    'ftn': {'min_year': 2022},
    'snap_counts': {'min_year': 2012},  # existing - currently not enforced
    'injuries': {'min_year': 2009},     # existing - currently not enforced
}
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Week-Level Partitioning for Bulk Data
**What:** Storing each week as a separate file when the source returns full-season data.
**Why bad:** Forces re-downloading the full season dataset to extract one week; creates hundreds of tiny files.
**Instead:** Store at season level, filter by week column at read time.

### Anti-Pattern 2: Full PBP Column Ingestion Without Purpose
**What:** Ingesting all 300+ PBP columns "just in case."
**Why bad:** 50-100 MB per season; most columns are not used in projections or predictions.
**Instead:** Start with a curated column list (~50-80 key columns including EPA, WPA, CPOE, air_yards, personnel, etc.). Add columns as Silver/Gold layers need them. Use `columns` parameter of `import_pbp_data()`.

### Anti-Pattern 3: Single Monolithic Ingestion Run
**What:** One script call that ingests all 20+ data types sequentially.
**Why bad:** One failure stops the entire pipeline; PBP alone takes minutes.
**Instead:** Support per-type ingestion (current pattern) plus batch mode with `continue-on-error` semantics. Log successes/failures independently.

### Anti-Pattern 4: Duplicating Sub-Type Logic
**What:** Writing separate `fetch_ngs_passing()`, `fetch_ngs_rushing()`, `fetch_ngs_receiving()` methods.
**Why bad:** Code duplication; the only difference is the `stat_type` string.
**Instead:** Single `fetch_ngs(stat_type, seasons)` method with the stat_type as a parameter. Same for PFR: `fetch_seasonal_pfr(s_type, seasons)`.

## Scalability Considerations

| Concern | Current (7 MB) | After Expansion (~500 MB) | At 10 Seasons (~1 GB) |
|---------|----------------|--------------------------|----------------------|
| Local disk | Trivial | Manageable | Still fine |
| Ingestion time | < 1 min | 5-10 min (PBP dominates) | 10-20 min |
| Memory during PBP load | N/A | ~500 MB RAM per season | Use `downcast=True`, column filtering |
| Pipeline reliability | Batch all | Separate PBP from light data types | Add retry logic for HTTP failures |

### PBP-Specific Considerations

Full PBP is the only data type that requires special handling due to size:

1. **Use `thread_requests=True`** for multi-season PBP loads (available in nfl-data-py)
2. **Use `downcast=True`** (default) to convert float64 to float32 (~30% memory savings)
3. **Consider `cache_pbp()`** - nfl-data-py has built-in caching that stores season files locally. This avoids re-downloading on every run.
4. **Column filtering** - Use the `columns` parameter to only pull needed columns. Start with the ~80 most useful for game prediction and fantasy analytics.

### Recommended PBP Column Subset (Initial)

```python
PBP_CORE_COLUMNS = [
    # Identity
    'game_id', 'play_id', 'season', 'week', 'season_type',
    # Teams
    'home_team', 'away_team', 'posteam', 'defteam',
    # Situation
    'quarter_seconds_remaining', 'half_seconds_remaining', 'game_seconds_remaining',
    'down', 'ydstogo', 'yardline_100', 'goal_to_go',
    # Play info
    'play_type', 'yards_gained', 'first_down', 'touchdown', 'interception',
    'fumble', 'sack', 'penalty', 'penalty_yards',
    # Scoring
    'total_home_score', 'total_away_score', 'score_differential',
    # Players
    'passer_player_name', 'passer_player_id',
    'rusher_player_name', 'rusher_player_id',
    'receiver_player_name', 'receiver_player_id',
    # Advanced
    'epa', 'wpa', 'wp', 'def_wp',
    'cpoe', 'air_yards', 'yards_after_catch',
    'pass_length', 'pass_location',
    # Personnel & formation
    'offense_formation', 'offense_personnel', 'defense_personnel',
    'defenders_in_box', 'number_of_pass_rushers',
    # NGS (when joined via participation)
    'ngs_air_yards', 'time_to_throw', 'was_pressure', 'route',
    # Situational
    'no_huddle', 'qb_scramble', 'shotgun', 'no_score_prob',
    'home_wp', 'away_wp',
]
```

## Key Architecture Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Extend NFLDataFetcher vs new class | Extend existing class | Same pattern, same responsibility (thin wrapper); no benefit to splitting |
| Registry pattern vs if/elif chain | Registry pattern | 20+ data types makes if/elif unmaintainable |
| Season-level vs week-level partitioning | Season-level for all new types | Source data is season-level; week filtering at read time |
| Full PBP columns vs subset | Start with ~80 column subset | 300+ columns is overkill; expand as needed |
| Separate PFR methods per s_type | Single method with s_type parameter | Avoid code duplication |
| Batch ingestion mode | Add --batch flag alongside per-type | Enables full-season bootstrap while keeping granular control |
| Local-first storage | Maintain existing pattern | AWS credentials expired; local works fine for development |
| PBP caching strategy | Use nfl-data-py cache_pbp() for local dev | Avoids re-downloading 50-100 MB files on each run |

## Sources

- nfl-data-py source code: `/Users/georgesmith/repos/nfl_data_engineering/venv/lib/python3.9/site-packages/nfl_data_py/__init__.py` (verified all function signatures, parameters, and minimum year constraints) -- **HIGH confidence**
- Existing codebase: `src/nfl_data_integration.py`, `src/config.py`, `scripts/bronze_ingestion_simple.py` -- **HIGH confidence**
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) and [nfl-data-py GitHub](https://github.com/nflverse/nfl_data_py) -- **HIGH confidence**
- Storage estimates: Based on nflverse GitHub release file sizes and typical NFL season data volumes -- **MEDIUM confidence** (actual sizes may vary by season)

---

*Architecture analysis: 2026-03-08*
