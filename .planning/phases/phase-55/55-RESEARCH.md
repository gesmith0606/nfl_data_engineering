# Phase 55: Full-Feature Residual Deployment - Research

**Researched:** 2026-04-07
**Domain:** ML residual modeling, feature selection, regularization for fantasy football projections
**Confidence:** HIGH

## Summary

Phase 54 revealed that Ridge regression with all 466+ features DEGRADES performance across all positions. The current 42-feature Ridge residual achieves -3.1% improvement for WR and -4.3% for TE, but full 466-feature Ridge overfits noise. Phase 55 must pivot from "deploy full features with Ridge" to "find the right model + feature subset that unlocks improvement from the 466-feature space."

The core problem is clear: Ridge cannot effectively regularize 466 features with ~16K training samples (WR) or ~8K (TE). The features-to-samples ratio is too high for a linear model with L2-only penalty. Three complementary strategies can address this: (1) SHAP-based feature selection to find the optimal subset between 42 and 466 features, (2) LightGBM residual models with early stopping (already proven in the codebase for game predictions and quantile models), and (3) Lasso/ElasticNet to automatically zero out noise features.

**Primary recommendation:** Replace Ridge with LightGBM residual models using SHAP-selected features (target 80-120 features), applying the same walk-forward CV framework already in `player_model_training.py`. Deploy for WR and TE only; keep QB on XGBoost direct and RB on heuristic.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RES-01 | WR residual with full features (target: -10%+) | LightGBM residual + SHAP selection on 80-120 features. Graph features (QB-WR chemistry, game script, red zone, WR matchup) are high-value WR-specific signals not in the 42-feature set. |
| RES-02 | TE residual with full features (target: -8%+) | Same LightGBM approach. TE-specific graph features (TE matchup, red zone) plus scheme features provide incremental signal. |
| RES-03 | QB residual evaluation | Phase 54 showed QB residual catastrophically overfits. Recommend: evaluate LightGBM residual as a formality, but expect heuristic+XGB to remain best. |
| RES-04 | RB residual evaluation | Same as QB — Phase 54 showed RB overfits. Evaluate LightGBM but expect heuristic to remain best. |
| RES-05 | Router update | Update `hybrid_projection.py` to support LightGBM residual models alongside Ridge. Router: QB->XGB, RB->heuristic, WR->LightGBM residual, TE->LightGBM residual. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lightgbm | 4.6.0 | Residual model (replaces Ridge) | Already installed, proven in ensemble_training.py and quantile_models.py. Tree-based with early stopping handles high-dimensional features without manual regularization. [VERIFIED: installed in venv] |
| scikit-learn | 1.6.1 | Feature selection pipeline, RidgeCV/ElasticNetCV baselines | Already installed. SimpleImputer + Pipeline pattern used throughout codebase. [VERIFIED: installed in venv] |
| shap | 0.49.1 | Feature importance ranking for selection | Already installed, used in feature_selector.py for game prediction feature selection. [VERIFIED: installed in venv] |
| xgboost | 2.1.4 | SHAP-based feature ranking (TreeExplainer) | Already installed, used in feature_selector.py. [VERIFIED: installed in venv] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| joblib | (bundled) | Model persistence | Save/load LightGBM residual models to models/residual/ |

**Installation:** No new dependencies needed. All libraries already installed.

## Architecture Patterns

### Current Residual Architecture
```
src/hybrid_projection.py
├── _create_residual_pipeline()     # Returns Pipeline(SimpleImputer + RidgeCV)
├── train_residual_model()          # Walk-forward CV with Ridge
├── train_and_save_residual_models() # Production training + persistence
├── load_residual_model()           # Load saved Pipeline from disk
└── apply_residual_correction()     # Apply correction at inference time
```

### Recommended Changes
```
src/hybrid_projection.py
├── _create_residual_pipeline()     # KEEP: Ridge baseline (fallback)
├── _create_lgb_residual_model()    # NEW: LightGBM with early stopping
├── _select_residual_features()     # NEW: SHAP-based selection (reuse feature_selector.py)
├── train_residual_model()          # MODIFY: support model_type='ridge'|'lgb'
├── train_and_save_residual_models() # MODIFY: per-position model type routing
├── load_residual_model()           # MODIFY: detect model type from metadata
└── apply_residual_correction()     # MODIFY: handle LightGBM predictions
```

