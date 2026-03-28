# Phase 34: CLV Tracking + Ablation - Research

**Researched:** 2026-03-28
**Domain:** Sports betting model evaluation (CLV) + feature ablation methodology
**Confidence:** HIGH

## Summary

This phase adds two capabilities: (1) Closing Line Value (CLV) tracking in the backtester, and (2) a full ablation comparing the P30 ensemble baseline vs a market-feature-augmented model on the sealed 2024 holdout. Both build directly on existing, well-structured code.

CLV computation is straightforward -- `predicted_margin - spread_line` is a one-liner on columns already present in the backtest DataFrame. The heavier lift is the ablation script, which orchestrates the full feature selection + ensemble training + holdout evaluation pipeline, comparing baseline vs market-augmented results. The key architectural insight is that market features (opening_spread, opening_total) are already wired into `_PRE_GAME_CONTEXT` in `feature_engineering.py` (Phase 33), so `get_feature_columns()` already includes them as candidates. The ablation re-runs feature selection with these candidates available, then retrains the ensemble, then compares holdout results.

All required libraries (shap 0.49.1, xgboost 2.1.4, lightgbm 4.6.0, catboost 1.2.10) are already installed. No new dependencies are needed.

**Primary recommendation:** Implement CLV as a pure function in `prediction_backtester.py`, add CLV reporting to the backtest CLI, then build a standalone `scripts/ablation_market_features.py` that calls existing feature selection and ensemble training functions.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Full ablation: retrain ensemble from scratch with market features as candidates in the feature selection pipeline -- do not manually add features to the P30 set. Re-run `run_feature_selection.py` with market_data Silver source included, then retrain ensemble, then compare holdout results
- **D-02:** The ablation trains on 2016-2021 (where market data exists) and evaluates on 2024 holdout (where market data does NOT exist -- NaN). This tests whether market-informed feature selection improves the model even when market features are unavailable at prediction time
- **D-03:** If market features are selected by SHAP but NaN for 2022-2024, XGBoost/LightGBM/CatBoost handle NaN natively -- no imputation needed. Ridge meta-learner gets NaN-filled to 0 (existing behavior)
- **D-04:** Create a dedicated ablation script `scripts/ablation_market_features.py` that orchestrates: (1) baseline P30 holdout eval, (2) re-run feature selection with market data, (3) retrain ensemble with selected features, (4) holdout eval, (5) comparison report
- **D-05:** Use nflverse `spread_line` already present in the assembled game features DataFrame -- no new data join required. CLV = `predicted_margin - spread_line`
- **D-06:** CLV is computed in `prediction_backtester.py` as a new function `evaluate_clv()` that takes the same DataFrame used by `evaluate_ats()`
- **D-07:** CLV metrics added to the backtest summary report (both CLI output and any saved JSON/CSV): `mean_clv`, `pct_beating_close`, `clv_by_season`, `clv_by_tier`
- **D-08:** If market features improve holdout ATS accuracy by any amount (even 0.1%), ship them
- **D-09:** If market features do NOT improve holdout ATS: exclude them from the production model. P30 ensemble remains production. CLV tracking still ships.
- **D-10:** The ship-or-skip decision is documented in the ablation output report, not encoded as a config flag
- **D-11:** If shipped, update `metadata.json` with the new feature set
- **D-12:** If `opening_spread` exceeds 30% SHAP importance: still ship it if holdout ATS improves
- **D-13:** Log the SHAP importance distribution in the ablation report
- **D-14:** If opening_spread dominates AND holdout does NOT improve: document this finding
- **D-15:** CLV by confidence tier: reuse existing tier thresholds (high >=3.0, medium >=1.5, low <1.5)
- **D-16:** CLV by season: one row per season with mean CLV, pct_beating_close, and game count
- **D-17:** Positive CLV = model line was closer to the final outcome than the closing line. Report both mean and median.

### Claude's Discretion
- Exact ablation script structure and CLI arguments
- SHAP visualization format (text table vs plot)
- How to handle the edge case where feature selection with market data selects fewer features than P30
- Logging and progress reporting during ablation

