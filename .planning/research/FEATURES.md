# Feature Landscape

**Domain:** Bronze layer backfill for 9 new NFL data types across 10 years (2016-2025)
**Researched:** 2026-03-08
**Confidence:** HIGH (all features verified against existing codebase, config, adapter, and data dictionary)

## Table Stakes

Features users expect. Missing = backfill feels incomplete.

### Tier 1: Core Ingestion (9 New Data Types)

| Feature | Why Expected | Complexity | Dependencies |
|---------|--------------|------------|--------------|
| PBP ingestion (2016-2025) | Foundation for game prediction ML; 103 curated columns already defined in `PBP_COLUMNS` | High | Memory-safe single-season loop (already built), `downcast=True`, `include_participation=False` |
| NGS passing/rushing/receiving (2016-2025) | Tracking data is the gold standard for player evaluation; 3 sub-types | Medium | `--sub-type` dispatch already in registry; each sub-type is a separate fetch call |
| PFR weekly pass/rush/rec/def (2018-2025) | Advanced box-score metrics (pressures, broken tackles); 4 sub-types | Medium | `--sub-type` dispatch already in registry; uses `pfr_player_id` (not GSIS) |
| PFR seasonal pass/rush/rec/def (2018-2025) | Season aggregates for baseline comparisons; 4 sub-types | Medium | Same sub-type dispatch; uses `pfr_id` (different key name from weekly) |
| QBR weekly + seasonal (2016-2025) | ESPN's proprietary QB metric; already has `--frequency` flag | Low | `--frequency weekly/seasonal` already in CLI; filename prefix prevents collisions |
| Depth charts (2016-2025) | Starter/backup status drives projection multipliers | Low | Simple season-list fetch, no sub-types |
| Draft picks (2016-2025) | Player capital for rookie projections and trade analysis | Low | Simple season-list fetch, no sub-types |
| Combine (2016-2025) | Athletic testing for prospect evaluation | Low | Simple season-list fetch, no sub-types |
| Teams (static, one-time) | Reference data for all team lookups | Low | No season partitioning; `requires_season=False` |

### Tier 2: Batch Ingestion Infrastructure

| Feature | Why Expected | Complexity | Dependencies |
|---------|--------------|------------|--------------|
| `--seasons 2016-2025` range flag works for all 9 types | Backfilling one season at a time is unusable | Already built | `parse_seasons_range()` + season-by-season loop exist in CLI |
| Season range validation per data type | NGS starts 2016, PFR starts 2018, QBR starts 2006 -- invalid seasons must be rejected cleanly | Already built | `validate_season_for_type()` + `DATA_TYPE_SEASON_RANGES` in config.py |
| Sub-type iteration for NGS/PFR | Must ingest all 3 NGS sub-types and all 4 PFR sub-types without manual repetition | Low | Add `--all-sub-types` flag or loop wrapper; currently requires separate CLI invocations |
| Validation for all 9 types | `validate_data()` must check required columns for each type | Already built | All 9 types have `required_columns` entries in `nfl_data_integration.py` |
| Progress reporting for multi-season batch | "Ingesting season 2020... (5/10)" feedback | Already built | Season loop in `main()` already prints progress |

### Tier 3: Existing Type Backfill (6 Types, Extended Range)

| Feature | Why Expected | Complexity | Dependencies |
|---------|--------------|------------|--------------|
| Schedules backfill to 2016 | Currently have 2020-2025; need 2016-2019 | Low | Same `--seasons 2016-2019` flag, same adapter |
| Player weekly backfill to 2016 | Currently have 2020-2024; need 2016-2019 + 2025 | Low | Same adapter; weekly fetch returns all weeks for a season |
| Player seasonal backfill to 2016 | Currently have 2020-2024; need 2016-2019 + 2025 | Low | Same adapter |
| Snap counts backfill to 2016 | Currently have 2020-2024; need 2016-2019 + 2025; starts at 2012 | Medium | Uses positional `(season, week)` -- needs all-weeks iteration or accept full-season fetch |
| Injuries backfill to 2016 | Currently have 2020-2024; need 2016-2019 + 2025; starts at 2009 | Low | Same adapter |
| Rosters backfill to 2016 | Currently have 2020-2024; need 2016-2019 + 2025 | Low | Same adapter; uses `import_seasonal_rosters` |

