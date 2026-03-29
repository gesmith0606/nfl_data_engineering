---
phase: 36-silver-and-feature-vector-assembly
plan: 01
subsystem: data-pipeline
tags: [silver, parquet, market-data, player-quality, line-movement, nfl-data-py]

# Dependency graph
requires:
  - phase: 35-bronze-data-completion
    provides: Bronze odds for 2016-2025, Bronze player/team data for 2025
provides:
  - Silver market_data for 10 seasons (2016-2025) with line movement features
  - Silver player_quality for 6 seasons (2020-2025) with QB EPA, injury impact
  - All 2025 Silver paths complete (13 output paths)
affects: [36-02-feature-vector-assembly, 37-holdout-reset, 38-ensemble-retraining]

# Tech tracking
tech-stack:
  added: []
  patterns: [nflverse-bridge zero-shift convention for 2022+ market data]

key-files:
  created: []
  modified:
    - scripts/silver_player_quality_transformation.py

key-decisions:
  - "2025 depth charts use ESPN schema without depth_team -- guard added for graceful fallback"
  - "Bridge seasons (2022-2025) produce spread_shift=0, total_shift=0 as expected (opening==closing)"

patterns-established:
  - "Schema guard: check column existence before access when Bronze sources change schema across seasons"

requirements-completed: [SLVR-01, SLVR-02]

# Metrics
duration: 6min
completed: 2026-03-29
---

# Phase 36 Plan 01: Silver Layer Expansion Summary

**Silver market data generated for all 10 seasons (2016-2025) and all Silver transformations completed for 2025 including player quality gap-fill for 2020-2025**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-29T04:44:01Z
- **Completed:** 2026-03-29T04:50:01Z
- **Tasks:** 2
- **Files modified:** 1 (scripts/silver_player_quality_transformation.py)

## Accomplishments
- Silver market_data covers all 10 seasons: FinnedAI (2016-2021) with real line movement, nflverse-bridge (2022-2025) with zero-shift convention
- Silver player_quality gap filled for 5 missing seasons (2020, 2021, 2022, 2024, 2025) -- now covers full 2020-2025 range
- All 13 Silver output paths populated for 2025 (usage, advanced, game_context, pbp_metrics, tendencies, sos, situational, pbp_derived, player_quality, market_data, referee_tendencies, playoff_context, defense/positional)

## Task Commits

Each task was committed atomically:

1. **Task 1: Silver market data expansion (all 10 seasons)** - No source code changes; data artifacts only (gitignored Parquet files)
2. **Task 2: Silver player quality expansion and 2025 Silver transformations** - `8d4911a` (fix)

## Files Created/Modified
- `scripts/silver_player_quality_transformation.py` - Added depth_team column existence check for 2025 ESPN-schema depth charts

## Data Artifacts Generated (gitignored)
- `data/silver/teams/market_data/season=2016/` through `season=2025/` (10 seasons, 5,210 total rows)
- `data/silver/teams/player_quality/season=2020/` through `season=2025/` (6 seasons)
- `data/silver/players/usage/season=2025/` (46,011 rows)
- `data/silver/players/advanced/season=2025/` (19,421 rows, 112 columns)
- `data/silver/teams/pbp_metrics/season=2025/` (544 rows)
- `data/silver/teams/tendencies/season=2025/` (544 rows)
- `data/silver/teams/sos/season=2025/` (544 rows)
- `data/silver/teams/situational/season=2025/` (544 rows)
- `data/silver/teams/pbp_derived/season=2025/` (544 rows, 164 columns)
- `data/silver/teams/game_context/season=2025/` (570 rows)
- `data/silver/teams/referee_tendencies/season=2025/` (570 rows)
- `data/silver/teams/playoff_context/season=2025/` (544 rows)

## Decisions Made
- 2025 depth charts changed to ESPN schema (pos_rank instead of depth_team) -- added column guard to fall back gracefully
- Bridge seasons (2022-2025) correctly produce zero line movement (opening==closing per Phase 35 design)
- PYTHONPATH required for scripts importing nfl_data_integration.py (uses `from src.config`)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed KeyError on depth_team for 2025 depth charts**
- **Found during:** Task 2 (Silver player quality transformation for 2025)
- **Issue:** 2025 Bronze depth charts use ESPN schema with `pos_rank` column instead of nflverse `depth_team` column, causing KeyError
- **Fix:** Added `has_depth_team = "depth_team" in depth_df.columns` guard before accessing the column; falls back to `backup_qb_start=False`
- **Files modified:** scripts/silver_player_quality_transformation.py
- **Verification:** 2025 player quality transformation completes with 570 rows, 32 teams, 28 columns
- **Committed in:** 8d4911a

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential fix for 2025 compatibility. No scope creep.

## Issues Encountered
- PYTHONPATH needed for silver_player_transformation.py and other scripts that import from nfl_data_integration.py (uses `from src.config` which requires project root on sys.path). Resolved by setting `PYTHONPATH=/Users/georgesmith/repos/nfl_data_engineering`.
- No QBR weekly data available for 2025 (nflverse limitation) -- qbr_ columns are NaN, which is expected and handled by gradient boosting.
- No injury data for 2025 (nflverse caps at 2024) -- injury impact columns set to zero as designed per D-06.

## Known Stubs
None -- all Silver paths produce real data from Bronze sources.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Silver layer complete for feature vector assembly (plan 36-02)
- All 10 Silver source paths populated for 2016-2025 training window
- 2025 has 13 Silver output paths ready for holdout feature vector

---
*Phase: 36-silver-and-feature-vector-assembly*
*Completed: 2026-03-29*