### Deferred Ideas (OUT OF SCOPE)
- No-vig implied probability CLV -- v2.2 Betting Framework
- Automated ablation pipeline (re-run on new data) -- v3.0 Production Infra
- CLV-weighted bet sizing -- v2.2 Betting Framework
- Rolling CLV monitoring for model drift detection -- v3.0
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLV-01 | Compute point-based CLV (model_spread - closing_spread) per game in backtest output | `evaluate_ats()` already produces DataFrame with `predicted_margin` and `spread_line` columns; CLV is `predicted_margin - spread_line` one-liner |
| CLV-02 | Report average CLV broken out by confidence tier (high/medium/low) in backtest summary | Tier thresholds exist in prediction pipeline (>=3.0 high, >=1.5 medium, <1.5 low); `compute_season_stability()` provides groupby pattern |
| CLV-03 | Track per-season CLV averages to measure model quality trends over time | `compute_season_stability()` groupby-season pattern can be cloned for CLV metrics |
| LINE-04 | Add line movement features as candidates to feature selection with ablation on sealed holdout | Market features already in `_PRE_GAME_CONTEXT` (Phase 33); `run_feature_selection.py` + `train_ensemble.py` provide full pipeline |
</phase_requirements>

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shap | 0.49.1 | SHAP importance for ablation report | Already used in `feature_selector.py`; TreeExplainer for XGBoost |
| xgboost | 2.1.4 | Base model in ensemble + feature selection | Existing ensemble component |
| lightgbm | 4.6.0 | Base model in ensemble | Existing ensemble component |
| catboost | 1.2.10 | Base model in ensemble | Existing ensemble component |
| pandas | (installed) | DataFrame operations throughout | Core data library |
| numpy | (installed) | Numeric computations | Core numeric library |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sklearn.linear_model.RidgeCV | (installed) | Meta-learner in stacking ensemble | Ensemble retraining during ablation |

**No new dependencies required.** All libraries are already installed.

## Architecture Patterns

### Recommended Changes by File

```
src/
├── prediction_backtester.py   # ADD: evaluate_clv(), compute_clv_by_season(), compute_clv_by_tier()
scripts/
├── backtest_predictions.py    # ADD: CLV section to print output
├── ablation_market_features.py # NEW: orchestrates full ablation pipeline
```

### Pattern 1: CLV as Pure Function in Backtester
**What:** Add `evaluate_clv(df)` to `prediction_backtester.py` following the same pattern as `evaluate_ats(df)` -- takes a DataFrame, returns it with CLV columns added.
**When to use:** Any time CLV metrics are needed from backtest results.
**Example:**
```python
# Source: existing evaluate_ats() pattern in prediction_backtester.py
def evaluate_clv(df: pd.DataFrame) -> pd.DataFrame:
    """Add CLV columns to backtest results DataFrame.

    CLV = predicted_margin - spread_line
    Positive CLV means the model's line was closer to the actual outcome
    than the closing spread.

    Args:
        df: DataFrame with predicted_margin and spread_line columns.

    Returns:
        Copy of df with added column: clv.
    """
    df = df.copy()
    df["clv"] = df["predicted_margin"] - df["spread_line"]
    return df
```

### Pattern 2: CLV Breakdown Functions (Clone compute_season_stability Pattern)
**What:** `compute_clv_by_season()` and `compute_clv_by_tier()` follow the same groupby pattern as `compute_season_stability()`.
**Example:**
```python
# Source: compute_season_stability() pattern in prediction_backtester.py
def compute_clv_by_season(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-season CLV metrics.

    Args:
        df: DataFrame with clv, season columns.

    Returns:
        DataFrame with season, games, mean_clv, median_clv, pct_beating_close.
    """
    rows = []
    for season, group in df.groupby("season"):
        rows.append({
            "season": int(season),
            "games": len(group),
            "mean_clv": float(group["clv"].mean()),
            "median_clv": float(group["clv"].median()),
            "pct_beating_close": float((group["clv"] > 0).mean()),
        })
    return pd.DataFrame(rows)
```