## Differentiators

Features that add value beyond basic backfill. Not expected, but improve the platform.

| Feature | Value Proposition | Complexity | Dependencies |
|---------|-------------------|------------|--------------|
| `--all-sub-types` flag | Single command ingests all NGS sub-types or all PFR sub-types: `--data-type ngs --all-sub-types --seasons 2016-2025` instead of 3 separate runs | Low | Loop over `entry["sub_types"]` list in registry |
| QBR both-frequencies mode | `--frequency both` ingests weekly AND seasonal QBR in one pass | Low | Loop over `["weekly", "seasonal"]` when frequency="both" |
| Backfill manifest/report | After batch run, print summary: seasons ingested, row counts, file sizes, validation pass/fail per type | Medium | Accumulate stats during season loop, print at end |
| Idempotent re-ingestion | Skip seasons that already have local Parquet files (unless `--force` flag) | Medium | Check `os.path.exists()` on expected local path before fetching |
| Parallel sub-type ingestion | Fetch NGS passing/rushing/receiving concurrently within a season | Medium | `concurrent.futures.ThreadPoolExecutor`; nfl-data-py HTTP calls are I/O-bound |
| Backfill orchestration script | Single `scripts/backfill_all.py` that ingests all 15 types in dependency order | Medium | Wrapper calling existing CLI; teams first (no season), then season-partitioned types |
| Data freshness check | Verify 2025 data is actually current-season complete (not partial mid-season) | Low | Check max week in fetched data vs expected 18 weeks for completed 2025 season |
| Disk space estimation | Before backfill, estimate total disk usage from known per-season sizes | Low | PBP is ~150MB/season; others are <5MB/season; print warning before proceeding |

## Anti-Features

Features to explicitly NOT build during this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| S3 upload during backfill | AWS credentials are expired; local-first workflow is active | Keep `--s3` flag but default to off; fix S3 sync in a separate milestone |
| Silver/Gold processing of new types | This milestone is Bronze-only; Silver transformations need new analytics code | Defer to next milestone; Bronze data is self-contained and useful on its own |
| Week-level partitioning for seasonal data | PFR seasonal, player seasonal, combine, draft picks are season-level data | Store as `season=YYYY/` only; do not force week partitioning on non-weekly data |
| Custom column selection for NGS/PFR/QBR | Unlike PBP (which curates 103 of 300+ columns), these types have manageable column counts | Ingest all columns; filter at Silver layer if needed |
| Real-time / incremental ingestion | Backfill is a one-time batch operation for historical data | Use `--seasons` range for batch; weekly pipeline handles incremental during season |
| Rate limiting / retry logic for nfl-data-py | The library handles its own HTTP retries internally | Let nfl-data-py manage retries; adapter's `_safe_call` catches exceptions |
| Schema evolution tracking | Column sets are stable across seasons for these data types | Accept whatever nfl-data-py returns; validate required columns only |

## Feature Dependencies

```
Teams (static, no season) -- ingest first, reference data for all other types

Schedules (2016-2025)
  |
  v
PBP (2016-2025) -- depends on schedules for game_id context
  |
  v
NGS (2016-2025) -- supplements PBP with tracking data
PFR weekly (2018-2025) -- supplements PBP with advanced box-score
PFR seasonal (2018-2025) -- seasonal aggregates of PFR weekly
QBR (2016-2025) -- QB-specific overlay on PBP

Depth charts (2016-2025) -- independent, feeds projection engine
Draft picks (2016-2025) -- independent, feeds prospect evaluation
Combine (2016-2025) -- independent, feeds prospect evaluation

Rosters (2016-2025) -- independent, but links player IDs across sources
Player weekly (2016-2025) -- independent
Player seasonal (2016-2025) -- independent
Snap counts (2016-2025) -- independent
Injuries (2016-2025) -- independent
```

Note: Dependencies above are logical (what makes sense to have first), not technical blockers. Each data type can be ingested independently because the Bronze layer is raw storage with no cross-type joins.

## Sub-Type Handling Details

