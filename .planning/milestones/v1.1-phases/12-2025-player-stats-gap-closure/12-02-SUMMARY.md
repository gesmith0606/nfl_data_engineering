---
phase: 12-2025-player-stats-gap-closure
plan: 02
subsystem: data-ingestion
tags: [nflverse, stats_player, bronze, silver, parquet, 2025-backfill]

# Dependency graph
requires:
  - phase: 12-01-stats-player-adapter
    provides: Conditional routing, column mapping, seasonal aggregation for 2025+ seasons
provides:
  - "2025 weekly player stats Bronze Parquet (19,421 rows, 115 columns)"
  - "2025 seasonal player stats Bronze Parquet (2,025 rows, 60 columns)"
  - "2025 Silver usage metrics and opponent rankings"
affects: [gold-projections, draft-tool, backtest]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Season-only bronze path for player_weekly (no week partition for full-season fetch)"

key-files:
  created: []
  modified:
    - scripts/bronze_ingestion_simple.py
    - tests/test_infrastructure.py

key-decisions:
  - "Changed player_weekly registry to season-only path matching 2020-2024 storage pattern"
  - "High null percentages in EPA/kicker columns are expected (position-specific stats)"

patterns-established:
  - "Full-season player data stored at season= level without week partition"

requirements-completed: [BACKFILL-02, BACKFILL-03]

# Metrics
duration: 4min
completed: 2026-03-12
---

# Phase 12 Plan 02: Bronze Ingestion & Validation Summary

**2025 weekly (19,421 rows) and seasonal (2,025 rows) player stats ingested from nflverse stats_player, validated against 2024 schema, and processed through Silver pipeline**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-13T00:14:59Z
- **Completed:** 2026-03-13T00:18:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Ingested 2025 weekly player stats: 19,421 rows, 115 columns (62 additional columns vs 2024 including defensive/kicker stats)
- Ingested 2025 seasonal player stats: 2,025 rows, 60 columns with all 13 team-share columns
- Silver pipeline processed 2025: 46,011 player-week rows with usage metrics, rolling averages, game script indicators, venue splits, and opponent rankings
- Full test suite passes: 186 tests green

## Task Commits

Each task was committed atomically:

1. **Task 1: Ingest 2025 player weekly and seasonal via CLI** - `0b46e4c` (feat)
2. **Task 2: Validate and run Silver pipeline on 2025** - `e26559d` (feat)

## Files Created/Modified
- `scripts/bronze_ingestion_simple.py` - Fixed player_weekly registry path to season-only (no week partition)
- `tests/test_infrastructure.py` - Updated test_local_path_structure to match new path pattern

## Decisions Made
- Changed player_weekly bronze_path from `players/weekly/season={season}/week={week}` to `players/weekly/season={season}` to match existing 2020-2024 storage pattern and ensure Silver pipeline can read 2025 data
- High null percentages in EPA, kicker, and advanced columns are expected and acceptable -- these are position-specific stats (e.g., only QBs have passing_epa)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed player_weekly registry path template**
- **Found during:** Task 1 (Bronze ingestion)
- **Issue:** Registry had `week={week}` in path but Silver pipeline reads from `season=YYYY/` directly; 2020-2024 files stored at season level
- **Fix:** Changed requires_week to False and removed week={week} from bronze_path
- **Files modified:** scripts/bronze_ingestion_simple.py, tests/test_infrastructure.py
- **Verification:** Files saved to correct path, Silver pipeline reads them, 186 tests pass
- **Committed in:** 0b46e4c (Task 1), e26559d (Task 2 - test fix)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix was necessary for Silver pipeline compatibility. No scope creep.

## Issues Encountered
- Silver transformation script required PYTHONPATH to be set to project root for imports to work (pre-existing issue, not caused by this plan)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- 2025 Bronze + Silver data now available for Gold projections
- PLAYER_DATA_SEASONS in config.py may need updating to include 2025 for projection/backtest workflows
- Phase 12 complete: all 2025 player stats gap closure requirements fulfilled

---
*Phase: 12-2025-player-stats-gap-closure*
*Completed: 2026-03-12*