### Pattern: LightGBM Residual with Feature Selection
**What:** Train LightGBM on heuristic residuals (actual - heuristic) with SHAP-selected features and early stopping.
**When to use:** WR and TE positions where residual correction has shown improvement.
**Example:**
```python
# Source: pattern from quantile_models.py (QUANTILE_LGB_PARAMS) + feature_selector.py
RESIDUAL_LGB_PARAMS = {
    "objective": "regression",
    "n_estimators": 500,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "verbose": -1,
    "n_jobs": -1,
    "random_state": 42,
}

# Feature selection: reuse select_features_for_fold from feature_selector.py
# Target count: 80-120 (between current 42 and full 466)
result = select_features_for_fold(
    train_data, feature_cols, target_col="residual",
    target_count=100, correlation_threshold=0.90,
)
selected_features = result.selected_features

# Train with early stopping
model = lgb.LGBMRegressor(**RESIDUAL_LGB_PARAMS)
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    callbacks=[lgb.early_stopping(50, verbose=False)],
)
```

### Anti-Patterns to Avoid
- **Full 466 features with Ridge:** Phase 54 proved this overfits. Ridge cannot zero out noise features, only shrink them toward zero. With 466 features and ~16K samples, the noise dominates.
- **Same feature set for all positions:** QB-WR chemistry features are meaningless for RB. Position-specific feature selection is essential.
- **Training on holdout season (2025):** Must exclude HOLDOUT_SEASON. The `_assert_no_holdout` guard from `feature_selector.py` should be applied.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature selection | Custom importance ranking | `feature_selector.select_features_for_fold()` | Already has SHAP + correlation filtering + holdout guard. Proven in game prediction pipeline. |
| Walk-forward CV | New CV loop | `player_model_training.player_walk_forward_cv()` | Already handles season-based splits, OOF collection, early stopping kwargs. |
| LightGBM training | Raw lgb.train() | `lgb.LGBMRegressor` with early_stopping callback | Pattern already in `quantile_models.py` and `ensemble_training.py`. Consistent API. |
| Model persistence | Custom pickle | `joblib.dump/load` + JSON metadata | Same pattern as current `train_and_save_residual_models()`. |

## Common Pitfalls

### Pitfall 1: Feature Selection Leakage
**What goes wrong:** Running SHAP importance on the full dataset (including validation seasons) before walk-forward CV creates look-ahead bias.
**Why it happens:** Feature importance depends on the target distribution. If you select features using 2024 data, then validate on 2024, you've leaked.
**How to avoid:** Run `select_features_for_fold()` inside each CV fold, on training data only. The function already has `_assert_no_holdout()`.
**Warning signs:** Validation MAE much better than holdout MAE; feature importance ranks that change dramatically across folds.

### Pitfall 2: LightGBM Overfitting Residuals
**What goes wrong:** Even with early stopping, LightGBM can overfit small residual targets (mean ~0, small variance).
**Why it happens:** Residuals are inherently noisy — they're the part the heuristic couldn't predict. Trees can memorize player-specific patterns.
**How to avoid:** Conservative hyperparameters (max_depth=4, min_child_samples=20), high regularization (reg_lambda=1.0), subsample=0.8, colsample_bytree=0.7. Monitor train vs val gap.
**Warning signs:** Train MAE << val MAE (gap > 1.0 points). Alpha selected by RidgeCV was already very high (RB: 33.9), indicating heavy regularization was needed.

### Pitfall 3: Position-Specific Feature Availability
**What goes wrong:** Some graph features (QB-WR chemistry, WR matchup) are NaN for non-WR/TE positions. Including them in feature selection for QB/RB wastes feature budget and creates imputation artifacts.
**Why it happens:** `player_feature_engineering.py` already sets these to NaN for non-receivers (line 836-838), but `get_player_feature_columns()` returns all numeric columns regardless.
**How to avoid:** Filter feature candidates by position before selection. Remove columns that are >90% NaN for the position being trained.

### Pitfall 4: Residual Magnitude Expectations
**What goes wrong:** Expecting -10%+ improvement when the heuristic is already well-tuned (MAE 4.77).
**Why it happens:** Phase 54 tuned the heuristic aggressively (RECENCY_WEIGHTS, ceiling shrinkage). Residuals are now smaller and noisier.
**How to avoid:** Set realistic targets. WR at 4.63 MAE -> -10% = 4.17 is ambitious. A more realistic target is -5% to -7% improvement per position.
**Warning signs:** If CV shows <1% improvement, the model is probably just fitting noise.

## Code Examples

### Feature Selection for Residuals (adapting existing pattern)
```python
# Source: feature_selector.py (select_features_for_fold) adapted for residuals
from feature_selector import select_features_for_fold

# Filter to position-relevant features (>10% non-NaN)
pos_data = all_data[all_data["position"] == "WR"]
nan_rates = pos_data[feature_cols].isna().mean()
pos_features = [f for f in feature_cols if nan_rates[f] < 0.90]

# Run SHAP selection on residual target
result = select_features_for_fold(
    train_data=pos_data[pos_data["season"] < val_season],
    feature_cols=pos_features,
    target_col="residual",  # actual - heuristic
    target_count=100,
    correlation_threshold=0.90,
)
# result.selected_features: list of 100 best features
# result.shap_scores: feature -> importance
```

