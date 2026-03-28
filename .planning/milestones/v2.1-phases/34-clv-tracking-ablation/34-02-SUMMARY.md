---
phase: 34-clv-tracking-ablation
plan: 02
subsystem: prediction
tags: [ablation, shap, feature-selection, market-data, ensemble, xgboost]

# Dependency graph
requires:
  - phase: 34-01
    provides: "CLV evaluation functions (evaluate_clv, compute_clv_by_tier, compute_clv_by_season)"
  - phase: 33
    provides: "opening_spread and opening_total in _PRE_GAME_CONTEXT feature set"
  - phase: 30
    provides: "P30 stacking ensemble (XGB+LGB+CB+Ridge) in models/ensemble/"
provides:
  - "Ablation orchestrator script comparing P30 baseline vs market-augmented ensemble"
  - "Ship-or-skip decision logic with strict > comparison (D-08)"
  - "SHAP importance report with opening_spread dominance detection (D-12/D-13)"
  - "apply_ship_decision with shutil.copytree copy semantics"
affects: [v2.2-betting-framework, model-evaluation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ablation pattern: separate model directory, compare on sealed holdout, ship only if improved"
    - "Feature selection reimplemented in script using src/feature_selector.py (no script imports)"

key-files:
  created:
    - scripts/ablation_market_features.py
    - tests/test_ablation.py
  modified: []

key-decisions:
  - "Feature selection logic reimplemented in ablation script using src/feature_selector.py directly, avoiding anti-pattern of importing from scripts/"
  - "Ablation trains to models/ensemble_ablation/ to protect production P30 ensemble"
  - "Ship-or-skip uses strict > (any improvement ships per D-08)"

patterns-established:
  - "Ablation script pattern: 5-step orchestration (baseline, selection, retrain, eval, report)"
  - "Copy semantics: shutil.copytree with dirs_exist_ok=True for model promotion"

requirements-completed: [LINE-04]

# Metrics
duration: 4min
completed: 2026-03-28
---

# Phase 34 Plan 02: Market Feature Ablation Summary

**Ablation script comparing P30 baseline vs market-feature-augmented ensemble with SHAP importance, opening_spread dominance detection, and ship-or-skip decision logic**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-28T14:30:19Z
- **Completed:** 2026-03-28T14:34:31Z
- **Tasks:** 1 (TDD: tests + implementation)
- **Files created:** 2

## Accomplishments
- Ablation script with 5-step orchestration: baseline eval, feature selection, retrain, holdout eval, comparison report
- SHAP importance report with opening_spread dominance check (>30% threshold per D-12/D-13)
- D-14 behavior: documents "model already captures market signal indirectly" when dominance + SKIP
- 17 new tests covering decision logic, report format, directory safety, and copy semantics
- Full suite: 571 tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ablation script with tests** - `e77c6ea` (feat - TDD RED+GREEN)

## Files Created/Modified
- `scripts/ablation_market_features.py` - 5-step ablation orchestrator with CLI (--dry-run, --counts, --correlation-threshold)
- `tests/test_ablation.py` - 17 tests: TestShipOrSkip, TestAblationReport, TestAblationPaths, TestApplyShipDecision

## Decisions Made
- Feature selection reimplemented in ablation script using `src/feature_selector.py` directly (anti-pattern of importing from scripts/ avoided)
- Ablation trains to `models/ensemble_ablation/` (never `models/ensemble/`) per Pitfall 4
- `apply_ship_decision` uses `shutil.copytree(ABLATION_DIR, ENSEMBLE_DIR, dirs_exist_ok=True)` for atomic promotion

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all functions fully implemented with proper imports and logic.

## Next Phase Readiness
- Phase 34 complete: CLV tracking (Plan 01) + market feature ablation (Plan 02)
- To run ablation: `python scripts/ablation_market_features.py` (requires Silver data for feature assembly)
- Dry-run mode: `python scripts/ablation_market_features.py --dry-run` (baseline eval only)

---
*Phase: 34-clv-tracking-ablation*
*Completed: 2026-03-28*
