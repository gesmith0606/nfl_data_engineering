---
phase: 60-data-quality
plan: 01
subsystem: data-pipeline
tags: [sleeper-api, roster-refresh, position-classification, change-log, tdd, pytest, pandas]

# Dependency graph
requires:
  - phase: v3.2-website
    provides: "Gold preseason projections parquet with player_name + recent_team columns"
  - phase: existing
    provides: "scripts/refresh_rosters.py baseline (team-only refresh), SLEEPER_TO_NFLVERSE_TEAM mapping"
provides:
  - "build_roster_mapping(players) -> Dict[name, {team, position}]"
  - "update_rosters(df, mapping) -> (updated_df, changes_df) with position + team correction"
  - "log_changes(changes_df, log_path) -> timestamped append-only audit trail"
  - "roster_changes.log artifact for Phase 61 news/sentiment operators to review"
  - "13-test regression suite in tests/test_data_quality.py"
affects:
  - "Phase 60-02 (sanity check): can rely on up-to-date positions in Gold"
  - "Phase 60-03 (CI gate): daily-sentiment.yml cron will now fix positions on every run"
  - "Phase 61 (news/sentiment): player position lookups match Sleeper source of truth"
  - "Website projections UI: kickers/RB/WR/TE/QB labels always match Sleeper"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-pass Sleeper refresh: team + position corrected in one update_rosters() call"
    - "Active-wins collision resolution for Sleeper full_name duplicates"
    - "Append-only change log with timestamped section headers even on no-op runs"
    - "Backward-compatible extension: legacy build_team_mapping/update_teams kept untouched"

key-files:
  created:
    - "tests/test_data_quality.py"
  modified:
    - "scripts/refresh_rosters.py"

key-decisions:
  - "Added update_rosters() alongside legacy update_teams() for backward compatibility instead of replacing in place"
  - "log_changes() writes a header even on empty/dry-run runs so the audit trail captures every refresh invocation"
  - "Active-status preference runs regardless of position filter: defense-in-depth against future FANTASY_POSITIONS expansion"

patterns-established:
  - "Sleeper refresh extension pattern: build_*_mapping -> update_* -> log_* pipeline callable from main() or programmatically"
  - "DQAL test aliases: canonical test names (test_position_update etc.) alongside implementation-specific names keep frontmatter req mapping explicit"

requirements-completed: [DQAL-01, DQAL-02]

# Metrics
duration: 5min
completed: 2026-04-17
---

# Phase 60 Plan 01: Roster Refresh Position Updates + Change Logging Summary

**Extended scripts/refresh_rosters.py so the daily Sleeper cron now corrects Gold projection positions as well as teams, with a timestamped roster_changes.log audit trail and Active-wins collision handling.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-17T17:58:32Z
- **Completed:** 2026-04-17T18:03:22Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `build_roster_mapping(players)` produces `{team, position}` per player with LAR->LA normalization and Active-wins collision resolution (Pitfall 1 mitigation from 60-RESEARCH.md).
- `update_rosters(df, mapping)` mutates `recent_team` AND `position` in the Gold parquet in a single pass, returning a changes DataFrame with `old_position`/`new_position` surfaced only when position actually changed (satisfies DQAL-01 + DQAL-02 together).
- `log_changes(changes_df, log_path)` appends a timestamped section to `roster_changes.log` on every invocation -- including no-op and dry-run paths -- giving operators a continuous audit trail (D-02).
- `main()` rewired to call the new trio; prints position-reclassification breakdowns and persists the log after save.
- 13-test pytest suite covering team-only changes, position-only changes, combined changes, unmapped-player safety, empty-changes logging, append semantics, and DQAL-aligned aliases (`test_position_update`, `test_team_update`, `test_name_collision_handling`, `test_roster_changes_log`).
- Legacy `build_team_mapping` and `update_teams` preserved untouched for any external callers.

## Task Commits

Each task was committed atomically following the TDD RED/GREEN cycle:

1. **Task 1: Create test scaffolding (RED)** - `d4b165f` (test)
2. **Task 2: Extend refresh_rosters.py with position update, change logging, collision handling (GREEN)** - `dbaf5f7` (feat)

_Note: Refactor step was not required; implementation landed clean on first pass._

## Files Created/Modified
- `tests/test_data_quality.py` (created, 342 lines) - 13 unit tests covering build_roster_mapping, update_rosters, and log_changes; mock Sleeper payload with name collision and non-fantasy position entries.
- `scripts/refresh_rosters.py` (modified, +190/-10) - Added build_roster_mapping, update_rosters, log_changes; rewired main() to call the new trio and persist the log on every path; legacy functions untouched.

