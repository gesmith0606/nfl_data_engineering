---
phase: 41-accuracy-improvements
plan: 02
subsystem: ml
tags: [lightgbm, ridge, ensemble, stacking, player-models, walk-forward-cv]

# Dependency graph
requires:
  - phase: 41-01
    provides: "SHAP feature selection per stat-type group, ratio/delta features"
provides:
  - "XGB+LGB+Ridge ensemble stacking per position per stat"
  - "assemble_player_oof_matrix for row-index OOF merge"
  - "CLI --stage flag for two-stage evaluation"
  - "Two-stage ablation report (features-only vs ensemble)"
affects: [42-confidence-intervals, player-model-evaluation]

# Tech tracking
tech-stack:
  added: [lightgbm (player models), sklearn.linear_model.RidgeCV, joblib]
  patterns: [two-stage ship gate, per-stat ensemble stacking, OOF matrix assembly on row index]

key-files:
  created: []
  modified:
    - src/player_model_training.py
    - scripts/train_player_models.py
    - tests/test_player_model_training.py

key-decisions:
  - "XGB+LGB+Ridge (no CatBoost) for player ensemble — matches D-10 design"
  - "LGB params adapted per stat type: TD/turnover get shallower trees (max_depth=3, min_child_samples=30)"
  - "Ensemble stacking only runs for SKIP positions from Stage 1 to avoid unnecessary compute"

patterns-established:
  - "Two-stage ship gate: features-only first, ensemble only for SKIPs"
  - "assemble_player_oof_matrix joins on row index (not game_id) for player-level data"

requirements-completed: [ACCY-04]

# Metrics
duration: 5min
completed: 2026-03-31
---

# Phase 41 Plan 02: Ensemble Stacking Summary

**XGB+LGB+Ridge ensemble stacking per position with two-stage CLI evaluation and 6 new unit tests (638 total passing)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-31T12:26:41Z
- **Completed:** 2026-03-31T12:31:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- LGB model support with stat-type-specific hyperparameters (shallower for TD/turnover)
- Full ensemble stacking pipeline: XGB walk-forward CV + LGB walk-forward CV + Ridge meta-learner per stat
- CLI --stage flag (features-only / ensemble / both) with separate JSON reports per stage
- Two-stage ablation report comparing Heuristic vs XGB-Only vs Ensemble per position
- 6 new unit tests covering LGB kwargs, params, OOF matrix assembly, and ensemble stacking

## Task Commits

Each task was committed atomically:

1. **Task 1: Add LGB model support and ensemble stacking functions** - `11b9fc6` (test) + `74bb946` (feat)
2. **Task 2: Extend CLI with --stage flag and two-stage evaluation** - `a278cf2` (feat)

_Note: Task 1 followed TDD with separate RED and GREEN commits_

## Files Created/Modified
- `src/player_model_training.py` - Added 5 new functions: _player_lgb_fit_kwargs, get_lgb_params_for_stat, assemble_player_oof_matrix, train_player_ridge_meta, player_ensemble_stacking
- `scripts/train_player_models.py` - Added --stage CLI flag, Stage 1/2 evaluation flow, two-stage ablation report
- `tests/test_player_model_training.py` - 6 new tests for LGB/ensemble functionality

## Decisions Made
- XGB+LGB+Ridge (no CatBoost) for player ensemble per D-10 design decision
- LGB TD/turnover stats use max_depth=3, min_child_samples=30, n_estimators=300 (analogous to XGB stat-type tuning)
- Ensemble stacking only runs for SKIP positions from Stage 1 to save compute
- OOF matrix assembly uses row index (not game_id) consistent with player_walk_forward_cv contract

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added missing 'carries' column to ensemble stacking test data**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Synthetic test data for RB ensemble stacking lacked 'carries' column, which is in POSITION_STAT_PROFILE["RB"]
- **Fix:** Added carries column to test fixture DataFrame
- **Files modified:** tests/test_player_model_training.py
- **Verification:** All 6 new tests pass
- **Committed in:** 74bb946 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test data fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functions are fully wired with real implementations.

## Next Phase Readiness
- Ensemble stacking infrastructure ready for Phase 42 (confidence intervals with MAPIE)
- Two-stage evaluation framework enables independent assessment of features vs ensemble contribution
- 638 tests passing (622 baseline + 10 from Plan 01 + 6 from Plan 02)

---
*Phase: 41-accuracy-improvements*
*Completed: 2026-03-31*
