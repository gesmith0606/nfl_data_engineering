# Project Research Summary

**Project:** NFL Data Engineering Platform - Bronze Layer Expansion
**Domain:** NFL game prediction data pipeline
**Researched:** 2026-03-08
**Confidence:** HIGH

## Executive Summary

The platform needs to expand its Bronze layer from 6 fantasy-focused data types (~7 MB) to include 9+ game-prediction data types (~500 MB total). The single highest-value addition is full play-by-play data with EPA/WPA/CPOE columns -- this is the foundation of modern NFL analytics and the backbone of any competitive prediction model. Secondary additions (NGS, PFR advanced stats, depth charts, betting lines) add incremental accuracy but PBP alone with schedule betting lines can build a viable model.

The recommended approach is to extend the existing Medallion Architecture and NFLDataFetcher class rather than introduce new patterns. Before adding any new data types, three prerequisite fixes are required: (1) make bronze ingestion work locally (currently requires expired AWS credentials), (2) fix the hardcoded 2025 season cap, and (3) decide whether to build an adapter layer over nfl-data-py since it was archived in September 2025. The pragmatic choice is to keep nfl-data-py with an adapter layer -- it still works and reads from the same nflverse data repos as its successor nflreadpy.

The primary risk is PBP data volume: a single season is 50-100 MB with 390 columns, 100x larger than the entire current Bronze layer. This requires column subsetting, per-season processing, and memory-conscious patterns that differ from the existing "fetch all into pandas" approach. Secondary risk is the archived dependency -- any nflverse data format change could silently break ingestion.

## Key Findings

### Recommended Stack

Extend nfl-data-py (v0.3.3) with 9 new `import_*` functions. No new libraries needed.

**Tier 1 (Critical -- add first):**
- Full PBP via `import_pbp_data(years, columns)` -- remove current 12-column restriction, use ~80 curated columns
- NGS via `import_ngs_data(stat_type, years)` -- 3 stat types (passing/rushing/receiving), seasonal aggregates only
- PFR via `import_weekly_pfr(s_type, years)` + `import_seasonal_pfr(s_type, years)` -- 4 sub-types each (pass/rec/rush/def)
- Betting lines -- verify existing schedule data has spread_line/total_line before adding `import_sc_lines`

**Tier 2 (Valuable context -- add second):**
- Depth charts via `import_depth_charts(years)` -- starter identification
- QBR via `import_qbr(years, frequency='weekly')` -- complements EPA
- Draft picks, combine data -- rookie context (low volume, easy ingest)

### Expected Features

**Must have (table stakes):**
- PBP with EPA/WPA/CPOE -- the single most predictive data source for team quality
- Betting lines (spread, total) -- closing lines are the strongest single predictor of outcomes
- Team EPA aggregates in Silver layer -- rolling offensive/defensive EPA per play by team-week
- Injury + depth chart integration -- starter availability changes win probability materially

**Should have (differentiators):**
- NGS metrics (RYOE, time-to-throw, separation) -- capture talent/scheme quality beyond box scores
- PFR advanced stats (pressure rate, blitz rate) -- defensive scheme context
- Exponentially weighted rolling metrics -- better future prediction than raw averages

**Defer:**
- Combine data, draft capital, referee data -- minimal game prediction value (see anti-features in FEATURES.md)
- Full weather API -- PBP already includes temp/wind; separate pipeline adds ~2pp accuracy for high complexity
- FTN charting -- only 3 seasons of history, insufficient for ML training

### Architecture Approach

Extend existing patterns: add fetch methods to NFLDataFetcher, refactor bronze_ingestion_simple.py from if/elif chain to registry/dispatch pattern, use season-level partitioning for all new types. PBP is the only type requiring special handling (column subsetting, `downcast=True`, `cache_pbp()` for local caching).

**Key decisions:**
1. Season-level partitioning for all new types (source data is season-level; week filtering at read time)
2. Registry pattern in CLI replaces 17-way elif chain with config-driven dispatch
3. ~80 curated PBP columns (not all 390) -- expand as Silver/Gold layers need them
4. Single parameterized methods for NGS and PFR (not separate methods per sub-type)

### Critical Pitfalls

