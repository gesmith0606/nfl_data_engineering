---
phase: 41-accuracy-improvements
verified: 2026-03-31T14:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
human_verification:
  - test: "Run python scripts/train_player_models.py --holdout-eval with real Silver data to confirm OOF MAE improvement over Phase 40 baselines"
    expected: "At least one of RB/WR/TE flips from SKIP to SHIP (OOF MAE < heuristic * 0.96)"
    why_human: "Requires real data training pass; cannot verify accuracy improvement programmatically without Silver parquet files"
---

# Phase 41: Accuracy Improvements — Verification Report

**Phase Goal:** Per-position prediction accuracy improves beyond the baseline models through decomposition, regression features, and ensemble stacking
**Verified:** 2026-03-31
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Opportunity-efficiency decomposition features (yards_per_carry, yards_per_target, yards_per_reception, catch_rate, rush_td_rate, rec_td_rate with roll3/roll6) exist and are wired into assemble_player_features | VERIFIED | `compute_efficiency_features` defined at line 201 of `src/player_feature_engineering.py`, called at line 458 inside `assemble_player_features` |
| 2 | TD regression features (expected_td_pos_avg, expected_td_player) use red zone target share multiplied by conversion rates | VERIFIED | `compute_td_regression_features` defined at line 243, uses `POSITION_AVG_RZ_TD_RATE` from config (RB: 0.08, WR: 0.12, TE: 0.14), called at line 459 |
| 3 | Role momentum delta features (snap_pct_delta, target_share_delta, carry_share_delta = roll3 minus roll6) are available as model inputs | VERIFIED | `compute_momentum_features` defined at line 283, called at line 460; skips silently on missing columns |
| 4 | Ensemble stacking (XGB+LGB+Ridge meta-learner per stat) is implemented and wired into CLI | VERIFIED | `player_ensemble_stacking` defined in `src/player_model_training.py` line 587; CLI `--stage` flag present with `features-only / ensemble / both` choices; two-stage ablation report implemented |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/player_feature_engineering.py` | compute_efficiency_features, compute_td_regression_features, compute_momentum_features | VERIFIED | All three functions defined (lines 201, 243, 283), all three called inside assemble_player_features (lines 458-460) |
| `src/config.py` | POSITION_AVG_RZ_TD_RATE constants | VERIFIED | Defined at line 466: `{"RB": 0.08, "WR": 0.12, "TE": 0.14}` |
| `tests/test_player_feature_engineering.py` | Unit tests for all three feature groups | VERIFIED | 9 tests present: TestEfficiencyFeatures (3), TestTdRegressionFeatures (3), TestMomentumFeatures (3) — all passing |
| `src/player_model_training.py` | _player_lgb_fit_kwargs, get_lgb_params_for_stat, assemble_player_oof_matrix, train_player_ridge_meta, player_ensemble_stacking | VERIFIED | All 5 functions defined at lines 155, 125, 529, 565, 587 respectively |
| `scripts/train_player_models.py` | --stage CLI flag and two-stage evaluation flow | VERIFIED | `--stage` argument at line 90 with choices `["features-only", "ensemble", "both"]`; STAGE 1 at line 407, STAGE 2 at line 433, TWO-STAGE ABLATION REPORT at line 548 |
| `tests/test_player_model_training.py` | Unit tests for LGB fit kwargs, OOF matrix, ensemble stacking | VERIFIED | 6 tests present at lines 279-393 — all passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/player_feature_engineering.py` | `assemble_player_features` return | called at end of assembly (lines 458-460) | WIRED | `compute_efficiency_features(base)`, `compute_td_regression_features(base)`, `compute_momentum_features(base)` called before logger.info and return |
| `src/player_feature_engineering.py` | `src/config.py` | `POSITION_AVG_RZ_TD_RATE` import | WIRED | Line 26 imports `POSITION_AVG_RZ_TD_RATE` from config; used in `compute_td_regression_features` |
| `scripts/train_player_models.py` | `src/player_model_training.py` | imports `player_ensemble_stacking` | WIRED | Line 36 imports `player_ensemble_stacking`; called at line 444 inside ensemble stage |
| `src/player_model_training.py` | `src/ensemble_training.py` | imports `make_lgb_model` | WIRED | Line 41: `from ensemble_training import make_lgb_model, make_xgb_model`; `make_lgb_model` called at lines 640, 663 inside `player_ensemble_stacking` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ACCY-01 | 41-01-PLAN.md | Opportunity-efficiency decomposition predicting shares/volume then per-touch efficiency | SATISFIED (with scope note) | 12 efficiency ratio features (6 ratios x 2 windows) implemented as model inputs. D-05 explicitly chose derived-features approach over chained two-stage prediction to avoid error compounding. The spirit of decomposing opportunity from efficiency is satisfied; the literal "predicts separately then combines" wording from the ROADMAP success criterion was intentionally not used. |
| ACCY-02 | 41-01-PLAN.md | TD regression features using red zone opportunity share x historical conversion rates | SATISFIED | expected_td_pos_avg and expected_td_player columns computed; POSITION_AVG_RZ_TD_RATE constants in config.py |
| ACCY-03 | 41-01-PLAN.md | Role momentum features (snap share trajectory as breakout/demotion signal) | SATISFIED | snap_pct_delta, target_share_delta, carry_share_delta implemented; named exactly per D-08 |
| ACCY-04 | 41-02-PLAN.md | Ensemble stacking (XGB+LGB+CB+Ridge) per position if single model leaves accuracy on the table | SATISFIED (with scope note) | XGB+LGB+Ridge implemented per stat per position. CatBoost dropped per D-10 ("no categorical features to justify it"). Requirements.md says "CB+Ridge" but the design decision document and both plan summaries confirm this was intentional. Functional stacking is complete. |