### LightGBM Residual Pipeline (adapting quantile pattern)
```python
# Source: quantile_models.py (QUANTILE_LGB_PARAMS) adapted for mean regression
import lightgbm as lgb
from sklearn.impute import SimpleImputer

# Impute NaN features
imputer = SimpleImputer(strategy="median")
X_train_imp = imputer.fit_transform(X_train)
X_val_imp = imputer.transform(X_val)

model = lgb.LGBMRegressor(
    objective="regression",
    n_estimators=500,
    max_depth=4,
    learning_rate=0.05,
    min_child_samples=20,
    subsample=0.8,
    colsample_bytree=0.7,
    reg_alpha=0.1,
    reg_lambda=1.0,
    verbose=-1,
    random_state=42,
)
model.fit(
    X_train_imp, y_train,
    eval_set=[(X_val_imp, y_val)],
    callbacks=[lgb.early_stopping(50, verbose=False)],
)
```

## Graph Features Inventory

49 graph-derived features are available in the feature vector. These are the primary candidates for improving WR/TE residuals beyond the base 42 features:

| Feature Group | Count | Position Relevance | Source Module |
|---------------|-------|-------------------|---------------|
| Injury cascade | 4 | All | `graph_feature_extraction.py` |
| WR matchup | 4 | WR | `graph_feature_extraction.py` |
| OL/RB | 5 | RB | `graph_feature_extraction.py` |
| TE matchup | 4 | TE | `graph_feature_extraction.py` |
| Scheme | 4 | RB, TE | `graph_feature_extraction.py` |
| QB-WR chemistry | 5 | WR, TE | `graph_qb_wr_chemistry.py` |
| Game script | 6 | All | `graph_game_script.py` |
| Red zone | 7 | WR, TE, RB | `graph_red_zone.py` |
| College networks | 10 | All (rookies) | `graph_college_networks.py` |

**High-value for WR:** QB-WR chemistry (5), WR matchup (4), red zone (7), game script (6) = 22 features
**High-value for TE:** TE matchup (4), QB-WR chemistry (5), red zone (7), scheme (4) = 20 features

## Feature Selection Strategy

### Recommended Approach: Two-Stage Selection
1. **Pre-filter by position:** Remove features >90% NaN for the target position. This eliminates WR-specific features when training RB, etc.
2. **SHAP selection:** Use `select_features_for_fold()` with target_count=100 on the residual (actual - heuristic). Run per CV fold to avoid leakage.
3. **Stable feature identification:** Take intersection of top-100 across CV folds. Features consistently selected across folds are the stable signal.

### Feature Count Sweet Spot
- **42 features (current):** Only Silver-layer rolling stats. Proven to work with Ridge.
- **80-120 features (target):** Silver stats + graph features + select interaction features. Enough signal without noise.
- **466+ features (full):** Too many for any linear model. LightGBM with selection could work, but pre-selection to 100 is safer.

## Model Comparison Plan

| Model | Features | Expected WR MAE | Expected TE MAE | Risk |
|-------|----------|----------------|----------------|------|
| Ridge (current 42) | 42 | 4.63 (-3.1% from heuristic) | 3.58 (-4.3%) | LOW — baseline |
| Ridge (full 466) | 466 | WORSE (Phase 54 result) | WORSE | N/A — already tested |
| ElasticNet (full 466) | 466 | ~4.55 | ~3.50 | MEDIUM — L1 may help |
| LightGBM (SHAP 100) | 100 | ~4.40-4.50 | ~3.40-3.50 | MEDIUM — best bet |
| LightGBM (full 466) | 466 | ~4.45-4.55 | ~3.45-3.55 | MEDIUM-HIGH — may overfit |

[ASSUMED] These MAE estimates are based on the general principle that tree models with early stopping handle high dimensions better than linear models, and that graph features contain position-specific signal not in the 42-feature set. Actual numbers must be validated through walk-forward CV.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ridge on all features | Ridge on 42 features | Phase 54 (2026-04-03) | Avoided overfitting; -3.1% WR, -4.3% TE |
| Simplified heuristic for training | Production heuristic for training | Phase 54 | Eliminated train/eval mismatch |
| Per-stat XGBoost models (QB) | Heuristic + residual correction (WR/TE) | Phase 53 | Hybrid approach adopted |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | LightGBM residual will outperform Ridge residual for WR/TE | Model Comparison | Main hypothesis of phase. If wrong, keep current Ridge 42-feature models. Low downside risk. |
| A2 | 80-120 SHAP-selected features is the sweet spot | Feature Selection | If optimal count is different (e.g., 50 or 200), the SHAP selection process will find it through the target_count parameter. |
| A3 | Graph features (QB-WR chemistry, red zone, game script) contain signal for WR residuals | Graph Features Inventory | If graph features are all noise, the SHAP selection will exclude them. No wasted effort beyond the selection computation. |
| A4 | QB and RB residuals will continue to underperform heuristic | Phase Requirements | Based on Phase 54 results. If LightGBM somehow helps, that's an upside surprise. |
| A5 | MAE improvement of -5% to -10% per position is achievable | Pitfall 4 | May only achieve -3% to -5%. The heuristic is well-tuned after Phase 54. |

