---
phase: 30-model-ensemble
verified: 2026-03-26T01:10:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 30: Model Ensemble Verification Report

**Phase Goal:** A three-model stacking ensemble (XGBoost + LightGBM + CatBoost with Ridge meta-learner) is trained on the reduced feature set and backtested against the v1.4 single-XGBoost baseline
**Verified:** 2026-03-26T01:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LightGBM and CatBoost base learners train with model-specific Optuna search spaces (separate from XGBoost's) | VERIFIED | `LGB_CONSERVATIVE_PARAMS` and `CB_CONSERVATIVE_PARAMS` exist in `src/config.py`. `train_ensemble.py` Optuna objectives use LGB-specific params (`min_child_samples`, `force_col_wise`) and CB-specific params (`depth`, `l2_leaf_reg`, `rsm`, `bootstrap_type`) distinct from XGB space. |
| 2 | OOF predictions are generated from walk-forward CV folds where no base model trained on future data generates predictions for past games | VERIFIED | `walk_forward_cv_with_oof` trains on `season < val_season` for each fold. `TestWalkForwardCVWithOOF.test_oof_temporal_correctness` asserts all train_seasons < val_season. Holdout guard raises `ValueError` if `val_season == HOLDOUT_SEASON`. 12 tests pass. |
| 3 | The Ridge meta-learner trains on temporal OOF predictions and produces ensemble spread and total predictions | VERIFIED | `train_ridge_meta` uses `RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])` on `["xgb_pred", "lgb_pred", "cb_pred"]`. `train_ensemble` calls it after `assemble_oof_matrix`. `predict_ensemble` stacks base predictions and calls `ridge.predict(stacked)`. |
| 4 | Running the backtest CLI with --ensemble produces a side-by-side ATS/ROI comparison vs the v1.4 single-XGBoost baseline | VERIFIED | `run_comparison_backtest` function in `scripts/backtest_predictions.py` loads both single XGBoost and ensemble, evaluates both, then prints a comparison table with `COMPARISON: Single XGBoost vs Ensemble` header, Accuracy/Profit/ROI columns and deltas. `--help` shows `--ensemble` flag. |
| 5 | Model artifacts save to models/ensemble/ with metadata.json that the prediction CLI dispatches on automatically | VERIFIED | `train_ensemble` saves `xgb_{target}.json`, `lgb_{target}.txt`, `cb_{target}.cbm`, `ridge_{target}.pkl` and `metadata.json` to `ensemble_dir`. `generate_predictions.py` loads via `load_ensemble(args.ensemble_dir)` when `--ensemble` is passed, reads `metadata["selected_features"]`. |

**Score:** 5/5 success criteria verified (10/10 artifacts and links below)

### Plan 01 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LightGBM base learner trains via walk-forward CV and produces OOF predictions | VERIFIED | `make_lgb_model` factory + `_lgb_fit_kwargs` with `lgb.early_stopping(50)` callback. `walk_forward_cv_with_oof` callable pattern handles framework differences. |
| 2 | CatBoost base learner trains via walk-forward CV and produces OOF predictions | VERIFIED | `make_cb_model` factory + `_cb_fit_kwargs` with `eval_set=(X_val, y_val)` tuple (not list). |
| 3 | XGBoost base learner trains via generalized walk-forward CV and produces OOF predictions | VERIFIED | `make_xgb_model` factory + `_xgb_fit_kwargs`. Generalized CV works for all three via `model_factory` + `fit_kwargs_fn` pattern. |
| 4 | Ridge meta-learner trains on the 3-column OOF matrix from all base models | VERIFIED | `assemble_oof_matrix` inner-joins XGB/LGB/CB OOF on `game_id`, adds `actual`. `train_ridge_meta` trains `RidgeCV` on `["xgb_pred", "lgb_pred", "cb_pred"]`. |
| 5 | Full ensemble pipeline trains two independent ensembles (spread and total) | VERIFIED | `train_ensemble` iterates `{"spread": "actual_margin", "total": "actual_total"}` and trains independent base models + Ridge for each. |
| 6 | All ensemble artifacts save to models/ensemble/ with metadata.json | VERIFIED | `os.makedirs(ensemble_dir, exist_ok=True)` + saves 9 files: 4 per target (xgb, lgb, cb, ridge) + metadata.json. Test `test_train_ensemble_saves_all_artifacts` passes. |

### Plan 02 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running train_ensemble.py CLI trains the full ensemble and saves to models/ensemble/ | VERIFIED | `--help` exits 0 showing `--tune`, `--trials`, `--ensemble-dir`. Main calls `train_ensemble(...)`. Commit `f4bf0ba`. |
| 2 | Running backtest_predictions.py --ensemble produces side-by-side ATS/ROI comparison vs single XGBoost | VERIFIED | `run_comparison_backtest` with `COMPARISON:` print string. `--help` shows `--ensemble`. Commit `d3789b4`. |
| 3 | Running generate_predictions.py --ensemble loads ensemble models and generates predictions | VERIFIED | Ensemble branch in `main()`: `load_ensemble`, `predict_ensemble` for spread and total, sets `model_version = "v2.0-ensemble"`. |
| 4 | Existing single-model workflows remain unchanged (backward compatibility) | VERIFIED | `else` branch in `main()` of both CLIs uses existing `load_model`/`generate_week_predictions` unchanged. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/ensemble_training.py` | Generalized CV with OOF, model factories, Ridge meta-learner, ensemble save/load | VERIFIED | 529 lines. All 9 exported functions present and substantive. |
| `src/config.py` | LGB_CONSERVATIVE_PARAMS, CB_CONSERVATIVE_PARAMS, ENSEMBLE_DIR | VERIFIED | Lines 433-466: all three constants present with correct values (max_depth=4, learning_rate=0.05, n_estimators=500 for LGB; depth=4, iterations=500, allow_writing_files=False for CB). |
| `tests/test_ensemble_training.py` | Tests for ENS-01 through ENS-04 | VERIFIED | 12 test functions across 5 test classes: TestModelFactories, TestWalkForwardCVWithOOF, TestRidgeMeta, TestTrainEnsemble, TestLoadEnsemble, TestPredictEnsemble. All 12 pass in 7.33s. |
| `scripts/train_ensemble.py` | CLI with --tune, --trials, --ensemble-dir | VERIFIED | 349 lines. `build_parser()` defines all three flags. `_run_optuna_tuning()` with model-specific search spaces. Imports `train_ensemble` from ensemble_training. |
| `scripts/backtest_predictions.py` | Updated with --ensemble flag for side-by-side comparison | VERIFIED | `--ensemble` flag in argparse. `run_ensemble_backtest` and `run_comparison_backtest` functions present. COMPARISON table printed with XGBoost, Ensemble, Delta columns. |
| `scripts/generate_predictions.py` | Updated with --ensemble flag | VERIFIED | `--ensemble` flag in argparse. Ensemble branch sets `model_version = "v2.0-ensemble"`. Features loaded from `ens_metadata["selected_features"]`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/ensemble_training.py` | `src/config.py` | `from config import LGB_CONSERVATIVE_PARAMS, CB_CONSERVATIVE_PARAMS, ENSEMBLE_DIR` | WIRED | Line 37-44: full import block verified. |
| `src/ensemble_training.py` | `src/model_training.py` | `from model_training import WalkForwardResult` | WIRED | Line 36: import present. Used as return type in `walk_forward_cv_with_oof`. |
| `scripts/train_ensemble.py` | `src/ensemble_training.py` | `from ensemble_training import train_ensemble` | WIRED | Lines 29-38: imports `train_ensemble` and all factory/CV functions. Called in `main()`. |
| `scripts/backtest_predictions.py` | `src/ensemble_training.py` | `from ensemble_training import load_ensemble, predict_ensemble` | WIRED | Line 26: import present. Used in `run_ensemble_backtest` and `run_comparison_backtest`. |
| `scripts/generate_predictions.py` | `src/ensemble_training.py` | `from ensemble_training import load_ensemble, predict_ensemble` | WIRED | Line 38: import present. Used in ensemble branch of `main()`. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ENS-01 | 30-01-PLAN.md | Train LightGBM base learner with model-specific Optuna search space | SATISFIED | `make_lgb_model` factory, `LGB_CONSERVATIVE_PARAMS`, LGB-specific Optuna objective in `train_ensemble.py` |
| ENS-02 | 30-01-PLAN.md | Train CatBoost base learner with model-specific tuning constraints | SATISFIED | `make_cb_model` factory, `CB_CONSERVATIVE_PARAMS` (depth, l2_leaf_reg, rsm, Bernoulli bootstrap), CB-specific Optuna objective |
| ENS-03 | 30-01-PLAN.md | Generate temporal OOF predictions from walk-forward CV for stacking | SATISFIED | `walk_forward_cv_with_oof` returns OOF DataFrame. Temporal guard: trains on `season < val_season`. Holdout guard raises `ValueError`. |
| ENS-04 | 30-01-PLAN.md | Train Ridge meta-learner on OOF predictions from all base models | SATISFIED | `train_ridge_meta` with `RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])`. `assemble_oof_matrix` joins XGB/LGB/CB OOF into 3-column matrix. |
| ENS-05 | 30-02-PLAN.md | Backtest ensemble model and compare ATS/ROI vs single XGBoost baseline | SATISFIED | `run_comparison_backtest` in `backtest_predictions.py`: loads both models, evaluates, prints side-by-side table with Accuracy/Profit/ROI deltas. `--ensemble` flag in backtest CLI. |

All 5 requirement IDs (ENS-01 through ENS-05) declared across plans are accounted for. No orphaned requirements found in REQUIREMENTS.md for Phase 30.

### Anti-Patterns Found

No anti-patterns found. Scanned `src/ensemble_training.py`, `scripts/train_ensemble.py`, `scripts/backtest_predictions.py`, and `scripts/generate_predictions.py` for TODO/FIXME, empty implementations, placeholder returns, and stub handlers. None found.

**Minor observation (not a blocker):** `predict_ensemble` contains a redundant `else` branch that is identical to the `if isinstance(lgb_model, lgb.Booster)` branch (lines 518-521). This is a cosmetic issue from an initial draft. Does not affect correctness.

### Human Verification Required

No human verification required. All success criteria are programmatically verifiable. The backtest CLI produces a comparison table but requires actual trained model artifacts at runtime — the interface structure has been verified via code inspection.

Note: The final ATS accuracy improvement over v1.4 baseline is a runtime outcome that cannot be verified statically. Phase 31 requires a final holdout comparison documenting the result.

### Gaps Summary

No gaps. All 10 must-haves verified across both plans.

- Plan 01 (ENS-01 through ENS-04): 6/6 truths verified. `src/ensemble_training.py` is fully substantive with all exported functions implemented. 12 tests pass with temporal correctness verified programmatically.
- Plan 02 (ENS-05): 4/4 truths verified. All three CLIs have correct `--ensemble` dispatch wiring. Side-by-side comparison table is implemented with XGBoost/Ensemble/Delta columns. Backward compatibility confirmed via `else` branches.
- Commit hashes from SUMMARY (73da829, 862757a, f4bf0ba, d3789b4) all exist in git history.

---

_Verified: 2026-03-26T01:10:00Z_
_Verifier: Claude (gsd-verifier)_