**Note on ACCY-01 and ACCY-04 scope variance:** Both requirements have minor wording differences between REQUIREMENTS.md and the implemented design. Both are documented design decisions in `41-CONTEXT.md` (D-05 and D-10), recorded in plan summaries, and do not represent gaps — they represent intentional implementation choices made during design.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| No blocker anti-patterns found | — | — | — | — |

Scanned `src/player_feature_engineering.py`, `src/player_model_training.py`, `scripts/train_player_models.py`, and `tests/test_player_feature_engineering.py`. No TODO/FIXME/placeholder comments, no empty return stubs, no hardcoded empty data flowing to rendering.

---

### Human Verification Required

#### 1. OOF Accuracy Gate — Real Data Training Run

**Test:** Run `python scripts/train_player_models.py --stage both` with real Silver data loaded (requires `data/silver/players/usage/season=2022/` through 2024 populated)
**Expected:** At least one of RB/WR/TE flips from SKIP to SHIP — OOF MAE improvement of 4%+ over Phase 40 heuristic baseline (RB < 4.448, WR < 4.132, TE < 3.152)
**Why human:** Requires full training pass with real parquet data. Cannot verify accuracy gain programmatically — only the infrastructure for making that gain can be code-verified.

---

### Full Test Suite

638 tests pass (`python -m pytest tests/ -v` — 50s runtime):
- 9 new tests in `tests/test_player_feature_engineering.py` covering efficiency, TD regression, and momentum feature groups
- 6 new tests in `tests/test_player_model_training.py` covering LGB fit kwargs, params, OOF matrix assembly, and ensemble stacking

---

## Summary

Phase 41 goal is achieved at the infrastructure level. All four requirements are satisfied:

- **ACCY-01** (efficiency decomposition): 12 ratio features (6 ratios x roll3/roll6) wired into the player feature vector, with safe division via np.where and auto-discovery by get_player_feature_columns.
- **ACCY-02** (TD regression): expected_td_pos_avg and expected_td_player columns use rz_target_share_roll3 multiplied by position-specific or player-specific conversion rates.
- **ACCY-03** (momentum features): Three delta columns (snap_pct_delta, target_share_delta, carry_share_delta) detect role trajectory changes.
- **ACCY-04** (ensemble stacking): Full XGB+LGB+Ridge stacking per stat per position implemented; CLI --stage flag enables two-stage evaluation with separate ship gate reports.

The two intentional design deviations (ACCY-01: derived features vs chained prediction; ACCY-04: XGB+LGB+Ridge vs XGB+LGB+CB+Ridge) are both documented in the design decisions file and both plan summaries. They do not represent implementation gaps.

One item requires human verification: the actual OOF accuracy improvement can only be confirmed by running a full training pass against real Silver data.

---

_Verified: 2026-03-31_
_Verifier: Claude (gsd-verifier)_
