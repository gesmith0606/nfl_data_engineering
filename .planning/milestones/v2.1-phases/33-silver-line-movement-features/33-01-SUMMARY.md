---
phase: 33-silver-line-movement-features
plan: 01
subsystem: analytics
tags: [market-data, line-movement, odds, silver-layer, pandas]

# Dependency graph
requires:
  - phase: 32-bronze-odds-ingestion
    provides: Bronze odds Parquet with opening/closing spreads and totals
provides:
  - market_analytics.py module with compute_movement_features() and reshape_to_per_team()
  - Silver market transformation CLI (silver_market_transformation.py)
  - Silver market_data Parquet output for season 2020 (488 per-team rows)
  - 20 unit tests for movement computation, magnitude, key crossings, steam move, per-team reshape
affects: [33-02-feature-integration, feature-engineering, prediction-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: [per-team-reshape-with-directional-sign-flip, magnitude-ordinal-buckets, key-number-crossing-detection]

key-files:
  created:
    - src/market_analytics.py
    - scripts/silver_market_transformation.py
    - tests/test_market_analytics.py
  modified: []

key-decisions:
  - "Magnitude buckets encoded as ordinal float64 (0-3) not categorical strings -- passes numeric dtype filter in get_feature_columns()"
  - "Directional features (spread columns) negated for away team; symmetric features (totals, magnitude, crossings) identical for both teams"
  - "is_steam_move column set to NaN for all rows -- forward-compatible schema placeholder per D-15/D-16"

patterns-established:
  - "Market analytics module: compute_movement_features() for game-level features, reshape_to_per_team() for Silver output"
  - "Key number crossing: check if absolute spread crosses [3, 7, 10] or total crosses [41, 44, 47]"

requirements-completed: [LINE-01, LINE-02, LINE-03]

# Metrics
duration: 6min
completed: 2026-03-28
---

# Phase 33 Plan 01: Silver Line Movement Features Summary

**Line movement module with spread/total shift, ordinal magnitude buckets (0-3), key number crossings, and per-team reshape producing 488-row Silver Parquet for season 2020**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-28T04:44:51Z
- **Completed:** 2026-03-28T04:51:37Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments
- Created market_analytics.py with two public functions: compute_movement_features() and reshape_to_per_team()
- 20 unit tests across 5 test classes (TestMovementComputation, TestMagnitudeBuckets, TestKeyNumberCrossing, TestSteamMove, TestPerTeamReshape)
- Silver CLI produces market_data Parquet: 488 rows (244 games x 2 teams), 20 columns
- Full test suite: 536 passed (up from 516), zero failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Create market_analytics.py with tests** - `10b8076` (feat) -- TDD: 20 tests written first, then implementation
2. **Task 2: Create Silver market transformation CLI** - `d7402ae` (feat)

## Files Created/Modified
- `src/market_analytics.py` - Line movement computation and per-team reshape (2 public functions, key number constants)
- `tests/test_market_analytics.py` - 20 unit tests with synthetic fixtures across 5 test classes
- `scripts/silver_market_transformation.py` - Silver CLI with argparse, Bronze reader, local save, optional S3 upload

## Decisions Made
- Magnitude buckets as ordinal float64 (0/1/2/3) not strings -- required for numeric dtype filter in feature_engineering.py
- Pre-game vs retrospective feature classification documented in code comments (D-08)
- Silver output includes game_id and game_type for debugging (existing dedup logic handles suffixed duplicates)

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all features fully implemented. is_steam_move is intentionally NaN per D-15/D-16 (no timestamp data in FinnedAI), not a stub.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Silver market_data Parquet ready for Plan 02 feature engineering integration
- Plan 02 will add market_data to SILVER_TEAM_LOCAL_DIRS in config.py and opening_spread/opening_total to _PRE_GAME_CONTEXT
- Full test suite green (536 passed)

---
*Phase: 33-silver-line-movement-features*
*Completed: 2026-03-28*
