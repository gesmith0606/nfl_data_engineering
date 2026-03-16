---
phase: 20-infrastructure-and-data-expansion
plan: 02
subsystem: infra
tags: [pbp, officials, bronze-ingestion, parquet, nfl-data-py]

requires:
  - phase: 20-01
    provides: Expanded PBP_COLUMNS (140 cols), officials adapter/registry, config season ranges
provides:
  - 10 PBP Bronze parquet files (2016-2025) with 140-column expanded schema
  - 10 Officials Bronze parquet files (2016-2025) with referee crew data
affects: [21-team-analytics, 22-travel-distance, 23-prediction-models]

tech-stack:
  added: []
  patterns: [batch season-by-season ingestion for memory safety]

key-files:
  created:
    - data/bronze/pbp/season=2016/ through season=2025/ (re-ingested with 140 cols)
    - data/bronze/officials/season=2016/ through season=2025/ (new)
  modified: []

key-decisions:
  - "PBP re-ingested season-by-season to avoid memory issues (per RESEARCH.md Pitfall 3)"
  - "Old PBP files retained alongside new ones; download_latest_parquet reads newest automatically"
  - "Officials ingestion starts at 2016 (not 2015) per DATA_TYPE_SEASON_RANGES alignment with PBP"

patterns-established:
  - "Batch ingestion pattern: one season at a time via CLI loop for large datasets"

requirements-completed: [INFRA-01, INFRA-02]

duration: 2min
completed: 2026-03-16
---

# Phase 20 Plan 02: Bronze Data Ingestion Summary

**Re-ingested PBP for 2016-2025 with 140-column expanded schema and ingested officials referee data for 10 seasons; 302 tests pass with zero regressions**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-16T15:57:44Z
- **Completed:** 2026-03-16T15:59:35Z
- **Tasks:** 2
- **Files modified:** 20 parquet files (10 PBP + 10 officials, not git-tracked)

## Accomplishments
- Re-ingested PBP Bronze data for all 10 seasons (2016-2025) with expanded 140-column schema including penalty_type, kick_distance, fumble_recovery_1_team, drive_play_count, and 33 other new columns
- Ingested officials/referee crew data for 10 seasons (2016-2025) with correct schema: game_id, official_name, official_position, official_id, season
- Officials data contains all 7 crew positions (BJ, DJ, FJ, LJ, R, SJ, U) with ~1,900 rows per season
- Full test suite (302 tests) passes with zero regressions after data expansion

## Task Commits

Data files are in .gitignore (parquet files stored locally, not in git). No code changes were required for this plan -- all code/config changes were completed in Plan 01.

1. **Task 1: Re-ingest PBP data for 2016-2025** - data-only (no git commit; files at data/bronze/pbp/)
2. **Task 2: Ingest officials data for 2016-2025** - data-only (no git commit; files at data/bronze/officials/)

**Plan metadata:** see final docs commit

## Files Created/Modified
- `data/bronze/pbp/season=2016/` through `season=2025/` - Re-ingested PBP with 140 columns (was 103)
- `data/bronze/officials/season=2016/` through `season=2025/` - New officials referee crew data

## Data Inventory

| Season | PBP Rows | PBP Cols | Officials Rows |
|--------|----------|----------|----------------|
| 2016   | 47,651   | 140      | 1,886          |
| 2017   | 47,984   | 140      | 1,893          |
| 2018   | 47,996   | 140      | 1,878          |
| 2019   | 48,058   | 140      | 1,855          |
| 2020   | 48,111   | 140      | 1,883          |
| 2021   | 50,712   | 140      | 1,988          |
| 2022   | 50,692   | 140      | 1,987          |
| 2023   | 49,847   | 140      | 1,993          |
| 2024   | 49,492   | 140      | 1,995          |
| 2025   | 48,771   | 140      | 1,994          |

## Decisions Made
- Ingested one season at a time per RESEARCH.md Pitfall 3 guidance (memory safety for PBP)
- Old PBP parquet files left in place alongside new ones; download_latest_parquet() selects the newest file automatically
- Officials ingested for 2016-2025 (config supports 2015+, but aligning with PBP range for consistency)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PBP Bronze data with expanded columns ready for Phase 21 (team analytics: penalties, special teams, turnovers, drives)
- Officials Bronze data ready for Phase 23 (prediction models: referee tendencies)
- All Phase 20 infrastructure deliverables complete (config + code from Plan 01, data from Plan 02)

---
*Phase: 20-infrastructure-and-data-expansion*
*Completed: 2026-03-16*
