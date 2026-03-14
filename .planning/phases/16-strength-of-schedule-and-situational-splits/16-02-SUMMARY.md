---
phase: 16-strength-of-schedule-and-situational-splits
plan: 02
subsystem: analytics
tags: [situational-splits, epa, home-away, divisional, game-script, rolling-windows, pandas]

# Dependency graph
requires:
  - phase: 16-01
    provides: compute_sos_metrics(), TEAM_DIVISIONS, _filter_valid_plays(), apply_team_rolling()
provides:
  - compute_situational_splits() function producing 12 EPA split columns with rolling windows
  - Silver team CLI producing 4 datasets per season (pbp_metrics, tendencies, sos, situational)
affects: [projection-engine, draft-optimizer, silver-team-transformation]

# Tech tracking
tech-stack:
  added: []
  patterns: [wide-format-before-rolling, 7-point-game-script-threshold, division-lookup-tagging]

key-files:
  created: []
  modified:
    - src/team_analytics.py
    - scripts/silver_team_transformation.py
    - tests/test_team_analytics.py

key-decisions:
  - "Game script uses 7-point threshold: leading >= 7, trailing <= -7, neutral excluded"
  - "Pivot to wide format before rolling windows to avoid cross-situation contamination"
  - "Non-applicable situations produce NaN (not zero) for clean downstream filtering"

patterns-established:
  - "Situational split pattern: tag plays, filter by tag, groupby mean EPA, merge wide, then roll"
  - "CLI produces all 4 Silver team datasets in a single pass per season"

requirements-completed: [SIT-01, SIT-02, SIT-03]

# Metrics
duration: 4min
completed: 2026-03-14
---

# Phase 16 Plan 02: Situational Splits Summary

**Home/away, divisional, and game script EPA splits with rolling windows wired into Silver team CLI producing 4 datasets per season**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-14T18:50:58Z
- **Completed:** 2026-03-14T18:54:38Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- compute_situational_splits() produces 12 EPA split columns (home/away offense+defense, divisional/non-divisional offense+defense, leading/trailing offense+defense) per team-week in wide format
- Rolling windows (_roll3, _roll6, _std) applied to all 12 split columns (51 total output columns)
- Silver team CLI now produces 4 datasets per season: pbp_metrics, tendencies, sos, situational
- Verified on real 2024 data: 544 rows, 32 teams, all 4 Parquet files saved locally and to S3
- 11 new tests (TestSituational: 9, TestIdempotency: 2), full suite at 246 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Situational splits computation with tests** - `794acb1` (feat)
2. **Task 2: Wire SOS and situational into Silver team CLI** - `c1fcae9` (feat)

## Files Created/Modified
- `src/team_analytics.py` - Added compute_situational_splits() with home/away, divisional, game script EPA splits
- `scripts/silver_team_transformation.py` - Wired compute_sos_metrics and compute_situational_splits into CLI pipeline
- `tests/test_team_analytics.py` - Added TestSituational (9 tests) and TestIdempotency (2 tests) with 4-team divisional fixture

## Decisions Made
- Game script uses 7-point threshold (leading >= 7, trailing <= -7); neutral plays excluded from both leading and trailing
- Wide format pivot before rolling windows to prevent cross-situation contamination per RESEARCH.md guidance
- Non-applicable situations produce NaN naturally (e.g., home_off_epa is NaN when team plays away)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All Phase 16 outputs complete: SOS metrics + situational splits + PBP metrics + tendencies
- 4 Silver team datasets produced per season via single CLI command
- Ready for Phase 17 (advanced player profiles) or projection engine integration

---
*Phase: 16-strength-of-schedule-and-situational-splits*
*Completed: 2026-03-14*
