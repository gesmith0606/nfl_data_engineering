---
phase: 25-feature-assembly-and-model-training
plan: 01
subsystem: ml-pipeline
tags: [xgboost, feature-engineering, differential-features, pandas, parquet]

# Dependency graph
requires:
  - phase: 22-prediction-data-foundation
    provides: "8 Silver team sources (pbp_metrics, tendencies, sos, situational, pbp_derived, game_context, referee_tendencies, playoff_context)"
provides:
  - "assemble_game_features() for game-level differential feature assembly"
  - "get_feature_columns() for label-safe feature selection"
  - "assemble_multiyear_features() for multi-season training data"
  - "CONSERVATIVE_PARAMS, PREDICTION_SEASONS, LABEL_COLUMNS config constants"
  - "xgboost, optuna, scikit-learn dependencies installed"
affects: [25-02-spread-model, 25-03-totals-model, game-prediction-pipeline]

# Tech tracking
tech-stack:
  added: [xgboost>=2.1.4, optuna>=4.0, scikit-learn>=1.5]
  patterns: [differential-features, game-level-assembly, label-exclusion-guard]

key-files:
  created:
    - src/feature_engineering.py
    - tests/test_feature_engineering.py
    - models/.gitkeep
  modified:
    - src/config.py
    - requirements.txt
    - .gitignore

key-decisions:
  - "Vectorized diff computation with pd.concat to avoid DataFrame fragmentation (3355 warnings reduced to 33)"
  - "Inner join with REG-filtered schedules ensures only regular season games in output"
  - "322 differential columns from 8 Silver sources; 337 total feature columns including context"

patterns-established:
  - "Differential features: diff_{col} = home_metric - away_metric for all numeric Silver columns"
  - "Label exclusion: LABEL_COLUMNS in config.py as single source of truth for forbidden features"
  - "Game assembly: game_context as base table (has game_id + is_home bridge)"

requirements-completed: [FEAT-01, FEAT-02, FEAT-04]

# Metrics
duration: 4min
completed: 2026-03-21
---

# Phase 25 Plan 01: Feature Assembly Summary

**Game-level differential feature assembly from 8 Silver team sources producing 272 REG game rows with 322 diff_ columns and 337 total features per season**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-21T02:01:41Z
- **Completed:** 2026-03-21T02:05:31Z
- **Tasks:** 1 (TDD: RED + GREEN + REFACTOR)
- **Files modified:** 6

## Accomplishments
- Feature assembly module transforms per-team-per-week Silver data into per-game differential rows
- 322 diff_ columns computed as home_metric minus away_metric across all 8 Silver sources
- Temporal lag verified -- no future data leaks into features; Week 1 NaN handled gracefully
- Label exclusion guard ensures scores, spreads, and results never appear in feature set
- XGBoost, optuna, scikit-learn dependencies installed and pinned

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests + config + deps** - `b403ec5` (test)
2. **Task 1 (GREEN+REFACTOR): Feature engineering implementation** - `ad629a9` (feat)

## Files Created/Modified
- `src/feature_engineering.py` - Game-level differential feature assembly (assemble_game_features, get_feature_columns, assemble_multiyear_features)
- `tests/test_feature_engineering.py` - 11 tests for differentials, labels, lag, early-season, row count
- `src/config.py` - CONSERVATIVE_PARAMS, PREDICTION_SEASONS, HOLDOUT_SEASON, LABEL_COLUMNS, SILVER_TEAM_LOCAL_DIRS, MODEL_DIR
- `requirements.txt` - Added xgboost>=2.1.4, optuna>=4.0, scikit-learn>=1.5
- `.gitignore` - Added models/ directory exclusion
- `models/.gitkeep` - Model output directory placeholder

## Decisions Made
- Used game_context as base table for assembly (contains game_id + is_home bridge columns)
- Inner join with REG-filtered schedules naturally eliminates playoff games
- Vectorized diff computation via pd.concat instead of per-column assignment (eliminates fragmentation warnings)
- 337 feature columns (322 diff_ + 15 context) -- larger than the 180 estimated in planning due to PBP-derived having 164 columns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Performance] Fixed DataFrame fragmentation in differential computation**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Per-column assignment of 322 diff_ columns generated 3,355 PerformanceWarnings
- **Fix:** Batch-computed all differentials into a dict, then used pd.concat(axis=1) to add at once
- **Files modified:** src/feature_engineering.py
- **Verification:** Warnings reduced from 3,355 to 33; all 11 tests still pass
- **Committed in:** ad629a9 (GREEN+REFACTOR commit)

---

**Total deviations:** 1 auto-fixed (1 performance bug)
**Impact on plan:** Essential performance fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Feature assembly module ready for Plans 25-02 (spread model) and 25-03 (totals model)
- assemble_multiyear_features() provides the training data interface
- CONSERVATIVE_PARAMS provides XGBoost defaults for both models
- 371 total tests passing (11 new + 360 existing)

---
*Phase: 25-feature-assembly-and-model-training*
*Completed: 2026-03-21*