## Decisions Made
- **Keep legacy functions:** `build_team_mapping` and `update_teams` retained as-is. The plan allowed replacement but Phase 60-02 (sanity check) and external callers may import them; backward-compat is cheap insurance.
- **Log on every run:** `log_changes` is invoked even when `changes_df` is empty and even on `--dry-run`, so every refresh invocation is visible in `roster_changes.log`. This was in the plan's example code but implementing it consistently across all four exit paths of `main()` required a deliberate choice.
- **Active-wins for all collisions:** The Active-status preference runs even though non-fantasy positions are already filtered earlier. Belt-and-suspenders against a future FANTASY_POSITIONS expansion (e.g., IDP) that would suddenly start admitting collisions.

## Deviations from Plan

None - plan executed exactly as written. Minor additions:
- Added `test_update_rosters_leaves_unmapped_players_untouched` and `test_log_changes_appends_rather_than_overwrites` beyond the 7 tests specified in the plan's behavior block, for stronger safety-net coverage. Also added 4 DQAL-aligned alias tests (`test_position_update`, `test_team_update`, `test_name_collision_handling`, `test_roster_changes_log`) so the requirement traceability table in 60-RESEARCH.md maps 1:1 to named tests. Net: 13 tests instead of 7, all pass.

## Issues Encountered

- **Pre-existing unrelated failure:** `tests/test_news_service.py::TestGetPlayerNews::test_returns_items_for_matching_player` fails on `main` both before and after this plan's changes (`assert None == 'Mahomes limited in practice'`). Verified by stashing all changes and re-running the test in isolation. Out of scope for Plan 60-01; flagged for Phase 61 (News & Sentiment Live) cleanup. All other 1520 tests pass; this plan's 13 new tests all pass.

## Deferred Issues

None.

## Known Stubs

None. All three new functions are fully wired into `main()`; there are no placeholder values, empty returns, or TODO markers in the committed code.

## Threat Flags

None. The plan's threat register (T-60-01 through T-60-04) covered all trust boundaries touched; no new surface was introduced.

## User Setup Required

None - no external service configuration required. The daily-sentiment GHA workflow already invokes `refresh_rosters.py`; the extended behavior ships automatically on next cron tick.

## Verification Evidence

- `python -m pytest tests/test_data_quality.py -x -v` -> 13 passed, 10 warnings in 0.77s
- `python scripts/refresh_rosters.py --season 2026 --dry-run` -> Runs clean. Fetches 11,580 Sleeper entries, builds mapping for 778 players with teams, detects no changes (current Gold is already in sync post-team-only refresh). Writes timestamped "No changes detected." entry to roster_changes.log.
- `grep -c "def build_roster_mapping(" scripts/refresh_rosters.py` -> 1
- `grep -c "def update_rosters(" scripts/refresh_rosters.py` -> 1
- `grep -c "def log_changes(" scripts/refresh_rosters.py` -> 1
- `grep -c "def build_team_mapping(" scripts/refresh_rosters.py` -> 1 (backward-compat preserved)
- `grep -c "def update_teams(" scripts/refresh_rosters.py` -> 1 (backward-compat preserved)
- Full-suite regression: 1520 passed, 1 failed (pre-existing news_service, unrelated), 1 skipped in 78.93s.

## Next Phase Readiness

- Plan 60-02 (sanity check enhancements) can depend on Gold positions matching Sleeper.
- Plan 60-03 (CI gate) can wire the sanity check into deploy-web.yml knowing roster refresh runs daily with logged diffs.
- `roster_changes.log` is ignored by `.gitignore` (`*.log`) and lives alongside the repo root; operators inspect it manually or via `tail -f` during cron troubleshooting.

## TDD Gate Compliance

- RED gate: `test(60-01): add failing tests for roster refresh position update and logging` - `d4b165f`
- GREEN gate: `feat(60-01): update rosters with position and change logging from Sleeper` - `dbaf5f7`
- REFACTOR gate: Skipped (not needed; implementation was clean on first pass).

## Self-Check: PASSED

- FOUND: tests/test_data_quality.py
- FOUND: scripts/refresh_rosters.py
- FOUND: .planning/phases/60-data-quality/60-01-SUMMARY.md
- FOUND: commit d4b165f (test - RED phase)
- FOUND: commit dbaf5f7 (feat - GREEN phase)

---
*Phase: 60-data-quality*
*Completed: 2026-04-17*
