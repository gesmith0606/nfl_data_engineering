# Project Research Summary

**Project:** NFL Data Engineering v1.1 Bronze Backfill
**Domain:** Data engineering -- batch ingestion of 9 new NFL data types across 10 years (2016-2025) into existing medallion architecture
**Researched:** 2026-03-08
**Confidence:** HIGH

## Executive Summary

This milestone is a pure execution problem, not an architecture problem. The v1.0 codebase already contains every component needed to ingest all 9 new data types: `NFLDataAdapter` has all 15 fetch methods implemented, `DATA_TYPE_REGISTRY` has all entries registered, `DATA_TYPE_SEASON_RANGES` defines valid ranges, and `validate_data()` has required columns for all 15 schemas. No new dependencies, no new libraries, no architectural changes required. The existing stack (Python 3.9, pandas 1.5.3, nfl-data-py 0.3.3, pyarrow 21.0) handles everything. The total backfill is approximately 184 ingestion operations producing ~1-1.5 GB of Parquet files locally.

The recommended approach is to execute the backfill in a carefully ordered sequence: start with small, simple data types (teams, draft picks, combine) to validate the pipeline end-to-end, then progress to types with sub-type dispatch (NGS, PFR, QBR), and finish with PBP (the largest and slowest dataset at ~100 MB/season). Existing data types (schedules, player weekly, etc.) should be backfilled to 2016-2019 alongside or after the new types. A backfill orchestration script wrapping the existing CLI eliminates manual error across ~24 CLI invocations.

The primary risks are: (1) GitHub rate limiting during bulk downloads -- mitigated by setting `GITHUB_TOKEN` (for StatsPlayerAdapter and gh CLI; nfl-data-py itself does not use it) and adding inter-call delays, (2) nfl-data-py is archived with no future fixes -- mitigated by completing the backfill now while nflverse-data URLs are stable and keeping dependency pins strict, (3) known data source gaps -- injury data is dead after 2024 and depth chart schemas changed in 2025. These are well-understood and have clear workarounds.

## Key Findings

### Recommended Stack

No changes to the technology stack. See [STACK.md](./STACK.md) for full analysis.

**Core technologies (all existing, all staying):**
- **Python 3.9.7**: Runtime -- nflreadpy requires 3.10+, migration out of scope
- **pandas 1.5.3**: DataFrame processing -- all adapter methods return pandas; do not upgrade (2.0 breaks `DataFrame.append`)
- **nfl-data-py 0.3.3**: NFL data source -- archived but functional; all 9 APIs verified returning data on 2026-03-08
- **pyarrow 21.0.0**: Parquet serialization -- handles all read/write needs
- **numpy <2.0**: Must stay pinned -- nfl-data-py uses deprecated `np.float_`

**Critical version constraint:** `numpy<2` and `nfl-data-py==0.3.3` must remain pinned in requirements.txt. Any `pip install --upgrade` risks breaking the pipeline.

### Expected Features

See [FEATURES.md](./FEATURES.md) for full feature landscape including 184 enumerated ingestion operations.

**Must have (table stakes):**
- All 9 new data types ingested for 2016-2025 (PBP, NGS x3, PFR weekly x4, PFR seasonal x4, QBR x2, depth charts, draft picks, combine, teams)
- Existing 6 data types backfilled from 2020-2024 to 2016-2025 (schedules, player weekly/seasonal, snap counts, injuries, rosters)
- Season range validation per data type (NGS starts 2016, PFR starts 2018, injuries max 2024)
- Sub-type and frequency dispatch working for all NGS/PFR/QBR variants
- Validation (`validate_data()`) running on every ingested file

**Should have (differentiators):**
- `--all-sub-types` flag for single-command NGS/PFR ingestion
- Backfill manifest/report summarizing row counts and validation results per type
- Idempotent re-ingestion with `--force` skip logic
- Backfill orchestration script (`backfill_all.py`) for one-command full backfill

**Defer (not this milestone):**
- S3 upload (AWS credentials expired; local-first workflow)
- Silver/Gold processing of new data types (separate milestone)
- Schema evolution tracking (stable schemas at Bronze level)
- nflreadpy migration (requires Python 3.10+ and Polars rewrite)

### Architecture Approach

No new architecture needed. See [ARCHITECTURE.md](./ARCHITECTURE.md) for component boundaries and data flow.

**Major components (all existing):**
1. **`bronze_ingestion_simple.py`** -- CLI entry point with registry-dispatch pattern, per-season batch loop, sub-type/frequency routing
2. **`NFLDataAdapter`** -- Wraps all 15 nfl-data-py `import_*` calls with consistent error handling via `_safe_call`
3. **`config.py`** -- Season ranges, PBP column list (103 curated), S3 paths; single source of truth for data type metadata
4. **`NFLDataFetcher.validate_data()`** -- Schema validation (required columns, null checks) in warn-never-block mode

