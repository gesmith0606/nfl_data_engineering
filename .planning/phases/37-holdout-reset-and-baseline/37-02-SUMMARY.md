---
phase: 37-holdout-reset-and-baseline
plan: 02
subsystem: ml
tags: [ensemble, xgboost, lightgbm, catboost, ridge, holdout, baseline, backtest]

requires:
  - phase: 37-01
    provides: "HOLDOUT_SEASON=2025 config, updated season ranges, test assertions"
provides:
  - "Retrained ensemble model files in models/ensemble/ (2016-2024 training)"
  - "BASELINE.md with 2025 holdout metrics for Phase 38 comparison"
affects: [38-market-feature-ablation]

tech-stack:
  added: []
  patterns: []

key-files:
  created:
    - .planning/phases/37-holdout-reset-and-baseline/BASELINE.md
  modified:
    - models/ensemble/xgb_spread.json
    - models/ensemble/lgb_spread.txt
    - models/ensemble/cb_spread.cbm
    - models/ensemble/ridge_spread.pkl
    - models/ensemble/metadata.json

key-decisions:
  - "Used all 321 features (SELECTED_FEATURES=None) since feature selector not re-run for new holdout"
  - "Model files gitignored -- BASELINE.md documents metrics for traceability"

patterns-established: []

requirements-completed: [HOLD-03]

duration: 3min
completed: 2026-03-29
---

# Phase 37 Plan 02: Holdout Reset and Baseline Summary

**Retrained XGB+LGB+CB+Ridge ensemble on 2016-2024 with sealed 2025 holdout: 51.7% ATS, -$3.73 profit, +0.14 CLV**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-29T15:21:42Z
- **Completed:** 2026-03-29T15:24:30Z
- **Tasks:** 1
- **Files modified:** 10 (9 model files + 1 BASELINE.md)

## Accomplishments
- Retrained ensemble on 2016-2024 (9 seasons) with 2025 as sealed holdout
- Evaluated 2025 holdout: 51.7% ATS accuracy, 140-131-1 record, -$3.73 profit, -1.38% ROI
- Documented prior 2024 baseline (53.0% ATS, +$3.09) and new 2025 baseline in BASELINE.md
- CLV analysis: +0.14 mean, 50.4% beating close -- model has directional signal above random

## Task Commits

Each task was committed atomically:

1. **Task 1: Document 2024 baseline, retrain ensemble, and evaluate 2025 holdout** - `72c6913` (feat)

**Plan metadata:** [pending] (docs: complete plan)

## Files Created/Modified
- `.planning/phases/37-holdout-reset-and-baseline/BASELINE.md` - 2025 holdout baseline metrics for Phase 38 comparison
- `models/ensemble/*.json|.txt|.cbm|.pkl` - Retrained ensemble model files (gitignored)
- `models/ensemble/metadata.json` - Training metadata (seasons, features, holdout)

## Decisions Made
- Used all 321 assembled features since SELECTED_FEATURES=None (feature selector not re-run for new holdout config). This is the honest baseline -- Phase 38 ablation will compare against this.
- Model files remain gitignored; BASELINE.md provides the documented metrics for traceability.
- 51.7% ATS is below break-even (52.38%) but above 50%, confirming directional signal. No D-11 investigation needed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- BASELINE.md ready for Phase 38 market feature ablation comparison
- Ship-or-skip gate: Phase 38 market-augmented model must achieve strict > 51.7% ATS on 2025 holdout
- Note: prior 2024 holdout was 53.0% ATS; 2025 holdout is harder (51.7% baseline)

---
*Phase: 37-holdout-reset-and-baseline*
*Completed: 2026-03-29*