### NGS: 3 Sub-Types

| Sub-Type | `--sub-type` Value | Adapter Kwarg | Season Range | Notes |
|----------|--------------------|---------------|-------------|-------|
| Passing | `passing` | `stat_type="passing"` | 2016-2025 | ~20 passing-specific columns (time_to_throw, aggressiveness, etc.) |
| Rushing | `rushing` | `stat_type="rushing"` | 2016-2025 | ~12 rushing-specific columns (RYOE, time_to_LOS, etc.) |
| Receiving | `receiving` | `stat_type="receiving"` | 2016-2025 | ~13 receiving-specific columns (separation, cushion, YAC over expected) |

Each sub-type writes to a separate path: `data/bronze/ngs/{sub_type}/season=YYYY/`. 10 seasons x 3 sub-types = 30 ingestion operations.

### PFR: 4 Sub-Types x 2 Frequencies = 8 Logical Types

| Frequency | Sub-Type | `--sub-type` Value | Adapter Kwarg | Season Range | Notes |
|-----------|----------|--------------------|---------------|-------------|-------|
| Weekly | Passing | `pass` | `s_type="pass"` | 2018-2025 | Uses `pfr_player_name` / `pfr_player_id` |
| Weekly | Rushing | `rush` | `s_type="rush"` | 2018-2025 | Same ID columns as passing |
| Weekly | Receiving | `rec` | `s_type="rec"` | 2018-2025 | Same ID columns as passing |
| Weekly | Defense | `def` | `s_type="def"` | 2018-2025 | Same ID columns as passing |
| Seasonal | Passing | `pass` | `s_type="pass"` | 2018-2025 | Uses `player` / `pfr_id` (DIFFERENT from weekly) |
| Seasonal | Rushing | `rush` | `s_type="rush"` | 2018-2025 | Same as seasonal passing |
| Seasonal | Receiving | `rec` | `s_type="rec"` | 2018-2025 | Same as seasonal passing |
| Seasonal | Defense | `def` | `s_type="def"` | 2018-2025 | Same as seasonal passing |

PFR weekly: 8 seasons x 4 sub-types = 32 ingestion operations.
PFR seasonal: 8 seasons x 4 sub-types = 32 ingestion operations.

### QBR: 2 Frequencies (Not Sub-Types)

| Frequency | `--frequency` Value | Filename Prefix | Season Range | Notes |
|-----------|---------------------|-----------------|-------------|-------|
| Weekly | `weekly` | `qbr_weekly_` | 2016-2025 | Per-game QBR |
| Seasonal | `seasonal` | `qbr_seasonal_` | 2016-2025 | Season aggregate |

Both frequencies write to the same path (`data/bronze/qbr/season=YYYY/`) but are differentiated by filename prefix. 10 seasons x 2 frequencies = 20 ingestion operations.

## Ingestion Operation Count Summary

| Data Type | Seasons | Sub-Types/Freq | Total Operations |
|-----------|---------|----------------|------------------|
| PBP | 10 (2016-2025) | 1 | 10 |
| NGS | 10 (2016-2025) | 3 | 30 |
| PFR weekly | 8 (2018-2025) | 4 | 32 |
| PFR seasonal | 8 (2018-2025) | 4 | 32 |
| QBR | 10 (2016-2025) | 2 | 20 |
| Depth charts | 10 (2016-2025) | 1 | 10 |
| Draft picks | 10 (2016-2025) | 1 | 10 |
| Combine | 10 (2016-2025) | 1 | 10 |
| Teams | 1 (static) | 1 | 1 |
| **Total new** | | | **155** |

For existing type backfill (4 additional seasons each for 2016-2019, plus 2025 for most):

| Data Type | Additional Seasons | Operations |
|-----------|--------------------|------------|
| Schedules | 4 (2016-2019) | 4 |
| Player weekly | 5 (2016-2019, 2025) | 5 |
| Player seasonal | 5 (2016-2019, 2025) | 5 |
| Snap counts | 5 (2016-2019, 2025) | 5 |
| Injuries | 5 (2016-2019, 2025) | 5 |
| Rosters | 5 (2016-2019, 2025) | 5 |
| **Total existing backfill** | | **29** |

