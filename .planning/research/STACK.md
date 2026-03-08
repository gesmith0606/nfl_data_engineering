# Technology Stack: Bronze Layer Expansion for Game Predictions

**Project:** NFL Data Engineering Platform - Game Prediction Data Sources
**Researched:** 2026-03-08
**Source:** nfl-data-py v0.3.3 source code (read from local venv), nflverse documentation, web research

## Current State

NFLDataFetcher currently implements 8 methods using 7 nfl-data-py functions:

| Method | nfl-data-py Function | Data Type |
|--------|---------------------|-----------|
| `fetch_game_schedules` | `import_schedules` | Game schedules |
| `fetch_play_by_play` | `import_pbp_data` | PBP (limited columns) |
| `fetch_team_stats` | `import_team_desc` + `import_seasonal_data` | Team info |
| `fetch_player_weekly` | `import_weekly_data` | Weekly player stats |
| `fetch_snap_counts` | `import_snap_counts` | Snap counts |
| `fetch_injuries` | `import_injuries` | Injury reports |
| `fetch_rosters` | `import_seasonal_rosters` | Rosters |
| `fetch_player_seasonal` | `import_seasonal_data` | Seasonal aggregates |

**Gap:** `fetch_play_by_play` exists but only fetches 12 columns. The full PBP dataset has 300+ columns including EPA, WPA, CPOE -- the core analytics needed for game prediction.

## New Functions to Add

### Tier 1: Critical for Game Prediction (add first)

#### 1. Full Play-by-Play (enhance existing `fetch_play_by_play`)

**Function:** `import_pbp_data(years, columns=None, include_participation=True, downcast=True, cache=False, alt_path=None, thread_requests=False)`
**Available:** 1999-present
**Confidence:** HIGH (read source code directly)

**What to change:** Remove the default column restriction in the existing `fetch_play_by_play`. Currently hardcodes 12 columns; should pass `columns=None` to get all 300+.

**Key columns for game prediction:**
- `epa` -- Expected Points Added per play (THE core advanced metric)
- `wpa` -- Win Probability Added per play
- `cpoe` -- Completion Percentage Over Expected
- `air_epa`, `yac_epa` -- EPA split by air yards vs yards after catch
- `air_wpa`, `yac_wpa` -- WPA split similarly
- `comp_air_epa`, `comp_yac_epa` -- EPA on completions
- `cp` -- Completion probability model output
- `success` -- Binary success indicator (EPA > 0)
- `qb_epa` -- EPA attributed to the QB
- `ep`, `wp` -- Expected Points and Win Probability at play start
- `score_differential` -- Point differential at time of play
- `rushing_yards`, `passing_yards`, `yards_gained`
- `shotgun`, `no_huddle`, `qb_dropback`, `qb_scramble`
- `pass_location` (left/middle/right), `run_location`, `run_gap`
- `interception`, `fumble`, `sack`
- `penalty`, `penalty_yards`
- `roof`, `surface`, `temp`, `wind` -- Weather/venue data
- `home_wp`, `away_wp` -- Win probability for each team
- `result` -- Play outcome yards
- `series_success` -- Whether drive converted
- `passer_player_id`, `rusher_player_id`, `receiver_player_id` -- Player IDs for joining

**Data volume:** ~50K plays per season. Parquet ~25-30 MB per season (compressed). 6 seasons (2020-2025) = ~150-180 MB on disk. In-memory with downcast: ~800 MB per season, ~5 GB for 6 seasons.
**Quirk:** `include_participation=True` merges a separate participation dataset (available 2016+). This adds ~15 columns but increases file size. Can be disabled.
**Quirk:** The function prints `"YYYY done."` to stdout for each year -- not logged, just printed.
**Quirk:** `downcast=True` converts float64 to float32, saving ~30% memory. Keep this on.
**Quirk:** `thread_requests=True` parallelizes downloads across years. Use this for multi-year fetches.
**Quirk:** `cache=True` with `alt_path` lets you cache PBP locally via `cache_pbp()`. Recommend using this for the local-first workflow instead of re-downloading each time.

