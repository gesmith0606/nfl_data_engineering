---
phase: 02-core-pbp-ingestion
plan: 01
subsystem: ingestion
tags: [pbp, epa, wpa, cpoe, nfl-data-py, parquet, bronze]

# Dependency graph
requires:
  - phase: 01-infrastructure-prerequisites
    provides: "NFLDataAdapter, DATA_TYPE_REGISTRY, local-first CLI"
provides:
  - "PBP_COLUMNS constant (103 curated columns)"
  - "include_participation param on fetch_pbp"
  - "PBP kwargs wiring in CLI (columns/downcast/include_participation)"
  - "--seasons batch flag with parse_seasons_range()"
affects: [03-advanced-stats, silver-pbp-transforms, game-prediction-models]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config constant for curated column lists (PBP_COLUMNS)"
    - "Per-data-type kwargs block in _build_method_kwargs"
    - "Batch season loop with single-season memory safety"

key-files:
  created:
    - tests/test_pbp_ingestion.py
  modified:
    - src/config.py
    - src/nfl_data_adapter.py
    - scripts/bronze_ingestion_simple.py

key-decisions:
  - "103 columns kept (not trimmed to ~80) -- all relevant for game prediction, minimal memory cost"
  - "include_participation defaults to False to prevent column merge issues"
  - "Batch loop processes one season at a time for memory safety (peak ~130 MB vs ~7 GB for all-at-once)"

patterns-established:
  - "PBP_COLUMNS as config constant: single source of truth for curated PBP columns"
  - "Per-method kwargs wiring in _build_method_kwargs for data-type-specific params"

requirements-completed: [PBP-01, PBP-02, PBP-03, PBP-04]

# Metrics
duration: 3min
completed: 2026-03-08
---

# Phase 2 Plan 01: PBP Column Curation and Batch CLI Summary

**103 curated PBP columns (EPA/WPA/CPOE/air yards/success) with memory-safe single-season batch ingestion via --seasons flag**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-08T16:38:37Z
- **Completed:** 2026-03-08T16:41:34Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- PBP_COLUMNS constant with 103 curated columns covering all key advanced metrics (EPA, WPA, CPOE, air yards, success) plus game context, player IDs, Vegas lines, and weather
- fetch_pbp updated with include_participation=False default to prevent column merge issues
- CLI wires columns/downcast/include_participation automatically for PBP data type
- --seasons batch flag enables range-based ingestion (e.g., 2010-2025), looping one season at a time for memory safety
- 10 new PBP tests, 100 total tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create PBP test suite (RED)** - `a46f7e8` (test)
2. **Task 2: Add PBP_COLUMNS config and update adapter** - `a9318e1` (feat)
3. **Task 3: Wire PBP kwargs in CLI and add --seasons batch flag** - `1e75a6a` (feat)

## Files Created/Modified
- `tests/test_pbp_ingestion.py` - 10 tests covering PBP-01 through PBP-04 requirements
- `src/config.py` - PBP_COLUMNS constant (103 curated columns)
- `src/nfl_data_adapter.py` - include_participation param added to fetch_pbp
- `scripts/bronze_ingestion_simple.py` - PBP kwargs wiring, parse_seasons_range(), --seasons flag, batch loop

## Decisions Made
- Kept 103 columns (not trimmed to ~80 from original estimate) -- all relevant for game prediction with minimal memory cost (66 MB per season)
- include_participation defaults to False to avoid 26 extra columns and merge issues when using curated column lists
- Batch loop processes one season per iteration (peak ~130 MB) rather than all at once (~7 GB)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PBP column curation and batch CLI ready for use
- Can run `python scripts/bronze_ingestion_simple.py --data-type pbp --seasons 2010-2025` to ingest all 16 seasons
- Foundation ready for Phase 3 advanced stats and silver-layer PBP transforms

---
*Phase: 02-core-pbp-ingestion*
*Completed: 2026-03-08*
