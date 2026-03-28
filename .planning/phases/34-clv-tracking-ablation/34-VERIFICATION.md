---
phase: 34-clv-tracking-ablation
verified: 2026-03-28T15:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 34: CLV Tracking + Ablation Verification Report

**Phase Goal:** Model quality is measured by CLV, and market features are shipped only if they improve the sealed 2024 holdout
**Verified:** 2026-03-28T15:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Backtest output includes point-based CLV (model_spread - closing_spread) per game, with mean CLV and pct_beating_close in the summary report | VERIFIED | `evaluate_clv()` in `src/prediction_backtester.py` line 72 computes `df["clv"] = df["predicted_margin"] - df["spread_line"]`; `print_clv_report()` in `scripts/backtest_predictions.py` line 119 formats Mean CLV and Pct Beating Close |
| 2 | CLV is reported broken out by confidence tier (high/medium/low) and by season, showing model quality trends over time | VERIFIED | `compute_clv_by_tier()` (line 89, bins [-inf, 1.5, 3.0, inf], labels ["low","medium","high"]) and `compute_clv_by_season()` (line 121) both exist; `print_clv_report()` calls both and renders "By Confidence Tier:" and "By Season:" sections |
| 3 | Ablation on the sealed 2024 holdout compares v2.0 baseline vs v2.0+market features, with SHAP importance report for market features | VERIFIED | `scripts/ablation_market_features.py` contains `evaluate_baseline()`, `run_feature_selection_with_market()`, `retrain_ablation_ensemble()`, `evaluate_ablation_model()`, `format_shap_report()` with opening_spread dominance check (>30% threshold per D-12/D-13), and `format_comparison_report()` |
| 4 | If market features do not improve holdout ATS accuracy, they are excluded from the production model; CLV tracking ships regardless | VERIFIED | `compute_ship_or_skip()` uses strict `>` comparison (returns "SKIP" when ablation_ats <= baseline_ats); `apply_ship_decision()` uses `shutil.copytree(ABLATION_DIR, ENSEMBLE_DIR, dirs_exist_ok=True)` only on "SHIP"; CLV functions are in `prediction_backtester.py` independently of ablation outcome |

**Score:** 4/4 success criteria verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/prediction_backtester.py` | `evaluate_clv()`, `compute_clv_by_tier()`, `compute_clv_by_season()` | VERIFIED | All three functions present at lines 72, 89, 121. CLV formula, bin edges, and groupby logic are substantive (not stubs). File is imported by `backtest_predictions.py`. |
| `tests/test_prediction_backtester.py` | `TestCLVEvaluation`, `TestCLVByTier`, `TestCLVBySeason` test classes | VERIFIED | All three classes present at lines 522, 559, 605. CLV functions imported at lines 16–18. 9 tests across 3 classes; 64 total in this file, all passing. |
| `scripts/backtest_predictions.py` | CLV section in ensemble backtest CLI output via `evaluate_clv` | VERIFIED | `evaluate_clv` imported at line 32; `print_clv_report()` defined at line 119 and called at lines 348, 480, 597 (ensemble, comparison, holdout modes). |
| `scripts/ablation_market_features.py` | Full ablation orchestrator: `run_ablation`, `evaluate_baseline`, `compute_ship_or_skip`, `format_shap_report`, `format_comparison_report`, `apply_ship_decision` | VERIFIED | All six functions present. `ABLATION_DIR = "models/ensemble_ablation"` at line 53. `VERDICT: SHIP` and `VERDICT: SKIP` strings present. `shutil.copytree(..., dirs_exist_ok=True)` at line 470. |
| `tests/test_ablation.py` | `TestShipOrSkip`, `TestAblationReport`, `TestAblationPaths`, `TestApplyShipDecision` | VERIFIED | All four classes present at lines 31, 65, 147, 162. `test_opening_spread_dominance_no_improvement` present. 17 tests, all passing. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/prediction_backtester.py` | `scripts/backtest_predictions.py` | `import evaluate_clv, compute_clv_by_season, compute_clv_by_tier` | WIRED | All three imported in `from prediction_backtester import (...)` block at lines 32, 35, 36; all three called inside `print_clv_report()` |
| `scripts/ablation_market_features.py` | `src/feature_selector.py` | `from feature_selector import` | WIRED | Line 41: `from feature_selector import FeatureSelectionResult, select_features_for_fold`. No import from `scripts/run_feature_selection.py` (anti-pattern confirmed clean). |
| `scripts/ablation_market_features.py` | `src/ensemble_training.py` | `from ensemble_training import` | WIRED | Line 39: `from ensemble_training import load_ensemble, predict_ensemble, train_ensemble` |
| `scripts/ablation_market_features.py` | `src/prediction_backtester.py` | `from prediction_backtester import` | WIRED | Line 42: `from prediction_backtester import` — includes `evaluate_ats`, `evaluate_holdout`, `evaluate_clv` |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CLV-01 | 34-01-PLAN.md | Compute point-based CLV (model_spread - closing_spread) per game in backtest output | SATISFIED | `evaluate_clv()` computes `df["clv"] = df["predicted_margin"] - df["spread_line"]`; wired into `print_clv_report()` in backtest CLI |
| CLV-02 | 34-01-PLAN.md | Report average CLV broken out by confidence tier (high/medium/low) in backtest summary | SATISFIED | `compute_clv_by_tier()` with bins [-inf, 1.5, 3.0, inf] and labels ["low","medium","high"]; rendered in "By Confidence Tier:" section of `print_clv_report()` |
| CLV-03 | 34-01-PLAN.md | Track per-season CLV averages to measure model quality trends over time | SATISFIED | `compute_clv_by_season()` groups by season; rendered in "By Season:" section of `print_clv_report()` |
| LINE-04 | 34-02-PLAN.md | Add line movement features as candidates to feature selection with ablation on sealed holdout | SATISFIED | `scripts/ablation_market_features.py` orchestrates 5-step ablation; market features (opening_spread, opening_total) already in `_PRE_GAME_CONTEXT` from Phase 33; `compute_ship_or_skip()` enforces strict > gate; ablation trains to `models/ensemble_ablation/` (not production directory) |

