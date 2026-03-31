---
phase: 40-baseline-models-ship-gate
verified: 2026-03-30T08:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 40: Baseline Models and Ship Gate Verification Report

**Phase Goal:** Per-position ML models produce stat-level predictions that are objectively measured against the heuristic baseline, with a clear ship-or-skip verdict
**Verified:** 2026-03-30
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
|-----|-------|--------|----------|
| 1 | Separate gradient boosting models exist for QB, RB, WR, and TE, each predicting raw stat components (yards, TDs, receptions) rather than fantasy points directly | VERIFIED | `POSITION_STAT_PROFILE` drives per-stat training in `train_position_models()`. 19 total stat models (QB:5, RB:6, WR:4, TE:4). `test_position_stat_models_count` verifies the count. |
| 2 | All models are trained using walk-forward temporal CV respecting season/week ordering with 2025 holdout sealed and never touched during training | VERIFIED | `player_walk_forward_cv()` uses `PLAYER_VALIDATION_SEASONS = [2022, 2023, 2024]`, raises `ValueError` if any val season equals `HOLDOUT_SEASON`. `stat_data = stat_data[stat_data["season"] != HOLDOUT_SEASON]` in `train_position_models()`. `test_holdout_guard` and `test_player_walk_forward_folds` (3 folds) verify behavior. |
| 3 | Per-position MAE, RMSE, and correlation are reported independently and compared side-by-side against heuristic baselines (QB: 6.58, RB: 5.06, WR: 4.85, TE: 3.77) | VERIFIED | `compute_position_mae()` computes fantasy-point MAE from raw stat predictions. `print_ship_gate_table()` renders a per-position comparison table with delta percentages. Heuristic re-run via `generate_heuristic_predictions()` on identical rows (D-12). `build_ship_gate_report()` saves JSON at `models/player/ship_gate_report.json`. |
| 4 | A ship-or-skip gate produces a clear verdict: positions where ML achieves 4%+ MAE improvement over heuristic are shipped; others fall back to heuristic | VERIFIED | `ship_gate_verdict()` implements dual agreement: `holdout_improvement >= 0.04 and oof_improvement >= 0.04 and not safety_violation`. Safety floor: any stat model >10% worse triggers SKIP. `test_ship_gate_verdict_ship`, `test_ship_gate_verdict_skip_insufficient`, `test_ship_gate_verdict_skip_disagreement`, `test_safety_floor` all pass. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Min Lines | Actual Lines | Status | Details |
|----------|-----------|--------------|--------|---------|
| `src/player_model_training.py` | 300 | 852 | VERIFIED | Full implementation: walk-forward CV, SHAP feature selection, model training, ship gate verdict, heuristic comparison, serialization. No NotImplementedError stubs. |
| `tests/test_player_model_training.py` | 150 | 273 | VERIFIED | 8 tests covering model count, stat groups, CV folds, holdout guard, hyperparams, fantasy conversion, feature selection, serialization — all 8 pass. |
| `scripts/train_player_models.py` | 150 | 407 | VERIFIED | Full CLI with argparse (--positions, --dry-run, --skip-feature-selection, --holdout-eval, --scoring). Imports and calls all ship gate functions. `--help` exits 0. |
| `tests/test_player_ship_gate.py` | 80 | 175 | VERIFIED | 6 tests covering verdict SHIP, verdict SKIP (insufficient), verdict SKIP (disagreement), safety floor, heuristic baseline, report JSON — all 6 pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/player_model_training.py` | `src/ensemble_training.py` | `make_xgb_model` | WIRED | Line 35: `from ensemble_training import make_xgb_model`. Used throughout `run_player_feature_selection()` and `train_position_models()`. |
| `src/player_model_training.py` | `src/config.py` | `HOLDOUT_SEASON, CONSERVATIVE_PARAMS` | WIRED | Line 34: `from config import CONSERVATIVE_PARAMS, HOLDOUT_SEASON`. Both constants actively used in guard checks and hyperparameter profiles. |
| `src/player_model_training.py` | `src/projection_engine.py` | `POSITION_STAT_PROFILE` | WIRED | Line 38: `from projection_engine import POSITION_STAT_PROFILE`. Drives stat model count and position-stat mapping throughout. |
| `src/player_model_training.py` | `src/feature_selector.py` | `_assert_no_holdout, filter_correlated_features` | WIRED | Line 36: `from feature_selector import _assert_no_holdout, filter_correlated_features`. Used in `run_player_feature_selection()`. |
| `src/player_model_training.py` | `src/scoring_calculator.py` | `calculate_fantasy_points_df` | WIRED | Lazy import at line 668 inside `compute_position_mae()`. Used for both ML and heuristic MAE computation. |
| `scripts/train_player_models.py` | `src/player_model_training.py` | `train_position_models, run_player_feature_selection, predict_player_stats` | WIRED | Lines 31-42: full import of all training, ship gate, and reporting functions. All used in main flow. |
| `scripts/train_player_models.py` | `src/player_feature_engineering.py` | `assemble_multiyear_player_features, get_player_feature_columns, detect_leakage` | WIRED | Lines 26-29: all three imported. Lines 199, 214, 220: called in main flow. |
| `scripts/train_player_models.py` | `src/projection_engine.py` | `POSITION_STAT_PROFILE` | WIRED | Line 42: imported. Used for position-level iteration. |

**Note on plan 01 key link:** The plan specified `from: "src/player_model_training.py" to: "src/player_feature_engineering.py"`. The import lives in `scripts/train_player_models.py` instead. This is architecturally correct: the training module is data-agnostic and the CLI orchestrates feature assembly, passing DataFrames into the training functions. The functional link (feature assembly feeding model training) is fully satisfied.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MODL-01 | 40-01-PLAN | Separate gradient boosting models trained per position (QB, RB, WR, TE) | SATISFIED | `train_position_models()` per position; 19 stat models across 4 positions via `POSITION_STAT_PROFILE` |
| MODL-02 | 40-01-PLAN | Walk-forward temporal CV respecting season/week ordering with 2025 holdout sealed | SATISFIED | `player_walk_forward_cv()` with 3 folds (val 2022/2023/2024), holdout guard at line 174-176 |
| MODL-03 | 40-02-PLAN | Per-position MAE/RMSE/correlation evaluation against heuristic baseline | SATISFIED | `compute_position_mae()`, `generate_heuristic_predictions()`, `print_ship_gate_table()` with side-by-side comparison |
| MODL-04 | 40-02-PLAN | Ship-or-skip gate requiring 4%+ per-position MAE improvement over heuristic | SATISFIED | `ship_gate_verdict()` with 4% dual-agreement threshold and 10% per-stat safety floor |
| PIPE-01 | 40-01-PLAN | Stat-level predictions (yards, TDs, receptions) with scoring formula applied downstream | SATISFIED | `predict_player_stats()` returns `pred_{stat}` columns; `compute_position_mae()` calls `calculate_fantasy_points_df()` for downstream scoring conversion |

All 5 requirement IDs satisfied. No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None detected | — | — | — | — |

Scan results: no TODO/FIXME/placeholder comments, no NotImplementedError stubs, no empty return patterns in any of the 4 phase artifacts.

### Human Verification Required

#### 1. Ship Gate Verdict on Real Data

**Test:** Run `python scripts/train_player_models.py --positions QB RB WR TE` with actual 2020-2024 player feature data loaded
**Expected:** 19 stat models train successfully, per-position MAE comparison table prints to stdout, `models/player/ship_gate_report.json` is created with SHIP/SKIP verdicts
**Why human:** Data assembly requires live local data files. Cannot verify end-to-end pipeline execution programmatically without running the full training pipeline.

#### 2. Walk-Forward CV Fold Quality

**Test:** Inspect fold MAEs printed during training for each position/stat model
**Expected:** Fold MAEs are reasonable (not 0.0 or extremely large), training seasons increase across folds (2020-2021 -> 2022, 2020-2022 -> 2023, 2020-2023 -> 2024)
**Why human:** The synthetic test data verifies fold structure but cannot validate fold MAE quality on real data distributions.

#### 3. Heuristic Baseline Fairness

**Test:** Compare ML predictions and heuristic predictions produced by `generate_heuristic_predictions()` on the same player-week rows
**Expected:** Both prediction sets are populated for the same rows; heuristic values align with known projection engine outputs for well-known players
**Why human:** Verifying the heuristic re-run uses identical rows (D-12) requires spot-checking actual data outputs.

### Gaps Summary

No gaps found. All 4 success criteria are implemented and tested. All 5 requirement IDs are satisfied. All 14 unit tests (8 from plan 01, 6 from plan 02) pass. Full test suite at 622 tests with zero regressions.

The phase goal — per-position ML models producing stat-level predictions with objective measurement against the heuristic baseline and a clear ship-or-skip verdict — is fully achieved at the code and test level.

---

_Verified: 2026-03-30_
_Verifier: Claude (gsd-verifier)_