### Pattern 3: Ablation Script as Orchestrator
**What:** `scripts/ablation_market_features.py` calls existing functions rather than reimplementing logic. It uses `assemble_multiyear_features()`, `find_optimal_feature_count()`, `run_final_selection()`, `train_ensemble()`, and `evaluate_holdout()`.
**When to use:** The ablation is a one-time comparison, not a runtime feature.
**Key flow:**
1. Load baseline P30 ensemble from `models/ensemble/` and evaluate holdout
2. Re-run feature selection with market features as candidates (they are already in the assembled data since Phase 33 wired them into `_PRE_GAME_CONTEXT`)
3. Retrain ensemble with newly selected features to a separate directory (e.g., `models/ensemble_ablation/`)
4. Evaluate ablation ensemble on holdout
5. Compare and produce report with SHAP importance
6. If improved: copy ablation artifacts to `models/ensemble/` and update metadata

### Pattern 4: Confidence Tier Computation
**What:** Tier assignment uses the edge magnitude `abs(predicted_margin - spread_line)` with existing thresholds.
**Example:**
```python
# Source: existing tier logic in prediction pipeline
def _assign_tier(edge: float) -> str:
    """Assign confidence tier based on edge magnitude."""
    if abs(edge) >= 3.0:
        return "high"
    elif abs(edge) >= 1.5:
        return "medium"
    return "low"
```

### Anti-Patterns to Avoid
- **Modifying existing ensemble artifacts in-place during ablation:** Always save ablation models to a separate directory (`models/ensemble_ablation/`), only copy to production if results improve.
- **Importing from scripts:** The ablation script should call functions from `src/` modules, not import from other scripts. If `run_feature_selection.py` logic is needed, call its constituent functions directly from `src/feature_selector.py` and `src/feature_engineering.py`.
- **Hardcoding feature lists:** The ablation must use `get_feature_columns()` to discover features dynamically, not manually list market features.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature selection | Custom market feature selector | `select_features_for_fold()` from `feature_selector.py` | Already handles SHAP ranking, correlation filtering, holdout exclusion |
| Ensemble training | New training pipeline | `train_ensemble()` from `ensemble_training.py` | Full XGB+LGB+CB+Ridge pipeline with walk-forward CV |
| Holdout evaluation | Custom holdout logic | `evaluate_holdout()` from `prediction_backtester.py` | Includes leakage guard (checks training_seasons) |
| SHAP computation | Manual feature importance | `shap.TreeExplainer` already used in `feature_selector.py` | Handles tree model SHAP natively |
| Walk-forward CV | Custom CV splitter | `walk_forward_cv_with_oof()` from `ensemble_training.py` | Produces OOF predictions for stacking |

**Key insight:** The entire ablation pipeline is an orchestration of existing functions. The only new logic is CLV computation (trivial) and the comparison report formatting.

## Common Pitfalls

### Pitfall 1: CLV Sign Convention
**What goes wrong:** Confusing whether positive CLV means the model is good or bad.
**Why it happens:** Different sources define CLV differently (some use closing - model, some use model - closing).
**How to avoid:** D-17 defines it clearly: CLV = `predicted_margin - spread_line`. Positive = model line was closer to the actual outcome. Verify with a test case: if model predicts home by 7, spread is -3 (home favored by 3), and home wins by 10, CLV = 7 - (-3) = 10. The model's prediction of 7 was closer to actual (10) than the spread (-3), so positive CLV is correct.
**Warning signs:** Mean CLV that is implausibly large (>5 points) or always positive -- indicates a sign or formula error.

### Pitfall 2: Holdout Leakage in Ablation
**What goes wrong:** Accidentally including 2024 holdout data in feature selection or training during ablation.
**Why it happens:** The ablation modifies the feature selection pipeline; easy to forget the holdout guard.
**How to avoid:** Use the existing `_assert_no_holdout()` guard in `feature_selector.py`. The `find_optimal_feature_count()` function already raises `ValueError` if holdout season is in the data. Also use `evaluate_holdout()` which checks `training_seasons`.
**Warning signs:** ATS accuracy above 58% on holdout (LEAKAGE_THRESHOLD).

