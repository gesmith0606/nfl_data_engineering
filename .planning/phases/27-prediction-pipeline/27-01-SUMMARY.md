---
phase: 27-prediction-pipeline
plan: 01
subsystem: predictions
tags: [xgboost, edge-detection, confidence-tiers, parquet, cli]

requires:
  - phase: 25-model-training
    provides: trained XGBoost spread and total models with load_model()
  - phase: 25-model-training
    provides: assemble_game_features() for 337-column feature vectors
provides:
  - Weekly prediction pipeline script (generate_predictions.py)
  - Edge detection (model line - Vegas line) for spread and total
  - Confidence tier classification (high/medium/low)
  - Gold Parquet output at data/gold/predictions/
affects: [documentation, production-pipeline]

tech-stack:
  added: []
  patterns: [edge-detection-convention, confidence-tier-thresholds]

key-files:
  created:
    - scripts/generate_predictions.py
    - tests/test_generate_predictions.py
  modified: []

key-decisions:
  - "Edge convention: spread_edge = model_spread - vegas_spread (positive = more home advantage than Vegas)"
  - "Confidence tiers at fixed thresholds: high >= 3.0, medium >= 1.5, low < 1.5"
  - "NaN Vegas lines produce NaN edges and None tiers (no crashes)"
  - "Output sorted by max(abs(spread_edge), abs(total_edge)) descending, NaN last"

patterns-established:
  - "Edge detection: model_line - vegas_line for both spread and total"
  - "Tier classification via classify_tier() with absolute edge thresholds"

requirements-completed: [PRED-01, PRED-02, PRED-03]

duration: 5min
completed: 2026-03-22
---

# Phase 27 Plan 01: Prediction Pipeline Summary

**Weekly prediction pipeline with edge detection vs Vegas lines, confidence tiers (high/medium/low at 3.0/1.5 thresholds), and Gold Parquet output**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-22T01:23:50Z
- **Completed:** 2026-03-22T01:28:26Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Built generate_predictions.py with CLI (--season, --week, --model-dir) for weekly game predictions
- Edge detection computes model_spread - vegas_spread and model_total - vegas_total with confidence tier classification
- 13 tests covering tier classification, edge computation, missing Vegas lines, sort order, output schema, Gold Parquet round-trip, and empty week handling
- Full test suite at 439 tests passing with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Tests and core prediction pipeline** - `7800535` (test: RED) + `cce382a` (feat: GREEN)
2. **Task 2: Full suite regression and integration smoke test** - `9752daa` (test)

_Note: Task 1 followed TDD with separate RED and GREEN commits_

## Files Created/Modified
- `scripts/generate_predictions.py` - Weekly prediction pipeline with edge detection, tier classification, and Gold Parquet output
- `tests/test_generate_predictions.py` - 13 tests for classify_tier, generate_week_predictions, integration

## Decisions Made
- Edge convention: positive spread_edge means model sees more home advantage than Vegas
- Fixed tier thresholds (3.0/1.5) matching D-05 specification from research phase
- NaN Vegas lines handled gracefully (NaN edge, None tier) rather than raising errors
- Output sorted by max edge magnitude so strongest plays appear first

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Prediction pipeline complete; v1.4 ML Game Prediction milestone ready for final docs update
- Models must be trained (scripts/train_models.py) before running predictions
- This is the last plan in Phase 27 and the final phase of the v1.4 milestone

## Self-Check: PASSED

All files exist and all commit hashes verified.

---
*Phase: 27-prediction-pipeline*
*Completed: 2026-03-22*
