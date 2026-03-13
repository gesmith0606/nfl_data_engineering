---
phase: 12-2025-player-stats-gap-closure
plan: 01
subsystem: data-ingestion
tags: [nflverse, stats_player, column-mapping, parquet, pandas, adapter]

# Dependency graph
requires:
  - phase: 08-bronze-data-types
    provides: NFLDataAdapter class with _safe_call pattern and _filter_seasons
provides:
  - "STATS_PLAYER_MIN_SEASON and STATS_PLAYER_COLUMN_MAP config constants"
  - "_fetch_stats_player() method for direct nflverse GitHub release download"
  - "_aggregate_seasonal_from_weekly() with 13 team-share columns"
  - "Conditional routing in fetch_weekly_data and fetch_seasonal_data for 2025+"
affects: [12-02-bronze-ingestion-validation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Season-conditional routing: split seasons at threshold, delegate to different fetch paths"
    - "Column mapping at ingestion: rename new schema to old names for backward compat"
    - "Seasonal aggregation from weekly: sum counting stats, recalculate share columns"

key-files:
  created:
    - tests/test_stats_player.py
  modified:
    - src/config.py
    - src/nfl_data_adapter.py

key-decisions:
  - "Map passing_cpoe -> dakota for backward compatibility (downstream uses dakota)"
  - "Use urllib.request (stdlib) instead of requests to avoid new dependency"
  - "13 share columns computed from team totals (tgt_sh, ay_sh, ry_sh, dom, w8dom, wopr_x, wopr_y, ppr_sh, rfd_sh, rtd_sh, rtdfd_sh, yac_sh, yptmpa)"
  - "Weighted average for dakota column (weight by attempts)"

patterns-established:
  - "Season-threshold routing: old_seasons/new_seasons split with STATS_PLAYER_MIN_SEASON"
  - "GitHub release download with optional GITHUB_TOKEN auth header"

requirements-completed: [BACKFILL-02, BACKFILL-03]

# Metrics
duration: 20min
completed: 2026-03-12
---

# Phase 12 Plan 01: Stats Player Adapter Summary

**stats_player adapter with column mapping, seasonal aggregation, and conditional routing for 2025+ nflverse data**

## Performance

- **Duration:** 20 min
- **Started:** 2026-03-12T23:46:42Z
- **Completed:** 2026-03-13T00:06:54Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Conditional routing in fetch_weekly_data and fetch_seasonal_data transparently handles 2025+ seasons via stats_player tag
- Column mapping (5 renames) ensures backward compatibility with all downstream code
- Seasonal aggregation computes 13 team-share columns (tgt_sh, ay_sh, dom, wopr, etc.) from weekly data
- 19 new tests covering config, mapping, download, auth, routing, and aggregation -- 186 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add config constants and test scaffold** - `06b4191` (feat)
2. **Task 2: Implement adapter methods and conditional routing** - `de22ec7` (feat)

## Files Created/Modified
- `src/config.py` - STATS_PLAYER_MIN_SEASON, STATS_PLAYER_COLUMN_MAP constants
- `src/nfl_data_adapter.py` - _fetch_stats_player, _aggregate_seasonal_from_weekly, modified fetch_weekly_data and fetch_seasonal_data
- `tests/test_stats_player.py` - 19 tests for config, column mapping, routing logic, adapter methods, and aggregation

## Decisions Made
- Mapped `passing_cpoe` to `dakota` for backward compatibility since downstream code references `dakota`
- Used `urllib.request` (stdlib) instead of `requests` to avoid adding a new dependency
- Computed 13 share columns from team totals rather than attempting to use pre-aggregated seasonal file (which lacks these columns)
- Weighted average for `dakota` column using `attempts` as weights

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Adapter methods ready for Bronze ingestion (Plan 02: `--data-type player_weekly --season 2025` should work transparently)
- Full test suite (186 tests) green with no regressions

---
*Phase: 12-2025-player-stats-gap-closure*
*Completed: 2026-03-12*
