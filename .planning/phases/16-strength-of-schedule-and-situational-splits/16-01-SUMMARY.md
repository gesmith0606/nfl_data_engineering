---
phase: 16-strength-of-schedule-and-situational-splits
plan: 01
subsystem: analytics
tags: [sos, epa, opponent-adjusted, rankings, rolling-windows, pandas]

# Dependency graph
requires:
  - phase: 15-pbp-team-metrics-and-tendencies
    provides: compute_team_epa(), _filter_valid_plays(), apply_team_rolling() in team_analytics.py
provides:
  - _build_opponent_schedule() function for opponent mapping from PBP
  - compute_sos_metrics() function producing adj_off_epa, adj_def_epa, off_sos_score, def_sos_score, off_sos_rank, def_sos_rank
  - TEAM_DIVISIONS dict (32 teams, 8 divisions) in config.py
  - SILVER_TEAM_S3_KEYS entries for 'sos' and 'situational'
affects: [16-02-situational-splits, silver-team-transformation, projection-engine]

# Tech tracking
tech-stack:
  added: []
  patterns: [lagged-opponent-adjustment, per-game-opponent-epa-lookup]

key-files:
  created: []
  modified:
    - src/team_analytics.py
    - src/config.py
    - tests/test_team_analytics.py

key-decisions:
  - "SOS uses per-game opponent EPA from the specific week faced, not cumulative season-to-date"
  - "Bye weeks produce no row in SOS output (skip, not NaN fill)"
  - "Rankings use ascending=False with method=min so rank 1 = hardest schedule"

patterns-established:
  - "Lagged SOS pattern: iterate (team, season) groups, collect prior opponents, lookup their EPA"
  - "Opponent schedule extraction: drop_duplicates on (game_id, posteam) to get one row per team-game"

requirements-completed: [SOS-01, SOS-02]

# Metrics
duration: 3min
completed: 2026-03-14
---

# Phase 16 Plan 01: SOS Metrics Summary

**Opponent-adjusted EPA with lagged schedule difficulty rankings using per-game opponent EPA lookup and rolling windows**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-14T18:45:19Z
- **Completed:** 2026-03-14T18:48:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- TEAM_DIVISIONS dict with 32 teams across 8 divisions (4 each) added to config.py
- compute_sos_metrics() produces opponent-adjusted EPA where week 1 adj == raw and week 2+ uses lagged opponent strength
- SOS rankings 1-N per season-week with rank 1 = hardest schedule
- Rolling windows (_roll3, _roll6, _std) applied to all SOS stat columns
- 10 new tests (4 config + 6 SOS), full suite at 235 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Config updates and SOS test scaffolding** - `bba83a2` (test)
2. **Task 2: Implement SOS computation functions** - `2df11ee` (feat)

## Files Created/Modified
- `src/config.py` - Added TEAM_DIVISIONS dict and 'sos'/'situational' entries in SILVER_TEAM_S3_KEYS
- `src/team_analytics.py` - Added _build_opponent_schedule() and compute_sos_metrics() functions
- `tests/test_team_analytics.py` - Added TestConfigSOS (4 tests) and TestSOS (6 tests) classes with deterministic 4-team fixture

## Decisions Made
- Used per-game opponent EPA from specific week faced (not cumulative season-to-date) for more granular SOS signal
- Bye weeks skip entirely (no row) rather than filling with NaN, consistent with compute_team_epa() behavior
- Rankings use ascending=False, method="min" so rank 1 = hardest schedule (highest mean opponent EPA)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SOS metrics ready for silver_team_transformation.py integration (Plan 16-02)
- compute_sos_metrics() can be called with raw PBP DataFrame
- SILVER_TEAM_S3_KEYS already has 'sos' and 'situational' entries for output paths

---
*Phase: 16-strength-of-schedule-and-situational-splits*
*Completed: 2026-03-14*
