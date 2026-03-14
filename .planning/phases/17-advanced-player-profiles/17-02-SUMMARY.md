---
phase: 17-advanced-player-profiles
plan: 02
subsystem: analytics
tags: [ngs, pfr, qbr, silver-layer, data-pipeline, parquet, player-profiles]

requires:
  - phase: 17-advanced-player-profiles
    provides: player_advanced_analytics.py compute functions and rolling utilities
provides:
  - silver_advanced_transformation.py CLI script for Bronze-to-Silver advanced player profiles
  - Merged advanced player profile Parquet files at data/silver/players/advanced/
  - Three-tier join strategy (GSIS ID for NGS, name+team for PFR/QBR)
affects: [gold-projections, draft-optimizer]

tech-stack:
  added: []
  patterns: [synthetic player ID for name-based rolling windows, overlap detection for multi-source merge]

key-files:
  created:
    - scripts/silver_advanced_transformation.py
  modified: []

key-decisions:
  - "Synthetic player_gsis_id from name+team enables PFR/QBR rolling windows despite missing GSIS IDs"
  - "QBR raw data 'team' column dropped before 'team_abb' rename to avoid duplicate team columns"
  - "Overlapping columns across NGS sources (avg_intended_air_yards) kept from first merge, dropped from second"
  - "PFR pressure 12% match rate is correct -- PFR pass data covers QBs only (~700/5653 player-weeks)"

patterns-established:
  - "Three-tier join: GSIS ID (NGS), normalized name+team (PFR/QBR), team-only (PFR team blitz)"
  - "Overlap detection before merge prevents pandas _x/_y suffix columns"

requirements-completed: [PROF-01, PROF-02, PROF-03, PROF-04, PROF-05, PROF-06]

duration: 9min
completed: 2026-03-14
---

# Phase 17 Plan 02: Silver Advanced Transformation CLI Summary

**Bronze-to-Silver pipeline merging NGS/PFR/QBR onto player roster with three-tier join strategy across 6 seasons (47,447 player-weeks)**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-14T22:25:45Z
- **Completed:** 2026-03-14T22:35:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Created silver_advanced_transformation.py CLI following silver_team_transformation.py pattern
- Successfully processed all 6 PLAYER_DATA_SEASONS (2020-2025) producing 47,447 total player-weeks
- Row count preservation verified for every season (no silent drops from left joins)
- QBR columns correctly NaN for non-QB rows; QBR data absent for 2024-2025 as expected
- NaN coverage logged for all 128 advanced stat columns per season

## Task Commits

Each task was committed atomically:

1. **Task 1: Create silver_advanced_transformation.py CLI** - `7562041` (feat)
2. **Task 2: Run full season range and verify output quality** - verification only, no code changes

## Files Created/Modified
- `scripts/silver_advanced_transformation.py` - CLI script orchestrating Bronze read, join, merge, rolling, and Silver write (581 lines)
- `data/silver/players/advanced/season={2020-2025}/` - Output Parquet files (6 seasons)

## Decisions Made
- Used synthetic player_gsis_id (name_team concatenation) for PFR and QBR data to enable apply_player_rolling groupby, since these sources lack GSIS IDs
- Dropped QBR raw `team` column before renaming `team_abb` -> `team` to prevent duplicate column creation
- When NGS receiving and passing both contain `avg_intended_air_yards`, keep first occurrence (receiving) and drop from second merge to avoid _x/_y suffixes
- PFR pressure match rate of 12% is expected and correct -- PFR pass data only covers QBs
- Team abbreviation normalization maps LAR->LA and WSH->WAS to prevent silent join failures

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed duplicate team column in QBR data**
- **Found during:** Task 1 (initial run)
- **Issue:** QBR Bronze data has both `team` (full name) and `team_abb` (abbreviation). Renaming `team_abb` -> `team` created duplicate `team` columns, causing merge failure.
- **Fix:** Drop original `team` column before rename.
- **Files modified:** scripts/silver_advanced_transformation.py
- **Verification:** Script runs without ValueError on QBR merge
- **Committed in:** 7562041

**2. [Rule 1 - Bug] Fixed NaN player_gsis_id breaking rolling windows**
- **Found during:** Task 1 (initial run)
- **Issue:** PFR and QBR data lack player_gsis_id. Using NaN as placeholder caused apply_player_rolling groupby to produce all-NaN rolling columns (0% coverage).
- **Fix:** Generate synthetic player_gsis_id from normalized name+team concatenation.
- **Files modified:** scripts/silver_advanced_transformation.py
- **Verification:** PFR rolling coverage 7.8%, QBR rolling coverage 6.8% (non-zero)
- **Committed in:** 7562041

**3. [Rule 1 - Bug] Fixed column collision across NGS merges**
- **Found during:** Task 1 (initial run)
- **Issue:** NGS receiving and passing both produce `ngs_avg_intended_air_yards`, causing pandas to create `_x`/`_y` suffix columns on merge.
- **Fix:** Added overlap detection that drops duplicate columns before each merge.
- **Files modified:** scripts/silver_advanced_transformation.py
- **Verification:** No `_x`/`_y` columns in output; clean column names throughout
- **Committed in:** 7562041

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All fixes necessary for correct data pipeline operation. No scope creep.

## Issues Encountered
None beyond the auto-fixed issues above.

## User Setup Required
None - no external service configuration required.

## Output Quality Summary

| Season | Rows | NGS Cols | PFR Cols | QBR Cols | Rolling Cols | Duplicates |
|--------|------|----------|----------|----------|-------------|------------|
| 2020 | 5,447 | 72 | 40 | 16 | 64 | 0 |
| 2021 | 5,698 | 72 | 40 | 16 | 64 | 0 |
| 2022 | 5,631 | 72 | 40 | 16 | 64 | 0 |
| 2023 | 5,653 | 72 | 40 | 16 | 64 | 0 |
| 2024 | 5,597 | 72 | 40 | 0 | 56 | 0 |
| 2025 | 19,421 | 72 | 40 | 0 | 56 | 0 |

QBR absent for 2024-2025 as expected per RESEARCH.md.

## Next Phase Readiness
- Silver advanced player profiles available for downstream Gold projections
- All 6 PROF requirements covered in output columns
- Pipeline ready for weekly automation via cron

---
*Phase: 17-advanced-player-profiles*
*Completed: 2026-03-14*
