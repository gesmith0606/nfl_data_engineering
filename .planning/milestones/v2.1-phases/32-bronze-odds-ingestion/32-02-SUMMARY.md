---
phase: 32-bronze-odds-ingestion
plan: 02
subsystem: infra
tags: [config, odds, bronze, parquet, data-quality]

# Dependency graph
requires:
  - phase: 32-01
    provides: "bronze_odds_ingestion.py script with parse, map, join, validate functions"
provides:
  - "odds registered in DATA_TYPE_SEASON_RANGES as (2016, lambda: 2021)"
  - "End-to-end validated Parquet output in data/bronze/odds/"
  - "Implausible spread filter (|spread| > 25) for corrupt FinnedAI entries"
affects: [silver-odds-transformation, line-movement-features, clv-tracking]

# Tech tracking
tech-stack:
  added: []
  patterns: ["static lambda cap for historical-only data types in DATA_TYPE_SEASON_RANGES"]

key-files:
  created: []
  modified:
    - src/config.py
    - tests/test_bronze_odds.py
    - tests/test_infrastructure.py
    - scripts/bronze_odds_ingestion.py

key-decisions:
  - "Implausible spread filter at |spread| > 25 drops ~24 corrupt FinnedAI entries per season"
  - "Sign convention check uses strict < 0 (not <= 0) to allow pick'em opening lines"

patterns-established:
  - "Static lambda cap pattern: (min_year, lambda: max_year) for fixed historical data types"

requirements-completed: [ODDS-03]

# Metrics
duration: 4min
completed: 2026-03-27
---

# Phase 32 Plan 02: Config Registration and E2E Pipeline Summary

**Odds registered in DATA_TYPE_SEASON_RANGES with (2016, lambda: 2021), end-to-end 2020 ingestion producing 244-row validated Parquet with r=0.997 cross-validation**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-27T21:39:23Z
- **Completed:** 2026-03-27T21:43:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Registered odds as 17th data type in DATA_TYPE_SEASON_RANGES with fixed historical range 2016-2021
- End-to-end pipeline run for 2020: 244 games, zero orphans, r=0.997 Pearson correlation, 97.1% within 1 point
- Added data quality filter dropping ~24 corrupt FinnedAI entries per season where totals were swapped into spread columns
- 516 tests passing (13 more than baseline 503)

## Task Commits

Each task was committed atomically:

1. **Task 1: Register odds in config.py and enable config test** - `abfe83a` (feat)
2. **Task 2: End-to-end pipeline run for single season** - `0affa70` (feat)

## Files Created/Modified
- `src/config.py` - Added odds to DATA_TYPE_SEASON_RANGES
- `tests/test_bronze_odds.py` - Unskipped config test, added season boundary test (13 total)
- `tests/test_infrastructure.py` - Updated to expect 17 data types, added odds to static cap set
- `scripts/bronze_odds_ingestion.py` - Added implausible spread filter, fixed sign convention check

## Decisions Made
- Implausible spread filter at |spread| > 25: FinnedAI has ~24 entries per season where close_over_under values appear in spread columns. Filtering at 25 is well above any realistic NFL spread (~21 max historically) while catching all corrupt entries.
- Sign convention check changed from <= 0 to < 0: a pick'em opening line (0.0) for a game where the line later moved to -9 is not a sign flip, just line movement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FinnedAI corrupt spread values (totals in spread columns)**
- **Found during:** Task 2 (End-to-end pipeline run)
- **Issue:** 24 FinnedAI entries for 2020 had closing spreads like -49.5, -55.0 (clearly total values, not spreads), causing cross-validation to fail (r=0.54)
- **Fix:** Added data quality filter in align_spreads() dropping rows where |opening_spread| > 25 or |closing_spread| > 25
- **Files modified:** scripts/bronze_odds_ingestion.py
- **Verification:** After filter, r=0.997 and within-1pt=97.1%
- **Committed in:** 0affa70

**2. [Rule 1 - Bug] Sign convention check too strict for pick'em lines**
- **Found during:** Task 2 (End-to-end pipeline run)
- **Issue:** KC vs CLE playoff game opened at 0.0 (pick'em), negation gives -0.0 which triggered <= 0 check despite nflverse showing KC as 7.5-point favorite
- **Fix:** Changed sign_flips filter from <= 0 to < 0
- **Files modified:** scripts/bronze_odds_ingestion.py
- **Verification:** Sign convention check now passes for all 45 clear home favorites
- **Committed in:** 0affa70

**3. [Rule 1 - Bug] Infrastructure tests expected exactly 16 data types**
- **Found during:** Task 1 (Config registration)
- **Issue:** test_season_ranges_has_all_16_types and test_validate_edge_max_year failed after adding odds
- **Fix:** Updated expected count to 17, added odds to static_cap_types set
- **Files modified:** tests/test_infrastructure.py
- **Verification:** All 33 infrastructure tests pass
- **Committed in:** abfe83a

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All auto-fixes necessary for correctness. No scope creep. The corrupt data in FinnedAI was a known risk; the filter is the correct approach.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Bronze odds layer complete: 2020 validated, script ready for all 2016-2021 seasons
- Ready for Silver transformation: line movement features (opening-to-closing shifts), CLV tracking
- FinnedAI JSON cached locally at data/raw/sbro/nfl_archive_10Y.json for future season runs

## Known Stubs
None - all data flows are wired and producing real output.

---
*Phase: 32-bronze-odds-ingestion*
*Completed: 2026-03-27*