**Recommendation:** Do NOT store full PBP as a single parquet per season in Bronze. Instead, define a curated column list (~80 columns) relevant to game prediction. Store per season/week as with other Bronze data. Full 300+ columns has diminishing returns and bloats storage.

#### 2. Betting Lines (`import_sc_lines`)

**Function:** `import_sc_lines(years=None)`
**Source:** `https://raw.githubusercontent.com/nflverse/nfldata/master/data/sc_lines.csv`
**Available:** Varies (CSV-based, maintained by nflverse community)
**Confidence:** HIGH (read source code directly)

**Key columns (expected based on nflverse conventions):**
- `season`, `week`, `game_id` -- Join keys
- `spread_line` -- Point spread
- `total_line` -- Over/under total
- `moneyline_home`, `moneyline_away` -- Moneyline odds
- `home_team`, `away_team` -- Team identifiers

**Data volume:** ~270 games/season x 6 seasons = ~1,600 rows. Tiny (<1 MB).
**Quirk:** CSV-based (not parquet). Loaded from a single CSV covering all years, then filtered.
**Quirk:** Warning in `import_win_totals` says "data source is currently in flux and may be out of date." The `import_sc_lines` does NOT have this warning, but both pull from the same nflverse/nfldata repo. Verify freshness of data before relying on it.

**Note:** PBP data already contains `spread_line`, `total_line`, and implied totals per game. The `import_sc_lines` may provide additional granularity (opening vs closing lines) but overlaps significantly with PBP schedule data. Evaluate whether PBP spread/total columns are sufficient before adding a separate sc_lines ingestion.

#### 3. Next Gen Stats (`import_ngs_data`)

**Function:** `import_ngs_data(stat_type, years=None)`
**stat_type:** `'passing'`, `'rushing'`, `'receiving'` (required, one at a time)
**Source:** `https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_{stat_type}.parquet`
**Available:** 2016-present (AWS tracking data era)
**Confidence:** HIGH (read source code directly)

**Key columns by stat_type:**

*Passing:*
- `avg_time_to_throw` -- Seconds from snap to throw
- `avg_completed_air_yards` -- Air yards on completions
- `avg_intended_air_yards` -- Air yards on all attempts
- `avg_air_yards_differential` -- Intended minus completed
- `aggressiveness` -- Percentage of throws into tight windows
- `max_completed_air_distance` -- Longest completion
- `avg_air_yards_to_sticks` -- Air yards relative to first down marker
- `passer_rating` -- Traditional passer rating
- `completion_percentage`, `expected_completion_percentage` -- Actual vs expected
- `completion_percentage_above_expectation` -- CPOE equivalent

*Rushing:*
- `efficiency` -- Yards per carry adjusted
- `avg_rush_yards` -- Average rush yards
- `rush_yards_over_expected` -- RYOE (key advanced rushing metric)
- `rush_yards_over_expected_per_att` -- RYOE per attempt
- `rush_pct_over_expected` -- Percentage above expected
- `avg_time_to_los` -- Time to reach line of scrimmage

*Receiving:*
- `avg_cushion` -- Distance between WR and CB at snap
- `avg_separation` -- Distance at throw point
- `avg_intended_air_yards` -- Target depth
- `catch_percentage` -- Catch rate
- `avg_yac` -- Yards after catch
- `avg_expected_yac` -- Expected YAC
- `avg_yac_above_expectation` -- YAC over expected

**Data volume:** ~300-500 rows per stat_type per season (qualified players only). ~3 calls x 6 seasons = 18 fetches. Total <5 MB.
**Quirk:** Data is aggregated at the season level by default (NOT weekly). The parquet file contains seasonal aggregates per player. If weekly NGS is needed, it is NOT available through this function.
**Quirk:** The function downloads one monolithic parquet file per stat_type covering ALL seasons, then filters. Even requesting one year downloads the full file.

#### 4. PFR Advanced Stats (`import_seasonal_pfr` / `import_weekly_pfr`)

