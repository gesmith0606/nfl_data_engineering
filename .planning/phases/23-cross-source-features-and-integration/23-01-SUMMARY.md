---
phase: 23-cross-source-features-and-integration
plan: 01
subsystem: analytics
tags: [referee, penalties, standings, division-rank, expanding-window, game-context]

# Dependency graph
requires:
  - phase: 22-cross-source-features-and-integration
    provides: game_context.py with weather, rest, travel, coaching features
provides:
  - compute_referee_tendencies() with expanding-window penalty rate per referee
  - compute_playoff_context() with W-L-T, division rank, games behind, contention flag
  - _unpivot_schedules now carries referee, team_score, opp_score columns
  - SILVER_TEAM_S3_KEYS entries for referee_tendencies and playoff_context
affects: [23-02, silver-team-pipeline, prediction-models]

# Tech tracking
tech-stack:
  added: []
  patterns: [expanding-window-shift1-lag, division-rank-groupby, cumsum-standings]

key-files:
  created: []
  modified:
    - src/game_context.py
    - src/config.py
    - tests/test_game_context.py

key-decisions:
  - "Division rank uses sort by (win_pct desc, wins desc) within division, then sequential rank 1-4"
  - "Games behind uses straight win difference (not baseball half-game convention)"
  - "Late season contention threshold: win_pct >= 0.4 AND week >= 10"
  - "Referee penalty rate computed at game level (sum both teams' penalties), then expanding mean per referee-season"

patterns-established:
  - "Referee tendency pattern: normalize names with strip().title(), aggregate penalties at game_id level, expanding mean with shift(1)"
  - "Standings pattern: cumsum with shift(1) for entering-game record, division rank via groupby sort"

requirements-completed: [CROSS-01, CROSS-02]

# Metrics
duration: 12min
completed: 2026-03-19
---

# Phase 23 Plan 01: Referee Tendencies and Playoff Context Summary

**Referee penalty-rate expanding window and cumulative W-L-T standings with division rank, games behind, and late-season contention flag**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-19T01:16:55Z
- **Completed:** 2026-03-19T01:28:48Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- compute_referee_tendencies: expanding mean of total penalties per game per referee with shift(1) lag and strip().title() normalization
- compute_playoff_context: cumulative W-L-T record, division rank 1-4, games behind division leader, late_season_contention flag
- _unpivot_schedules extended with referee, team_score, opp_score columns
- 30 tests passing (22 existing + 8 new), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add unit tests (RED phase)** - `65459f6` (test)
2. **Task 2: Implement compute functions (GREEN phase)** - `b33fda6` (feat)

## Files Created/Modified
- `src/game_context.py` - Added compute_referee_tendencies(), compute_playoff_context(), extended _unpivot_schedules with score/referee columns, added TEAM_DIVISIONS import
- `src/config.py` - Added referee_tendencies and playoff_context to SILVER_TEAM_S3_KEYS
- `tests/test_game_context.py` - 8 new tests, 2 new fixtures for referee and playoff context

## Decisions Made
- Division rank uses sort by (win_pct desc, wins desc) within division for tiebreaking
- Games behind uses straight win difference (football convention, not baseball half-game)
- Late season contention: win_pct >= 0.4 AND week >= 10
- Referee penalties summed at game level (both teams), then expanding mean per referee-season with shift(1)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed column naming in cumulative standings**
- **Found during:** Task 2 (compute_playoff_context implementation)
- **Issue:** Using `col + "s"` produced "losss" instead of "losses" for the loss column
- **Fix:** Used explicit mapping dict `{"win": "wins", "loss": "losses", "tie": "ties"}`
- **Files modified:** src/game_context.py
- **Verification:** All 30 tests pass
- **Committed in:** b33fda6 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Trivial naming bug caught immediately by tests. No scope creep.

## Issues Encountered
None beyond the auto-fixed column naming bug.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Referee tendencies and playoff context ready for integration into Silver pipeline (Plan 02)
- All functions follow existing game_context.py patterns and are joinable on [team, season, week]
- Config S3 keys ready for Silver team pipeline persistence

---
*Phase: 23-cross-source-features-and-integration*
*Completed: 2026-03-19*
