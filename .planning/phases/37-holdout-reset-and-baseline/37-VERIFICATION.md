---
phase: 37-holdout-reset-and-baseline
verified: 2026-03-29T16:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
---

# Phase 37: Holdout Reset and Baseline Verification Report

**Phase Goal:** The evaluation framework uses 2025 as the sealed holdout with a documented ensemble baseline, enabling honest model comparison going forward
**Verified:** 2026-03-29
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | HOLDOUT_SEASON is 2025 in config.py | VERIFIED | `src/config.py` line 408: `HOLDOUT_SEASON = 2025` |
| 2 | TRAINING_SEASONS, VALIDATION_SEASONS, PREDICTION_SEASONS are computed from HOLDOUT_SEASON, not hardcoded | VERIFIED | Lines 409-411 use `range(2016, HOLDOUT_SEASON + 1)`, `range(2016, HOLDOUT_SEASON)`, `range(2019, HOLDOUT_SEASON)` |
| 3 | Holdout guard rejects 2025 data in training folds | VERIFIED | `ensemble_training.py` line 349: `train_data = all_data[all_data["season"] < HOLDOUT_SEASON]`; metadata.json confirms training_seasons=[2016..2024], holdout_season=2025 |
| 4 | Running backtest --holdout produces ATS accuracy, profit, and CLV metrics | VERIFIED | BASELINE.md contains exact metrics: 51.7% ATS, -$3.73 profit, -1.38% ROI, +0.14 mean CLV, CLV by tier table |
| 5 | Baseline metrics are documented for Phase 38 comparison | VERIFIED | BASELINE.md documents prior 2024 baseline (53.0% ATS) and new 2025 baseline with full metrics; ship-or-skip gate explicitly stated |
| 6 | No test file hardcodes 2024 as the holdout season | VERIFIED | `grep -rn "holdout_season=2024"` returns zero matches in test source files |
| 7 | All tests pass with the new holdout season | VERIFIED | 594 tests pass (full test suite) |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/config.py` | Holdout config with derived season ranges | VERIFIED | HOLDOUT_SEASON=2025; TRAINING_SEASONS, VALIDATION_SEASONS, PREDICTION_SEASONS all derived |
| `tests/test_model_training.py` | Updated holdout references | VERIFIED | Imports HOLDOUT_SEASON, TRAINING_SEASONS; no hardcoded 2024 holdout values |
| `tests/test_ensemble_training.py` | Updated training range | VERIFIED | Imports TRAINING_SEASONS; uses `[s for s in TRAINING_SEASONS if s >= 2018]` |
| `tests/test_prediction_backtester.py` | Updated holdout references | VERIFIED | Imports HOLDOUT_SEASON, TRAINING_SEASONS; all ~15 occurrences replaced |
| `tests/test_feature_selector.py` | Updated docstring removing hardcoded 2024 | VERIFIED | Imports HOLDOUT_SEASON; stale "(2024)" removed from docstrings |
| `models/ensemble/` | Retrained ensemble model files | VERIFIED | xgb_spread.json, lgb_spread.txt, cb_spread.cbm, ridge_spread.pkl, metadata.json (and total variants) present |
| `.planning/phases/37-holdout-reset-and-baseline/BASELINE.md` | Documented 2025 holdout baseline metrics | VERIFIED | Contains ATS Accuracy, Record, Profit, ROI, CLV metrics; both 2024 prior and 2025 new baselines documented |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/config.py` | `src/ensemble_training.py` | `from config import HOLDOUT_SEASON` | VERIFIED | Line 41 imports HOLDOUT_SEASON; line 349 applies `season < HOLDOUT_SEASON` guard |
| `src/config.py` | `tests/test_model_training.py` | `from src.config import TRAINING_SEASONS` | VERIFIED | Lines 20-21 import HOLDOUT_SEASON and TRAINING_SEASONS; used in test body |
| `scripts/train_ensemble.py` | `models/ensemble/` | model save after training | VERIFIED | metadata.json trained_at=2026-03-29, training_seasons=[2016..2024], holdout_season=2025 |
| `scripts/backtest_predictions.py` | `BASELINE.md` | metrics documented after --holdout run | VERIFIED | BASELINE.md contains exact metrics matching the backtest output format (ATS Accuracy, Record, ROI, CLV) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| HOLD-01 | 37-01 | Holdout season rotated from 2024 to 2025 in config.py with all holdout guards updated | SATISFIED | config.py HOLDOUT_SEASON=2025; ensemble_training.py guard uses HOLDOUT_SEASON dynamically |
| HOLD-02 | 37-01 | TRAINING/VALIDATION/PREDICTION_SEASONS computed automatically from HOLDOUT_SEASON | SATISFIED | All three season lists use range expressions referencing HOLDOUT_SEASON; runtime verification confirms correct values |
| HOLD-03 | 37-02 | Ensemble retrained on 2016-2024 with sealed 2025 baseline documented | SATISFIED | models/ensemble/metadata.json confirms 9-season training; BASELINE.md documents 51.7% ATS, -$3.73 profit, CLV metrics |

All 3 requirements claimed by phase plans (HOLD-01, HOLD-02, HOLD-03) are satisfied. No orphaned requirements for Phase 37 exist in REQUIREMENTS.md.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | - | - | - |

No stubs, placeholders, or incomplete implementations found in modified files. BASELINE.md contains actual numeric metrics (not template placeholders).

### Human Verification Required

None. All phase deliverables are verifiable programmatically:

- Config constants verified via Python import
- Test suite passes (594/594)
- Model files exist with correct metadata
- BASELINE.md contains actual metrics (not `{X}` placeholders)

The only item that could warrant human review is whether 51.7% ATS on the 2025 holdout represents a reasonable signal — but the SUMMARY explicitly notes this is above 50% (directional signal present) and the D-11 investigation threshold was not triggered. This is a business interpretation, not a verification gap.

### Gaps Summary

No gaps. All must-haves verified.

---

## Success Criteria Verification (from ROADMAP.md)

1. **config.py HOLDOUT_SEASON equals 2025 and season ranges computed automatically** — VERIFIED. Runtime confirms TRAINING_SEASONS=[2016..2024], VALIDATION_SEASONS=[2019..2024], PREDICTION_SEASONS=[2016..2025].

2. **train_ensemble.py trains on 2016-2024 with holdout guard rejecting 2025** — VERIFIED. ensemble_training.py line 349 filters `season < HOLDOUT_SEASON`; metadata.json confirms the actual trained model used training_seasons=[2016..2024].

3. **backtest_predictions.py --holdout produces ATS accuracy, profit, CLV against sealed 2025 holdout with results documented** — VERIFIED. BASELINE.md contains: 51.7% ATS, 140-131-1 record, -$3.73 profit, -1.38% ROI, +0.14 mean CLV, CLV by tier table.

4. **All tests that previously hardcoded 2024 as holdout season now import HOLDOUT_SEASON from config and pass** — VERIFIED. Zero matches for `holdout_season=2024` in test source. All 594 tests pass.

---

_Verified: 2026-03-29_
_Verifier: Claude (gsd-verifier)_