**Function:** `import_seasonal_pfr(s_type, years=None)` and `import_weekly_pfr(s_type, years=None)`
**s_type:** `'pass'`, `'rec'`, `'rush'`, `'def'` (required)
**Available:** 2018-present only
**Confidence:** HIGH (read source code directly)

**Key columns by s_type:**

*pass:*
- `passing_drops`, `passing_drop_pct` -- Drops by receivers
- `passing_bad_throws`, `passing_bad_throw_pct` -- Inaccurate throws
- `times_sacked`, `times_blitzed`, `times_hurried`, `times_hit`, `times_pressured`
- `times_pressured_pct` -- Pressure rate
- `pocket_time` -- Average time in pocket

*rec:*
- `receiving_drop`, `receiving_drop_pct` -- Receiver drops
- `receiving_broken_tackles` -- Broken tackles after catch
- `receiving_yards_after_contact` -- Contact yards

*rush:*
- `rushing_broken_tackles` -- Broken tackles
- `rushing_yards_before_contact`, `rushing_yards_after_contact`

*def:*
- `def_times_blitzed`, `def_times_hurried`, `def_times_hitqb`
- `def_pressures`, `def_tackles_combined`, `def_missed_tackles`
- `def_interceptions`

**Data volume:** Seasonal: ~200-400 rows per s_type. Weekly: ~200-400 rows per s_type per year. 4 s_types x 6 years (weekly) = 24 fetches. Total <20 MB.
**Quirk:** `import_weekly_pfr` with no years arg calls `import_seasonal_pfr` to discover available seasons, then iterates. This means an empty years call downloads seasonal data FIRST, then all weekly files. Always pass explicit years.
**Quirk:** Minimum year is 2018, enforced in `__validate_pfr_inputs`. Requesting earlier years raises ValueError.
**Quirk:** Seasonal downloads one monolithic parquet and filters. Weekly downloads one parquet per year per s_type.

### Tier 2: Valuable Context (add second)

#### 5. Depth Charts (`import_depth_charts`)

**Function:** `import_depth_charts(years)`
**Available:** 2001-present
**Confidence:** HIGH (read source code directly)

**Key columns (expected):**
- `season`, `week`, `club_code` -- Join keys
- `position`, `full_name`, `depth_team` -- Position and depth
- `jersey_number`, `gsis_id` -- Player identification

**Data volume:** ~32 teams x 53 roster spots x ~20 weeks x 6 seasons = significant rows. Estimate 50-100K rows per season. Parquet per year. Total ~10-20 MB.
**Quirk:** Minimum year is 2001, enforced in source code.
**Quirk:** Downloads one parquet per year, concatenated. For 6 seasons, 6 HTTP requests.

**Value for prediction:** Depth chart position indicates starter vs backup. Useful for identifying personnel changes week-to-week that impact team performance.

#### 6. Draft Picks (`import_draft_picks`)

**Function:** `import_draft_picks(years=None)`
**Source:** Single parquet file covering all years, filtered by season.
**Available:** Historical (likely 1970s-present)
**Confidence:** HIGH (read source code directly)

**Key columns (expected based on nflverse conventions):**
- `season`, `round`, `pick`, `team` -- Draft position
- `player_name`, `position`, `college` -- Player info
- `age` -- Age at draft
- `pfr_player_id`, `gsis_id` -- Player IDs for joining
- `draft_value` -- Assigned value

**Data volume:** ~260 picks/year. Single monolithic parquet, filtered. <5 MB total.
**Value for prediction:** Draft capital correlates with playing time, especially for rookies. Combine with depth charts for rookie impact assessment.

#### 7. Combine Data (`import_combine_data`)

**Function:** `import_combine_data(years=None, positions=None)`
**Source:** Single parquet covering all years.
**Available:** Historical
**Confidence:** HIGH (read source code directly)

**Key columns:**
- `season`, `player_name`, `pos`, `school` -- Identification
- `ht`, `wt` -- Height, weight
- `forty`, `bench`, `vertical`, `broad_jump` -- Athletic testing
- `cone`, `shuttle` -- Agility drills
- `pfr_player_id` -- Join key