## Open Questions

1. **Feature count sensitivity**
   - What we know: 42 works with Ridge, 466 fails with Ridge.
   - What's unclear: Where's the optimal count for LightGBM? Is it 80, 100, 150?
   - Recommendation: Sweep target_count in [60, 80, 100, 120, 150] during training. Record MAE at each.

2. **Cross-fold feature stability**
   - What we know: `select_features_for_fold` runs per fold. Features may differ across folds.
   - What's unclear: How stable is the selection? If features change 50% across folds, the model is fragile.
   - Recommendation: Compute Jaccard similarity of top-100 features across folds. If < 0.6, reduce target_count.

3. **Interaction with Phase 57 quantile models**
   - What we know: `quantile_models.py` already uses all features with LightGBM.
   - What's unclear: Should Phase 55 residual and Phase 57 quantile share the same feature selection?
   - Recommendation: Phase 55 operates on residuals; Phase 57 on raw targets. Different targets may have different optimal features. Keep separate.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pytest.ini` (project root) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RES-01 | WR LightGBM residual improves over heuristic | integration | `python -m pytest tests/test_residual_lgb.py::test_wr_residual_improvement -x` | Wave 0 |
| RES-02 | TE LightGBM residual improves over heuristic | integration | `python -m pytest tests/test_residual_lgb.py::test_te_residual_improvement -x` | Wave 0 |
| RES-03 | QB residual evaluated (may not ship) | integration | `python -m pytest tests/test_residual_lgb.py::test_qb_residual_evaluation -x` | Wave 0 |
| RES-04 | RB residual evaluated (may not ship) | integration | `python -m pytest tests/test_residual_lgb.py::test_rb_residual_evaluation -x` | Wave 0 |
| RES-05 | Router dispatches correct model per position | unit | `python -m pytest tests/test_residual_lgb.py::test_router_dispatch -x` | Wave 0 |
| INFRA-01 | All existing tests pass | regression | `python -m pytest tests/ -v` | Exists |
| INFRA-03 | No position regression | integration | `python -m pytest tests/test_residual_lgb.py::test_no_regression -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_residual_lgb.py` -- covers RES-01 through RES-05, INFRA-03
- [ ] Feature selection test for residuals (can extend existing `tests/test_feature_selector.py`)

## Security Domain

No security concerns for this phase. All operations are local ML training on local data files. No user input, no network operations, no credential handling.

## Sources

### Primary (HIGH confidence)
- `src/hybrid_projection.py` -- current Ridge residual implementation, 601 lines [VERIFIED: codebase]
- `src/feature_selector.py` -- SHAP + correlation feature selection, 240 lines [VERIFIED: codebase]
- `src/quantile_models.py` -- LightGBM quantile pattern with walk-forward CV [VERIFIED: codebase]
- `src/player_model_training.py` -- walk-forward CV framework, LightGBM integration [VERIFIED: codebase]
- `src/player_feature_engineering.py` -- 466+ feature assembly from 9+ Silver sources [VERIFIED: codebase]
- `models/residual/wr_residual_meta.json` -- current WR Ridge model: 483 features, alpha=8.29 [VERIFIED: local file]
- `models/residual/te_residual_meta.json` -- current TE Ridge model: 483 features, alpha=0.49 [VERIFIED: local file]
- `models/residual/rb_residual_meta.json` -- current RB Ridge model: 466 features, alpha=33.9 [VERIFIED: local file]

### Secondary (MEDIUM confidence)
- Phase 54 results (from user context) -- Ridge with 466 features degrades all positions [CITED: user-provided Phase 54 results]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in codebase
- Architecture: HIGH -- extending existing patterns (feature_selector, quantile_models, hybrid_projection)
- Pitfalls: HIGH -- derived from Phase 54 findings and codebase analysis
- Expected improvements: MEDIUM -- MAE targets are estimates; must be validated through CV

**Research date:** 2026-04-07
**Valid until:** 2026-05-07 (stable domain, no external dependency changes expected)