### Pitfall 3: Market Features NaN for 2022-2024
**What goes wrong:** Market features (opening_spread, opening_total) are only available for 2016-2021 (SBRO data). For 2022-2024 they are NaN.
**Why it happens:** SBRO archives only cover 2016-2021; no free opening line source for 2022+.
**How to avoid:** D-03 specifies: XGBoost/LightGBM/CatBoost handle NaN natively. Ridge meta-learner already fills NaN with 0. No special handling needed. The ablation tests whether market-informed feature selection on 2016-2021 training data improves predictions even when market features are NaN at prediction time (2024 holdout).
**Warning signs:** If feature selection picks opening_spread as top feature, it will be NaN for all holdout games -- the model must still work via other features that were selected.

### Pitfall 4: Ablation Overwrites Production Ensemble
**What goes wrong:** Retraining writes to `models/ensemble/` and corrupts the production P30 baseline.
**Why it happens:** `train_ensemble()` defaults to `ENSEMBLE_DIR` which is `models/ensemble/`.
**How to avoid:** Pass `ensemble_dir="models/ensemble_ablation/"` explicitly. Only copy to production after confirming improvement.
**Warning signs:** `models/ensemble/metadata.json` timestamp changes during ablation.

### Pitfall 5: Feature Count Mismatch Between Baseline and Ablation
**What goes wrong:** The ablation selects a different number of features than P30 (310 features). If fewer features are selected, this may or may not be better.
**Why it happens:** Adding market features to the candidate pool changes correlation structure and SHAP rankings.
**How to avoid:** This is expected behavior per D-01. The ablation lets SHAP decide the optimal feature count via CV. Document the feature count difference in the report.
**Warning signs:** None -- this is a feature, not a bug. The comparison is on holdout accuracy, not feature count.

## Code Examples

### CLV Computation (verified pattern from existing codebase)
```python
# Source: prediction_backtester.py evaluate_ats() pattern
def evaluate_clv(df: pd.DataFrame) -> pd.DataFrame:
    """Add CLV column: predicted_margin - spread_line."""
    df = df.copy()
    df["clv"] = df["predicted_margin"] - df["spread_line"]
    return df
```

### CLV by Tier (verified pattern from existing codebase)
```python
# Source: compute_season_stability() groupby pattern + D-15 tier thresholds
def compute_clv_by_tier(df: pd.DataFrame) -> pd.DataFrame:
    """Compute CLV metrics per confidence tier."""
    edge = (df["predicted_margin"] - df["spread_line"]).abs()
    df = df.copy()
    df["tier"] = pd.cut(
        edge,
        bins=[-float("inf"), 1.5, 3.0, float("inf")],
        labels=["low", "medium", "high"],
    )
    rows = []
    for tier, group in df.groupby("tier", observed=True):
        rows.append({
            "tier": str(tier),
            "games": len(group),
            "mean_clv": float(group["clv"].mean()),
            "median_clv": float(group["clv"].median()),
            "pct_beating_close": float((group["clv"] > 0).mean()),
        })
    return pd.DataFrame(rows)
```

### Ablation Script Core Flow (using existing functions)
```python
# Source: existing train_ensemble.py + backtest_predictions.py patterns
from feature_engineering import assemble_multiyear_features, get_feature_columns
from ensemble_training import load_ensemble, predict_ensemble, train_ensemble
from prediction_backtester import evaluate_ats, evaluate_holdout, evaluate_clv

# Step 1: Baseline evaluation
spread_models, total_models, baseline_meta = load_ensemble("models/ensemble/")
all_data = assemble_multiyear_features()
# ... predict + evaluate_ats + evaluate_holdout -> baseline_accuracy

# Step 2: Re-run feature selection (market features are already candidates)
# Uses find_optimal_feature_count() + run_final_selection() from run_feature_selection.py

# Step 3: Retrain ensemble to separate directory
train_ensemble(all_data, new_features, ensemble_dir="models/ensemble_ablation/")

# Step 4: Evaluate ablation on holdout
# ... load ablation ensemble, predict, evaluate_holdout -> ablation_accuracy

# Step 5: Compare + SHAP report
```

