---
phase: 20-infrastructure-and-data-expansion
plan: 01
subsystem: infra
tags: [pbp, officials, stadium-coordinates, config, nfl-data-py]

requires:
  - phase: none
    provides: greenfield config expansion
provides:
  - Expanded PBP_COLUMNS (140 columns) for game prediction models
  - Officials data type (fetch_officials + registry) for referee analysis
  - STADIUM_COORDINATES dict (38 entries) for travel distance computation
affects: [20-02-data-ingestion, 21-team-analytics, 22-travel-distance, 23-prediction-models]

tech-stack:
  added: []
  patterns: [adapter-method-pattern for new data types, registry-driven ingestion]

key-files:
  created: []
  modified:
    - src/config.py
    - src/nfl_data_adapter.py
    - scripts/bronze_ingestion_simple.py
    - tests/test_infrastructure.py
    - tests/test_pbp_ingestion.py

key-decisions:
  - "Officials season range starts at 2015 per user decision (nflverse confirmed coverage)"
  - "PBP expanded by 37 columns (penalty, ST, fumble recovery, drive detail) to 140 total"
  - "Stadium coordinates include 6 international venues (London x2, Munich, Mexico City, Sao Paulo, Madrid)"

patterns-established:
  - "fetch_* adapter method pattern: _filter_seasons -> _import_nfl -> _safe_call with column renaming"
  - "STADIUM_COORDINATES 4-tuple format: (lat, lon, timezone_str, venue_name)"

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

duration: 4min
completed: 2026-03-16
---

# Phase 20 Plan 01: Infrastructure Config and Code Paths Summary

**Expanded PBP to 140 columns, added officials data type (2015+) with adapter/registry, and 38-entry stadium coordinate dict for travel distance**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-16T15:50:56Z
- **Completed:** 2026-03-16T15:55:23Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Expanded PBP_COLUMNS from 103 to 140 columns covering penalties, special teams, fumble recovery, and drive detail
- Added officials data type end-to-end: config season range (2015+), NFLDataAdapter.fetch_officials() with column renaming, and bronze registry entry
- Added STADIUM_COORDINATES with all 32 NFL teams plus 6 international venues (lat/lon/timezone/venue_name)
- Created 11 new infrastructure validation tests; updated 3 existing tests for compatibility; full suite at 302 passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Expand PBP_COLUMNS and add STADIUM_COORDINATES + officials season range** - `08c5148` (feat)
2. **Task 2: Add fetch_officials() adapter method and officials registry entry** - `7a2d6a9` (feat)
3. **Task 3: Create infrastructure validation tests** - `4f649dd` (test)

## Files Created/Modified
- `src/config.py` - PBP_COLUMNS expanded to 140, STADIUM_COORDINATES dict added, officials season range added
- `src/nfl_data_adapter.py` - fetch_officials() method with name/off_pos column renaming
- `scripts/bronze_ingestion_simple.py` - Officials entry added to DATA_TYPE_REGISTRY
- `tests/test_infrastructure.py` - 11 new Phase 20 tests plus updated existing counts
- `tests/test_pbp_ingestion.py` - Updated PBP column count assertions from 103 to 140

## Decisions Made
- Officials season range set to 2015 per user decision in CONTEXT.md (nflverse confirmed coverage)
- PBP expansion adds exactly 37 columns (140 total) covering all categories from plan
- Stadium coordinates use 4-tuple format for downstream haversine + timezone computation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing PBP column count tests**
- **Found during:** Task 3 (test creation)
- **Issue:** Two tests in test_pbp_ingestion.py hardcoded PBP_COLUMNS count at 103, failing after expansion
- **Fix:** Updated test_pbp_columns_count range to 128-160 and test_pbp_columns_exact_count to 140
- **Files modified:** tests/test_pbp_ingestion.py
- **Verification:** Full suite passes (302 tests)
- **Committed in:** 4f649dd (Task 3 commit)

**2. [Rule 1 - Bug] Updated season ranges count from 15 to 16**
- **Found during:** Task 3 (test creation)
- **Issue:** Existing test_season_ranges_has_all_15_types expected exactly 15 types, now 16 with officials
- **Fix:** Updated assertion to 16 types and added "officials" to expected set
- **Files modified:** tests/test_infrastructure.py
- **Verification:** All tests pass
- **Committed in:** 4f649dd (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both fixes necessary to maintain test suite consistency after planned changes. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All config and code paths are in place for Plan 02 (data ingestion)
- Officials ingestion can be run: `python scripts/bronze_ingestion_simple.py --season 2024 --data-type officials`
- STADIUM_COORDINATES ready for Phase 22 travel distance computation
- PBP_COLUMNS ready for Phase 21 team analytics PBP ingestion

---
*Phase: 20-infrastructure-and-data-expansion*
*Completed: 2026-03-16*