1. **nfl-data-py is archived** -- build adapter layer to isolate all `nfl.import_*` calls; future migration to nflreadpy changes one module
2. **PBP is 100x current data volume** -- always use `columns` parameter, `downcast=True`, process one season at a time
3. **Season ranges differ per data type** -- NGS starts 2016, PFR starts 2018; add per-type validation in config
4. **Bronze script requires AWS credentials** -- add local-first support before any new data types
5. **Season cap hardcoded at 2025** -- replace with dynamic `datetime.date.today().year + 1`

## Implications for Roadmap

### Phase 1: Prerequisites and Infrastructure
**Rationale:** Three blockers must be fixed before any new data types can be added
**Delivers:** Local-first bronze ingestion, dynamic season validation, registry-pattern CLI, adapter layer
**Addresses:** Pitfalls 1, 4, 7, 8, 9, 10
**Avoids:** Building on broken foundation

### Phase 2: Core PBP Ingestion
**Rationale:** PBP is the foundation -- all advanced metrics (EPA, WPA, CPOE) derive from it
**Delivers:** Full PBP with curated columns in Bronze, per-season processing, local caching
**Addresses:** Table stakes (PBP with EPA/WPA), betting line verification in schedules
**Avoids:** Memory explosion (Pitfall 3) via column subsetting and per-season processing

### Phase 3: NGS + PFR + Depth Charts
**Rationale:** These are the highest-value additions after PBP; all are small data, straightforward ingestion
**Delivers:** NGS (3 types), PFR weekly+seasonal (8 types), depth charts, QBR in Bronze
**Addresses:** Differentiator features (RYOE, pressure rate, separation, starter identification)

### Phase 4: Silver Layer for Game Prediction
**Rationale:** Raw Bronze data needs aggregation to team-week level before it feeds a prediction model
**Delivers:** Rolling team EPA, success rate, turnover rate, matchup features
**Addresses:** Team EPA aggregates (table stakes), exponentially weighted rolling metrics (differentiator)

### Phase Ordering Rationale
- Phase 1 before all else: cannot ingest new data without local-first support and validation fixes
- Phase 2 before Phase 3: PBP is the foundation; NGS/PFR add incremental value on top
- Phase 3 before Phase 4: Silver aggregations need all Bronze sources available
- Each phase is independently valuable: Phase 2 alone enables a basic prediction model

### Research Flags

Phases needing deeper research during planning:
- **Phase 2:** PBP memory management and column selection need benchmarking with real data
- **Phase 4:** Silver aggregation design (rolling windows, weighting schemes) needs game prediction domain research

Standard patterns (skip research-phase):
- **Phase 1:** Well-documented refactoring; patterns exist in Silver/Gold scripts
- **Phase 3:** Straightforward fetch-and-store; follows existing Bronze patterns exactly

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All function signatures verified from nfl-data-py source code |
| Features | HIGH | PBP/EPA as core predictor is consensus across NFL analytics community |
| Architecture | HIGH | Extends existing patterns; no new architectural decisions |
| Pitfalls | HIGH | Most pitfalls confirmed via direct code review |

**Overall confidence:** HIGH

### Gaps to Address

- **SC Lines vs PBP overlap:** Verify whether PBP spread_line/total_line columns are sufficient before adding separate sc_lines ingestion
- **Win totals reliability:** Source explicitly flagged as "in flux" by nflverse; defer until stability confirmed
- **nflreadpy maturity:** Monitor for feature parity; plan migration timeline for 2026 season data
- **PBP actual file sizes:** Storage estimates (50-100 MB/season) need validation with real downloads

## Sources

### Primary (HIGH confidence)
- nfl-data-py v0.3.3 source code (local venv) -- all function signatures, parameters, minimum year constraints
- Existing codebase (src/nfl_data_integration.py, src/config.py, scripts/) -- current patterns and gaps
- nflverse GitHub repos and data releases -- data availability and format

### Secondary (MEDIUM confidence)
- Frontiers: Advancing NFL win prediction (2025) -- ML model comparison, feature importance
- Open Source Football: NFL game prediction -- rolling EPA weighting approach
- ESPN referee bias analysis -- officials data value assessment

---
*Research completed: 2026-03-08*
*Ready for roadmap: yes*