**Key patterns to follow:**
- Per-season batch loop (never load multiple PBP seasons simultaneously -- 163 MB/season in RAM)
- Sub-type iteration for NGS (3 types) and PFR (4 types per frequency)
- Frequency-prefixed filenames for QBR (weekly vs seasonal in same directory)
- Season-independent fetch for teams (no `--season` argument)

### Critical Pitfalls

See [PITFALLS.md](./PITFALLS.md) for all 12 pitfalls with recovery strategies.

1. **nfl-data-py is archived** -- Complete backfill now while nflverse-data URLs are stable; pin `numpy<2` and `nfl-data-py==0.3.3`; adapter pattern isolates all imports to one module
2. **GitHub rate limiting on bulk downloads** -- Set `GITHUB_TOKEN` for 5000/hr limit (vs 60/hr unauthenticated); add 1-2s delay between API calls; silent 403s look like "no data" via `_safe_call`
3. **Injury data source dead after 2024** -- Update `DATA_TYPE_SEASON_RANGES["injuries"]` max to static 2024; backfill 2016-2019 while historical API still works
4. **Depth chart schema change in 2025+** -- ISO timestamps replace week numbers; validate schema per season before storing
5. **PBP memory explosion** -- 163 MB per season in RAM; always use per-season loop, `columns=PBP_COLUMNS`, `include_participation=False`; add `gc.collect()` between seasons
6. **Snap counts unique (season, week) signature** -- Requires nested season x week loop (180 calls for 10 years); only data type needing week-level iteration

## Implications for Roadmap

Based on combined research, suggested phase structure:

### Phase 1: Pre-Backfill Setup and Guards
**Rationale:** Every pitfall research finding points to setup steps that must happen before any data fetching begins. Skipping these causes silent failures (rate limiting) or wasted effort (injury 404s).
**Delivers:** Rate limiting protection, dependency verification, disk space validation, config fixes
**Addresses:** `GITHUB_TOKEN` configuration, `numpy<2` pin verification, injury season range fix (`DATA_TYPE_SEASON_RANGES["injuries"]` max -> 2024), disk space check (~2 GB free needed)
**Avoids:** Pitfalls 1 (archived library breakage), 3 (injury 404s), 5 (rate limiting), 10 (disk exhaustion)

### Phase 2: Simple Data Types (Teams, Draft Picks, Combine, Depth Charts)
**Rationale:** Start with zero-complexity types to validate the pipeline end-to-end before investing time in complex sub-type dispatch. Teams has no season parameter. Draft picks and combine are small (~0.05 MB/season), season-only fetches. Depth charts are medium-size but straightforward. Finding bugs here is cheap.
**Delivers:** 4 new data types fully ingested (2016-2025), ~31 ingestion operations
**Addresses:** FEATURES.md table stakes tier 1 (core ingestion) and tier 2 (batch infrastructure validation)
**Avoids:** Pitfall 4 (depth chart schema change -- validate 2024 vs 2025 schema here)

### Phase 3: Sub-Type Data Types (NGS, PFR Weekly, PFR Seasonal, QBR)
**Rationale:** These types test sub-type dispatch and frequency routing -- the most complex ingestion patterns. NGS has 3 sub-types, PFR has 4 sub-types x 2 frequencies, QBR has 2 frequencies. This phase covers 94 of the 155 new ingestion operations and validates the hardest code paths.
**Delivers:** 4 data types with all sub-type/frequency variants fully ingested, ~94 ingestion operations
**Addresses:** FEATURES.md sub-type handling details, QBR dual frequency ingestion
**Avoids:** Pitfalls 7 (QBR filename collision), 8 (NGS availability window), 12 (NGS/PFR param name inconsistencies)

### Phase 4: PBP Backfill (2016-2025)
**Rationale:** PBP is the largest dataset (~100 MB/season, ~1 GB total) and slowest to download (~30s/season). Doing it last means all pipeline bugs are found and fixed on smaller types first. A failed PBP run wastes 5-10 minutes per season of re-download time.
**Delivers:** 10 seasons of play-by-play data with 103 curated columns, ~10 ingestion operations
**Addresses:** FEATURES.md highest-value data type for future ML work
**Avoids:** Pitfall 2 (memory explosion -- per-season loop + `gc.collect()` + `columns=PBP_COLUMNS`)

### Phase 5: Existing Type Backfill (2016-2019 + 2025)
**Rationale:** Extends 6 already-working data types from their current 2020-2024 range to 2016-2025. Lower risk since these adapter code paths are proven. Snap counts require special handling with week-level iteration.
**Delivers:** Complete 10-year coverage for all 15 Bronze data types, ~29 ingestion operations
**Addresses:** FEATURES.md tier 3 (existing type backfill)
**Avoids:** Pitfall 9 (snap counts unique `(season, week)` signature -- verify week loop works)

### Phase 6: Validation, Inventory, and Orchestration
**Rationale:** Post-backfill quality assurance. Regenerate inventory docs, run cross-type validation, optionally build orchestration script for repeatable re-runs.
**Delivers:** Updated `BRONZE_LAYER_DATA_INVENTORY.md`, backfill summary report with row counts per type/season, optional `backfill_all.py` script
**Addresses:** FEATURES.md differentiators (manifest/report, idempotent re-ingestion)
**Avoids:** Pitfall 6 (schema drift -- cross-year schema comparison validates consistency)