**Grand total: ~184 ingestion operations.**

## 2025-2026 Data Freshness Considerations

| Data Type | 2025 Status | 2026 Status | Notes |
|-----------|-------------|-------------|-------|
| PBP | Full season available (W1-18 + playoffs) | Not started (season begins Sept 2026) | 2025 season completed Jan 2026 |
| NGS | Full 2025 season | No data until Sept 2026 | Tracking data published weekly during season |
| PFR weekly/seasonal | Full 2025 season | No data until Sept 2026 | PFR publishes after each game |
| QBR | Full 2025 season | No data until Sept 2026 | ESPN publishes after each game |
| Depth charts | Full 2025 season | Partial (offseason depth charts may exist) | Teams publish throughout offseason |
| Draft picks | Full through 2025 draft | 2026 draft is April 2026 -- available soon | Historical + upcoming |
| Combine | Full through 2025 combine | 2026 combine already happened (Feb 2026) | Should be available via nfl-data-py |
| Teams | Static, always current | Same | No season dependency |
| Schedules | Full 2025 | 2026 schedule not yet released | NFL schedule release is typically May |
| Player weekly/seasonal | Full 2025 | No data until Sept 2026 | Depends on games being played |
| Snap counts | Full 2025 | No data until Sept 2026 | Same as weekly |
| Injuries | Full 2025 | No data until Sept 2026 | Injury reports during season only |
| Rosters | Full 2025 | 2026 offseason rosters may be available | Free agency changes in March |

**Key insight:** The 2026 combine data may already be available. Worth attempting `--season 2026` for combine and draft picks. All other 2026 data requires the NFL season to begin (September 2026).

## Snap Counts Special Case

Snap counts is the only data type using positional `(season, week)` args instead of `seasons` list. The current CLI handles this, but backfill across 10 seasons x 18 weeks = 180 week-level operations per season is impractical.

**Investigation needed:** Does `nfl-data-py` `import_snap_counts(season, week)` accept `week=None` or `week=0` to fetch all weeks? If not, the adapter or CLI needs a week-iteration wrapper for snap count backfill. The existing data (2020-2024) uses week-level files, suggesting manual week-by-week ingestion was done previously.

**Recommendation:** Test whether the adapter can fetch all weeks at once. If not, add a `--all-weeks` flag that iterates weeks 1-18 for the given season(s). This is the highest-complexity backfill operation due to the week dimension.

## MVP Recommendation

Prioritize in this order:

1. **Teams (static)** -- one-time, zero complexity, reference data
2. **PBP (2016-2025)** -- highest value for ML; largest dataset (~150MB/season); validate memory safety first
3. **Schedules backfill (2016-2019)** -- completes the game context for PBP
4. **NGS (2016-2025, all 3 sub-types)** -- highest-value tracking data for player evaluation
5. **QBR (2016-2025, both frequencies)** -- low complexity, high value for QB analysis
6. **Depth charts (2016-2025)** -- feeds projection engine starter/backup logic
7. **Draft picks + Combine (2016-2025)** -- prospect data, lower priority for current prediction models
8. **PFR weekly + seasonal (2018-2025, all 4 sub-types each)** -- advanced metrics, but most operations (64 total)
9. **Existing type backfill (2016-2019, 2025)** -- extends history for types already working

**Defer:** `--all-sub-types` flag and `backfill_all.py` orchestration script are nice-to-haves. The existing CLI with `--seasons 2016-2025` works for manual execution. Add orchestration only if manual process proves too painful.

## Sources

- `src/config.py` -- DATA_TYPE_SEASON_RANGES, PBP_COLUMNS, validate_season_for_type
- `scripts/bronze_ingestion_simple.py` -- DATA_TYPE_REGISTRY, batch ingestion loop, sub-type handling
- `src/nfl_data_adapter.py` -- all 15 fetch method signatures and kwarg patterns
- `src/nfl_data_integration.py` -- validate_data() required columns for all 15 types
- `docs/NFL_DATA_DICTIONARY.md` -- full schema documentation for all Bronze types
- `.planning/PROJECT.md` -- v1.1 milestone context and constraints