**Data volume:** ~300 players/year. Single parquet. <5 MB total.
**Quirk:** Accepts both `years` and `positions` as filters. Both optional.
**Value for prediction:** Athletic profiles for player evaluation. Most useful at Silver/Gold layer for building player archetypes.

#### 8. QBR (`import_qbr`)

**Function:** `import_qbr(years=None, level='nfl', frequency='season')`
**level:** `'nfl'` or `'college'`
**frequency:** `'season'` or `'weekly'`
**Source:** ESPN's espnscrapeR-data repo (CSV)
**Available:** 2006-present
**Confidence:** HIGH (read source code directly)

**Key columns (expected):**
- `season`, `player_name`, `team` -- Identification
- `qbr_total` -- Total QBR (ESPN's proprietary metric)
- `pts_added` -- Points added above average
- `qb_plays` -- Number of plays

**Data volume:** ~40-60 QBs per season. Tiny. <1 MB.
**Quirk:** Minimum year 2006. CSV-based (not parquet).
**Quirk:** `frequency='weekly'` gives weekly QBR which is more useful for game prediction.
**Value for prediction:** ESPN's QBR is a holistic QB evaluation metric. Complements EPA/play from PBP.

#### 9. Officials (`import_officials`)

**Function:** `import_officials(years=None)`
**Source:** `https://raw.githubusercontent.com/nflverse/nfldata/master/data/officials.csv`
**Available:** Historical
**Confidence:** HIGH (read source code directly)

**Key columns:**
- `game_id`, `season` -- Join keys
- Official names/positions (referee, umpire, etc.)

**Data volume:** One CSV covering all years. <5 MB.
**Quirk:** CSV-based. Derives `season` from `game_id` string parsing.
**Value for prediction:** Referee crews have measurable tendencies (penalty rates, holding calls). Niche but useful as a feature.

### Tier 3: Nice to Have (add last)

#### 10. Win Totals (`import_win_totals`)

**Function:** `import_win_totals(years=None)`
**Source:** `https://raw.githubusercontent.com/mrcaseb/nfl-data/master/data/nfl_lines_odds.csv.gz`
**Confidence:** MEDIUM

**Data volume:** ~32 teams/season. Tiny.
**Quirk:** WARNING in source code: "The win totals data source is currently in flux and may be out of date." This is a reliability concern.
**Quirk:** Derives `season` from `game_id` string parsing, filters to non-null game_ids.
**Value for prediction:** Preseason win totals reflect market expectations. Useful as a prior for team strength but not critical if you have weekly betting lines.

#### 11. FTN Charting Data (`import_ftn_data`)

**Function:** `import_ftn_data(years, columns=None, downcast=True, thread_requests=False)`
**Available:** 2022-present ONLY
**Confidence:** HIGH (read source code directly)

**Key columns:**
- `is_play_action`, `is_trick_play`, `is_qb_out_of_pocket`
- `is_throw_away`, `is_catchable`, `is_contested`
- `is_qb_sneak`, `is_blitz`, `is_no_huddle`
- QB location, pass rush details

**Data volume:** ~50K plays/season, 3 available seasons. ~15 MB per season.
**Quirk:** CC-BY-SA 4.0 license. Must attribute "FTN Data via nflverse."
**Quirk:** Only 3-4 seasons of data (2022+). Too short for robust historical modeling.
**Value for prediction:** Rich play-level charting. Excellent for scheme analysis but limited history reduces ML training value.

#### 12. Contracts (`import_contracts`)

**Function:** `import_contracts()`
**Source:** Single parquet file.
**No parameters** -- returns all historical contract data.
**Confidence:** HIGH (read source code directly)

**Value for prediction:** Low direct value for game prediction. Useful for roster construction analysis.

#### 13. Player IDs (`import_ids`)

**Function:** `import_ids(columns=None, ids=None)`
**Source:** dynastyprocess player ID mapping CSV.
**Confidence:** HIGH (read source code directly)

**Value:** Cross-reference players across data sources (PFR, ESPN, Sleeper, etc.). Essential utility function, not a data source per se.

#### 14. Players (`import_players`)

**Function:** `import_players()`
**Source:** Single parquet with all player descriptive data.
**Confidence:** HIGH (read source code directly)

**Value:** Height, weight, age, draft info for all players. Useful reference table.

#### 15. Draft Values (`import_draft_values`)

**Function:** `import_draft_values(picks=None)`
**Source:** CSV with draft pick valuation models.
**Confidence:** HIGH (read source code directly)

**Value for prediction:** Trade value charts. Minimal game prediction value.

## Functions NOT in nfl-data-py

Things you might expect but are NOT available:

| Data | Status | Alternative |
|------|--------|-------------|
| Real-time scores | Not available | ESPN API, Sleeper API |
| Weather (detailed) | Partial (in PBP: temp, wind, roof) | Weather API services |
| Coaching staff | Not available | Manual maintenance or PFR scraping |
| Stadium data | Partial (in schedules/PBP) | nflverse team_desc has stadium info |
| Player tracking (raw) | Not available (NGS is aggregated) | NFL's Big Data Bowl datasets (Kaggle) |
| Salary cap data | `import_contracts` has contracts | OverTheCap scraping for cap space |

## Data Source Reliability Assessment

| Function | Source Format | Update Frequency | Reliability |
|----------|-------------|------------------|-------------|
| `import_pbp_data` | Parquet (GitHub releases) | Within days of games | HIGH |
| `import_ngs_data` | Parquet (GitHub releases) | Weekly during season | HIGH |
| `import_seasonal_pfr` | Parquet (GitHub releases) | End of season | HIGH |
| `import_weekly_pfr` | Parquet (GitHub releases) | Weekly during season | HIGH |
| `import_sc_lines` | CSV (nfldata repo) | Unknown cadence | MEDIUM |
| `import_win_totals` | CSV.gz (mrcaseb repo) | Explicitly flagged as unstable | LOW |
| `import_depth_charts` | Parquet (GitHub releases) | Weekly during season | HIGH |
| `import_draft_picks` | Parquet (GitHub releases) | After each draft | HIGH |
| `import_combine_data` | Parquet (GitHub releases) | After each combine | HIGH |
| `import_qbr` | CSV (espnscrapeR-data) | Weekly during season | MEDIUM |
| `import_officials` | CSV (nfldata repo) | After each game | MEDIUM |
| `import_ftn_data` | Parquet (GitHub releases) | Weekly (48hr delay) | HIGH |

## Recommended Ingestion Priority

### Phase 1: Core Game Prediction Data
1. **Full PBP** -- Enhance existing method, remove column restriction, add `cache=True` support
2. **NGS passing/rushing/receiving** -- 3 new fetch methods (one per stat_type)
3. **PFR weekly (pass, rush, rec, def)** -- 4 new fetch methods or 1 parameterized method
4. **Betting lines (sc_lines)** -- Verify overlap with PBP spread/total first

### Phase 2: Contextual Data
5. **Depth charts** -- Starter identification
6. **QBR weekly** -- QB evaluation metric
7. **Draft picks** -- Rookie context
8. **Combine data** -- Athletic profiles

### Phase 3: Supplementary
9. **Officials** -- Referee tendencies
10. **FTN charting** -- Scheme analysis (2022+ only)
11. **Win totals** -- Only if data source stabilizes

### Do Not Add
- `import_contracts` -- Not relevant to game prediction
- `import_draft_values` -- Not relevant to game prediction
- `import_ids` -- Use as utility, not as ingested Bronze data
- `import_players` -- Use as utility/reference table, not weekly ingestion

## Implementation Notes

### Fetcher Method Design

Each new method should follow the established pattern in `nfl_data_integration.py`:
1. Validate seasons/years input
2. Call nfl-data-py function
3. Filter by week if applicable
4. Add `data_source` and `ingestion_timestamp` metadata columns
5. Return DataFrame

### Bronze Ingestion CLI Extensions

`bronze_ingestion_simple.py` needs new `--data-type` values:
- `pbp_full` (distinguish from existing limited `pbp`)
- `ngs_passing`, `ngs_rushing`, `ngs_receiving`
- `pfr_pass`, `pfr_rec`, `pfr_rush`, `pfr_def` (weekly)
- `pfr_seasonal_pass`, `pfr_seasonal_rec`, `pfr_seasonal_rush`, `pfr_seasonal_def`
- `sc_lines`
- `depth_charts`
- `qbr`
- `draft_picks`
- `combine`
- `officials`

### S3/Local Key Patterns

New keys for `config.py` PLAYER_S3_KEYS:
```python
PREDICTION_S3_KEYS = {
    "pbp_full": "plays/pbp/season={season}/week={week}/pbp_{ts}.parquet",
    "ngs_passing": "ngs/passing/season={season}/ngs_passing_{ts}.parquet",
    "ngs_rushing": "ngs/rushing/season={season}/ngs_rushing_{ts}.parquet",
    "ngs_receiving": "ngs/receiving/season={season}/ngs_receiving_{ts}.parquet",
    "pfr_weekly_pass": "pfr/weekly/pass/season={season}/week={week}/pfr_pass_{ts}.parquet",
    "pfr_weekly_rec": "pfr/weekly/rec/season={season}/week={week}/pfr_rec_{ts}.parquet",
    "pfr_weekly_rush": "pfr/weekly/rush/season={season}/week={week}/pfr_rush_{ts}.parquet",
    "pfr_weekly_def": "pfr/weekly/def/season={season}/week={week}/pfr_def_{ts}.parquet",
    "pfr_seasonal": "pfr/seasonal/{s_type}/season={season}/pfr_seasonal_{ts}.parquet",
    "sc_lines": "betting/lines/season={season}/week={week}/sc_lines_{ts}.parquet",
    "depth_charts": "depth_charts/season={season}/week={week}/depth_charts_{ts}.parquet",
    "qbr": "qbr/season={season}/qbr_{ts}.parquet",
    "draft_picks": "draft/picks/season={season}/draft_picks_{ts}.parquet",
    "combine": "draft/combine/season={season}/combine_{ts}.parquet",
    "officials": "officials/season={season}/officials_{ts}.parquet",
}
```

### Memory Management

Full PBP is the biggest concern. For 6 seasons loaded simultaneously:
- With `downcast=True`: ~800 MB per season, ~5 GB total
- Recommendation: Process one season at a time, or use column selection
- The `cache_pbp()` function can pre-cache locally, avoiding repeated downloads
- For Bronze ingestion, download per-season and write immediately to local parquet

### Validation Extensions

`validate_data()` needs new entries in `required_columns`:
```python
'pbp_full': ['game_id', 'play_id', 'season', 'week', 'epa', 'wpa'],
'ngs': ['season', 'player_display_name'],
'pfr_weekly': ['season', 'week', 'pfr_player_id'],
'pfr_seasonal': ['season', 'pfr_player_id'],
'sc_lines': ['season', 'game_id'],
'depth_charts': ['season', 'week', 'club_code'],
'qbr': ['season'],
'draft_picks': ['season', 'round', 'pick'],
'combine': ['season', 'pos'],
'officials': ['game_id', 'season'],
```

## Sources

- nfl-data-py source code v0.3.3 (read directly from `/Users/georgesmith/repos/nfl_data_engineering/venv/lib/python3.9/site-packages/nfl_data_py/__init__.py`) -- PRIMARY SOURCE, HIGH confidence
- [nfl-data-py GitHub](https://github.com/nflverse/nfl_data_py) -- Repository documentation
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- Package metadata
- [nflreadr NGS Data Dictionary](https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html) -- NGS column reference
- [nflreadr PFR Advanced Stats](https://nflreadr.nflverse.com/reference/load_pfr_advstats.html) -- PFR column reference
- [nflfastR PBP Reference](https://nflfastr.com/reference/fast_scraper.html) -- PBP column reference
- [nflverse Data Repository](https://github.com/nflverse/nfldata/blob/master/DATASETS.md) -- Dataset catalog