### Phase Ordering Rationale

- **Setup before execution:** Rate limiting and dependency pins prevent silent failures that waste hours of backfill time
- **Small before large:** Finding bugs on draft picks (0.05 MB/season) is 2000x cheaper than finding them on PBP (100 MB/season)
- **Simple before complex:** Teams (no season, no sub-type) validates the pipeline before NGS (3 sub-types x 10 seasons = 30 operations)
- **New types before existing backfill:** New types exercise untested adapter code paths; existing types use proven paths
- **PBP last among new types:** Largest, slowest, highest cost of re-work if bugs found
- **Validation last:** Can only validate completeness after all data is ingested

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Sub-Type Types):** Verify NGS/PFR parameter mapping against actual nfl-data-py source code (not PyPI docs, which were historically wrong per issue #34); test QBR frequency-prefixed filename collision prevention end-to-end
- **Phase 5 (Existing Backfill):** Snap counts week-level iteration needs investigation -- does `import_snap_counts(season, week=None)` return all weeks or is a week 1-18 loop mandatory? This determines whether snap counts is 10 operations or 180.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Setup):** Configuration changes only, no unknowns
- **Phase 2 (Simple Types):** Straightforward season-list fetches, all APIs verified returning data
- **Phase 4 (PBP):** Well-documented, tested, per-season loop already built and proven
- **Phase 6 (Validation):** Standard inventory regeneration and reporting

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All 9 APIs verified returning data on 2026-03-08; no new dependencies; version constraints documented and tested |
| Features | HIGH | All features cross-referenced against existing codebase; 155 new + 29 existing = 184 operations enumerated with exact CLI commands |
| Architecture | HIGH | No new architecture -- every component exists and is tested; patterns documented with code line references |
| Pitfalls | HIGH | 12 pitfalls from codebase analysis, nflverse docs, and GitHub issues; recovery strategies and cost for each |

**Overall confidence:** HIGH -- This is a brownfield execution milestone on a well-understood codebase. The adapter pattern, registry dispatch, and batch loop are all proven in production with the original 6 data types. The unknowns are narrow and well-bounded.

### Gaps to Address

- **Snap counts week-level backfill:** Does `import_snap_counts(season, week=None)` return all weeks, or must we loop 1-18? Test before planning Phase 5 task breakdown. If loop is required, that is 180 API calls (~30 min).
- **Depth chart 2025+ schema:** Need to compare 2024 vs 2025 DataFrames to confirm the ISO timestamp vs week-number change noted in nflverse docs. Determines whether a Bronze-level transform is needed or if this is deferred to Silver.
- **QBR 2024 empty data:** Returned 0 rows when tested on 2026-03-08. Likely a temporary nflverse/ESPN publishing delay. Low impact -- script handles empty DataFrames gracefully and will skip.
- **Disk space for full backfill:** Estimated ~1-1.5 GB for all types across 10 seasons. PBP dominates at ~500 MB-1 GB. Verify available disk before Phase 4. Re-runs create duplicate timestamped files unless dedup is added.
- **Schedules path inconsistency:** Existing schedules data lives in `data/bronze/games/` (legacy) but registry says `schedules/`. New backfill will write to `schedules/` per registry -- document this for downstream consumers.

## Sources

### Primary (HIGH confidence)
- Local codebase verification: all 15 adapter methods, registry entries, validation rules, and config ranges tested 2026-03-08
- [nflverse Data Schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) -- availability windows, injury data death, depth chart schema change
- [nfl-data-py GitHub (archived)](https://github.com/nflverse/nfl_data_py) -- function signatures, deprecation status confirmed Sep 25, 2025
- [nflverse-data releases](https://github.com/nflverse/nflverse-data/releases) -- data hosting, download URLs still active

### Secondary (MEDIUM confidence)
- [nfl-data-py PyPI](https://pypi.org/project/nfl-data-py/) -- version 0.3.3, last release Sep 2024
- [nfl-data-py Issue #98](https://github.com/nflverse/nfl_data_py/issues/98) -- NumPy 2.0 `np.float_` incompatibility
- [nfl-data-py Issue #34](https://github.com/nflverse/nfl_data_py/issues/34) -- `stat_type` parameter mislabeled in docs
- [nflreadpy](https://nflreadpy.nflverse.com/) -- successor library analysis (for future migration context only)

### Tertiary (LOW confidence)
- PBP memory estimates: based on single-season measurement (163 MB for 2024 with 103 columns, downcast=True), extrapolated to 10 seasons. Earlier seasons may have fewer plays.
- Total disk estimates: ~1-1.5 GB post-backfill. Based on per-season Parquet size measurements, not full backfill verification.

---
*Research completed: 2026-03-08*
*Ready for roadmap: yes*
