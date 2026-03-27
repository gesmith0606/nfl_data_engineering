---
phase: 29-feature-selection
plan: 01
subsystem: ml
tags: [shap, xgboost, feature-selection, correlation-filtering, walk-forward-cv]

requires:
  - phase: 28-infrastructure-player-features
    provides: "SHAP 0.49.1 + CatBoost installed, player quality Silver features"
provides:
  - "FeatureSelectionResult dataclass for selection metadata"
  - "select_features_for_fold() — per-fold SHAP ranking + correlation filter + truncation"
  - "filter_correlated_features() — greedy pair removal with SHAP-informed resolution"
affects: [29-02, phase-30-ensemble]

tech-stack:
  added: []
  patterns: [per-fold-feature-selection, shap-treexplainer, greedy-correlation-filter]

key-files:
  created:
    - src/feature_selector.py
    - tests/test_feature_selector.py
  modified: []

key-decisions:
  - "TreeExplainer over KernelExplainer — exact for XGBoost, runs in seconds"
  - "20% random split for early stopping eval_set in quick SHAP model (not temporal — speed only)"
  - "SHAP subsample capped at 500 rows for speed; importance rankings stable at that size"
  - "sklearn train_test_split used for eval_set split inside select_features_for_fold"

patterns-established:
  - "Per-fold feature selection: select_features_for_fold takes train_data only, never full dataset"
  - "Holdout guard: _assert_no_holdout() raises ValueError before any computation"
  - "Greedy correlation filter: process pairs descending by r, skip already-dropped features"

requirements-completed: [FSEL-01, FSEL-02, FSEL-03, FSEL-04]

duration: 2min
completed: 2026-03-25
---

# Phase 29 Plan 01: Feature Selector Summary

**SHAP TreeExplainer feature ranking with greedy correlation filter (r > 0.90) and holdout guard, isolated per walk-forward CV fold**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-25T22:54:17Z
- **Completed:** 2026-03-25T22:56:59Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- FeatureSelectionResult dataclass with 9 fields including fold_seasons metadata (D-09)
- Correlation filter removes lower-SHAP feature from pairs above r=0.90, greedy from highest
- SHAP TreeExplainer computes mean absolute importance on 500-row subsample
- Holdout guard raises ValueError when 2024 data enters selection pipeline
- Zero-variance features excluded before SHAP computation (handles early folds missing Phase 28 features)
- 12 new tests covering FSEL-01 through FSEL-04, all passing; 461 total suite green

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for feature selector** - `5078f2e` (test)
2. **Task 1 (GREEN): Implement feature_selector.py** - `b922f7a` (feat)

## Files Created/Modified
- `src/feature_selector.py` — FeatureSelectionResult, select_features_for_fold, filter_correlated_features, _assert_no_holdout
- `tests/test_feature_selector.py` — 12 tests across 6 test classes

## Decisions Made
- Used TreeExplainer (not KernelExplainer) — exact for XGBoost, verified working with SHAP 0.49.1
- 20% random split for early stopping eval_set in the quick SHAP model (not temporal — this is just for early stopping efficiency)
- SHAP subsample capped at min(500, len(train_data)) rows for speed; importance rankings are stable at that size
- Used sklearn.model_selection.train_test_split for the eval_set split (imported inside function to keep module-level imports minimal)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all functions are fully implemented with real SHAP computation and correlation analysis.

## Next Phase Readiness
- `select_features_for_fold()` ready for Plan 02 to orchestrate across CV folds and candidate counts
- `filter_correlated_features()` exposed as standalone for potential reuse
- FeatureSelectionResult provides all metadata Plan 02 needs for `models/feature_selection/metadata.json`

---
*Phase: 29-feature-selection*
*Completed: 2026-03-25*