### SHAP Importance Report (existing pattern from feature_selector.py)
```python
# Source: feature_selector.py uses shap.TreeExplainer
import shap
import xgboost as xgb

explainer = shap.TreeExplainer(xgb_model)
shap_values = explainer.shap_values(X_train)
importance = dict(zip(feature_cols, np.abs(shap_values).mean(axis=0)))
# Sort and format as text table for report
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single XGBoost (v1.4) | XGB+LGB+CB+Ridge stacking (v2.0) | Phase 30 | 50% -> 53% ATS on holdout |
| Manual feature selection | SHAP-based CV-validated selection | Phase 29 | Optimal 310-feature P30 set |
| Performance-only features | Performance + market data candidates | Phase 33 | opening_spread, opening_total available |

**Current production:** P30 Ensemble with 310 selected features, 53.0% ATS accuracy, +$3.09 profit on sealed 2024 holdout.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | pytest runs from project root: `python -m pytest tests/ -v` |
| Quick run command | `python -m pytest tests/test_prediction_backtester.py -x` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLV-01 | CLV computation: predicted_margin - spread_line per game | unit | `python -m pytest tests/test_prediction_backtester.py::TestCLVEvaluation -x` | Wave 0 |
| CLV-02 | CLV by tier with thresholds 3.0/1.5 | unit | `python -m pytest tests/test_prediction_backtester.py::TestCLVByTier -x` | Wave 0 |
| CLV-03 | CLV by season groupby | unit | `python -m pytest tests/test_prediction_backtester.py::TestCLVBySeason -x` | Wave 0 |
| LINE-04 | Ablation compares baseline vs market features on holdout | integration | `python -m pytest tests/test_ablation.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_prediction_backtester.py -x`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_prediction_backtester.py::TestCLVEvaluation` -- new test class for evaluate_clv(), covers CLV-01
- [ ] `tests/test_prediction_backtester.py::TestCLVByTier` -- new test class for compute_clv_by_tier(), covers CLV-02
- [ ] `tests/test_prediction_backtester.py::TestCLVBySeason` -- new test class for compute_clv_by_season(), covers CLV-03
- [ ] `tests/test_ablation.py` -- new test file for ablation script orchestration logic, covers LINE-04

*(Existing test infrastructure is sufficient -- no new framework install needed)*

## Open Questions

1. **Feature count CV search in ablation**
   - What we know: Existing `find_optimal_feature_count()` uses candidate counts [60, 80, 100, 120, 150]. The P30 selected 310 features (from a ~100 optimal count that expanded after correlation filtering).
   - What's unclear: Should the ablation use the same candidate counts, or should it include higher counts since the candidate pool is larger with market features?
   - Recommendation: Use the same [60, 80, 100, 120, 150] counts. The feature selection pipeline handles the pool size automatically -- adding 2 market features to 300+ candidates won't meaningfully change the optimal count.

2. **SHAP report format**
   - What we know: D-13 requires logging SHAP importance distribution. Existing `feature_selector.py` computes SHAP scores as a dict.
   - What's unclear: Whether to generate matplotlib plots or text tables.
   - Recommendation: Text table in CLI output (matches existing report style). Save SHAP scores to ablation metadata JSON for later analysis.

## Sources

### Primary (HIGH confidence)
- `src/prediction_backtester.py` -- evaluate_ats(), compute_season_stability(), evaluate_holdout(), compute_profit() patterns
- `src/feature_selector.py` -- SHAP-based selection with holdout guard, shap 0.49.1
- `src/ensemble_training.py` -- train_ensemble(), load_ensemble(), predict_ensemble()
- `scripts/run_feature_selection.py` -- find_optimal_feature_count(), run_final_selection(), save_metadata()
- `scripts/train_ensemble.py` -- CLI orchestration pattern
- `src/feature_engineering.py` -- get_feature_columns() with `_PRE_GAME_CONTEXT` including opening_spread, opening_total
- `models/ensemble/metadata.json` -- P30 ensemble with 310 selected features

### Secondary (MEDIUM confidence)
- `src/config.py` -- HOLDOUT_SEASON=2024, TRAINING_SEASONS=2016-2023, ENSEMBLE_DIR

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and in use
- Architecture: HIGH -- CLV is trivial computation, ablation orchestrates existing functions
- Pitfalls: HIGH -- based on direct code reading and understanding of the data pipeline

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable domain, no external dependencies changing)