No orphaned requirements — all four requirement IDs declared in plan frontmatter are accounted for.

---

### Anti-Patterns Found

No anti-patterns detected. Scan across all five phase files (`src/prediction_backtester.py`, `scripts/backtest_predictions.py`, `scripts/ablation_market_features.py`, `tests/test_prediction_backtester.py`, `tests/test_ablation.py`) returned zero hits for: TODO, FIXME, XXX, HACK, PLACEHOLDER, "not implemented", empty handlers, static return stubs.

Additional safety checks:
- `from run_feature_selection import` absent from ablation script (anti-pattern avoided; uses `src/feature_selector.py` directly)
- `ensemble_dir=ENSEMBLE_DIR` not used for retrain call in ablation script (production directory protected; uses `ABLATION_DIR`)
- D-14 string "model already captures market signal indirectly" present in `format_comparison_report()`

---

### Human Verification Required

#### 1. Ablation end-to-end run

**Test:** Run `python scripts/ablation_market_features.py --dry-run` with Silver data present.
**Expected:** Baseline P30 ensemble is loaded from `models/ensemble/`, predictions are generated, holdout accuracy is reported as approximately 53.0% ATS, and the script exits cleanly without retraining.
**Why human:** Requires Silver data assembled by `assemble_multiyear_features()` and a valid `models/ensemble/` directory. Cannot verify the prediction pipeline end-to-end without running the full data assembly.

#### 2. CLV report format in live backtest

**Test:** Run `python scripts/backtest_predictions.py --ensemble` (requires Gold predictions).
**Expected:** After ATS report, a "CLV RESULTS" section appears with mean CLV, pct_beating_close, tier table (high/medium/low), and season breakdown table.
**Why human:** Requires Gold prediction files present in `data/gold/predictions/`; output format can only be verified visually.

---

### Commit Verification

All SUMMARY-documented commit hashes verified present in git log:
- `fef6bd1` — feat(34-01): add CLV tracking functions with TDD tests
- `6d1b821` — feat(34-01): wire CLV reporting into backtest CLI
- `e77c6ea` — feat(34-02): ablation script for market feature comparison with tests

---

### Summary

Phase 34 fully achieves its goal. All four ROADMAP success criteria are satisfied:

1. CLV is computed per-game as `predicted_margin - spread_line` and reported in the backtest CLI output with mean CLV and pct_beating_close.
2. CLV is broken down by confidence tier (high/medium/low) and by season in `print_clv_report()`, wired into ensemble, comparison, and holdout backtest modes.
3. `scripts/ablation_market_features.py` implements the full 5-step ablation orchestrator comparing P30 baseline against market-augmented ensemble with SHAP importance and opening_spread dominance detection.
4. The ship-or-skip gate uses strict `>` comparison — market features are excluded unless they improve holdout ATS; CLV tracking is independent of this decision.

All 9 must-have artifacts and key links are verified substantive and wired. The test suite grew from 503 to 571 tests, all passing. No stubs, no anti-patterns, no orphaned requirements.

---

_Verified: 2026-03-28T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
