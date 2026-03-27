# Phase 29: Feature Selection - Research

**Researched:** 2026-03-25
**Domain:** SHAP-based feature importance, correlation filtering, walk-forward-safe feature selection
**Confidence:** HIGH

## Summary

Phase 29 reduces ~303 features to an optimal 80-120 subset using a three-step pipeline: quick SHAP pre-ranking, correlation filtering (r > 0.90), and CV-validated cutoff search. All selection runs inside walk-forward CV folds using only training data, never touching the 2024 holdout. The final selected feature list is persisted in `src/config.py` as `SELECTED_FEATURES`.

The technical stack is already installed: SHAP 0.49.1 with TreeExplainer works correctly with XGBoost 2.1.4 (verified locally). The primary implementation is a new `src/feature_selector.py` module that reuses the existing `walk_forward_cv()` fold structure from `model_training.py`. The current model has 283 features with 75 roll3/roll6 pairs that are almost certainly correlated above 0.90 -- these are the primary targets for correlation filtering.

**Primary recommendation:** Create `src/feature_selector.py` with a `FeatureSelectionResult` dataclass and a `select_features()` function that runs the full pipeline inside CV folds, then a `scripts/run_feature_selection.py` CLI that orchestrates the CV-validated cutoff search across candidate counts.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Pipeline order: quick SHAP pre-rank -> correlation filter (r > 0.90, keep higher-SHAP-ranked of each pair) -> final SHAP pruning to target count
- **D-02:** Correlation threshold: r > 0.90 Pearson correlation triggers pair removal
- **D-03:** When dropping one from a correlated pair, keep the feature with higher SHAP importance (pre-ranked before correlation step)
- **D-04:** All selection steps run inside each walk-forward CV fold using only that fold's training data -- no full-dataset selection
- **D-05:** Use CV-validated cutoff -- try multiple counts (60, 80, 100, 120, 150) and pick the one with best walk-forward CV MAE
- **D-06:** Feature budget ceiling remains 150 (from STATE.md)
- **D-07:** The optimal count is determined empirically, not fixed -- could land anywhere in the tested range
- **D-08:** 2024 season data is excluded from all feature selection operations -- a test asserts this
- **D-09:** Selection metadata records which seasons were used for each fold's selection
- **D-10:** After finding optimal feature count, retrain XGBoost spread + total models on the reduced feature set
- **D-11:** Run full backtest comparing reduced-feature XGBoost vs v1.4 baseline (303-feature XGBoost)
- **D-12:** Report ATS accuracy, O/U accuracy, and vig-adjusted profit at -110 for both configurations
- **D-13:** If reduced features don't improve or match baseline, investigate before proceeding to Phase 30
- **D-14:** Persist `SELECTED_FEATURES` list in `src/config.py` for Phase 30 to import
- **D-15:** Save detailed metadata to `models/feature_selection/metadata.json` with: selected features, drop reasons (correlation vs low importance), SHAP scores, correlated pairs, optimal cutoff, CV MAE at each cutoff
- **D-16:** `get_feature_columns()` in feature_engineering.py unchanged -- the selection is applied downstream in model training, not at assembly time (assembly still produces all 303 features)

### Claude's Discretion
- SHAP computation method (TreeExplainer vs KernelExplainer)
- Exact implementation of CV-validated cutoff loop
- Test structure and organization
- How to handle features with zero variance in some CV folds
- Visualization of SHAP importance / correlation heatmap (optional CLI output)

### Deferred Ideas (OUT OF SCOPE)
- Recursive feature elimination (RFE)
- Boruta / BorutaSHAP
- Feature interaction detection (Phase 31)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FSEL-01 | Remove highly correlated features (r > 0.90) to reduce redundancy | Correlation filtering step in pipeline; 75 roll3/roll6 pairs are primary targets; use pandas `.corr()` with abs threshold |
| FSEL-02 | Compute SHAP importance scores and prune low-signal features | SHAP 0.49.1 TreeExplainer verified working with XGBoost 2.1.4; mean absolute SHAP values for ranking |
| FSEL-03 | Run feature selection inside walk-forward CV folds (not on full dataset) | Reuse `VALIDATION_SEASONS` fold structure from `model_training.py`; selection in each fold's training split |
| FSEL-04 | Enforce holdout season exclusion from all feature selection operations | Guard: `assert data['season'].max() < HOLDOUT_SEASON` before any SHAP/correlation computation |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shap | 0.49.1 | TreeExplainer for feature importance | Already installed; exact computation for tree models, not approximate |
| xgboost | 2.1.4 | Base model for SHAP computation | Already the project's model; TreeExplainer is native to XGBoost |
| pandas | (installed) | Correlation matrix computation | `DataFrame.corr(method='pearson')` is the standard approach |
| numpy | (installed) | Mean absolute SHAP aggregation | Array operations for SHAP value summarization |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scikit-learn | (installed) | `mean_absolute_error` for CV evaluation | Already used in `model_training.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SHAP TreeExplainer | XGBoost native `feature_importances_` (gain) | Gain is faster but less robust; SHAP accounts for feature interactions -- use SHAP per D-01 |
| SHAP TreeExplainer | KernelExplainer | KernelExplainer is model-agnostic but 100x slower and approximate; TreeExplainer is exact for XGBoost |
| Pearson correlation | Spearman rank | Pearson catches linear redundancy which is the primary concern with roll3/roll6 pairs; Spearman adds marginal value here |

**Discretion recommendation:** Use TreeExplainer (not KernelExplainer). It is exact for XGBoost trees, runs in seconds on 303 features x ~2,100 rows, and is already verified working in the project environment.

## Architecture Patterns

### Recommended Project Structure
```
src/
  feature_selector.py          # NEW: FeatureSelectionResult, select_features(), correlation filter
  config.py                    # MODIFIED: add SELECTED_FEATURES list
  model_training.py            # UNMODIFIED (reuse walk_forward_cv pattern)
  feature_engineering.py       # UNMODIFIED (D-16: assembly unchanged)

scripts/
  run_feature_selection.py     # NEW: CLI orchestrating CV-validated cutoff search + retrain + backtest

models/
  feature_selection/
    metadata.json              # D-15: detailed selection metadata

tests/
  test_feature_selector.py     # NEW: unit + integration tests for selection pipeline
```

### Pattern 1: FeatureSelectionResult Dataclass
**What:** A result container holding selected features, drop reasons, SHAP scores, and metadata.
**When to use:** Returned by `select_features()` for each fold and by the CV-validated cutoff search.
**Example:**
```python
@dataclass
class FeatureSelectionResult:
    """Result of feature selection pipeline."""
    selected_features: List[str]
    dropped_correlation: Dict[str, str]   # dropped_feat -> kept_feat (the correlated partner)
    dropped_low_importance: List[str]
    shap_scores: Dict[str, float]         # feature -> mean |SHAP|
    correlated_pairs: List[Tuple[str, str, float]]  # (feat_a, feat_b, r)
    n_original: int
    n_after_correlation: int
    n_selected: int
    fold_seasons: Optional[List[int]]     # D-09: which seasons used
```

### Pattern 2: Per-Fold Feature Selection (FSEL-03)
**What:** Selection logic runs inside each CV fold using only the fold's training data.
**When to use:** Every time feature selection is invoked -- never on the full dataset.
**Example:**
```python
def select_features_for_fold(
    train_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    target_count: int,
    correlation_threshold: float = 0.90,
    params: Optional[Dict] = None,
) -> FeatureSelectionResult:
    """Run feature selection on a single fold's training data.

    Steps (D-01):
    1. Train quick XGBoost on train_data -> compute SHAP -> rank features
    2. Compute correlation matrix -> remove one of each pair with r > threshold
       (keep the one with higher SHAP rank per D-03)
    3. Truncate to target_count features by SHAP rank
    """
    # Guard: holdout exclusion (FSEL-04)
    assert train_data["season"].max() < HOLDOUT_SEASON, \
        f"Holdout season {HOLDOUT_SEASON} found in training data"

    # Step 1: Quick SHAP pre-rank
    model = xgb.XGBRegressor(**params)
    model.fit(train_data[feature_cols], train_data[target_col], verbose=False)
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(train_data[feature_cols])
    mean_shap = np.mean(np.abs(shap_values), axis=0)
    shap_rank = {col: score for col, score in zip(feature_cols, mean_shap)}

    # Step 2: Correlation filter
    corr_matrix = train_data[feature_cols].corr(method="pearson").abs()
    # ... remove lower-SHAP of each pair with r > threshold

    # Step 3: Truncate to target_count
    surviving = sorted(surviving_features, key=lambda f: shap_rank[f], reverse=True)
    selected = surviving[:target_count]

    return FeatureSelectionResult(...)
```

### Pattern 3: CV-Validated Cutoff Search (D-05)
**What:** Try multiple feature counts (60, 80, 100, 120, 150) and pick the one with best walk-forward CV MAE.
**When to use:** Once, to find the optimal count before final retrain.
**Example:**
```python
def find_optimal_feature_count(
    all_data: pd.DataFrame,
    feature_cols: List[str],
    target_col: str,
    candidate_counts: List[int] = [60, 80, 100, 120, 150],
) -> Tuple[int, Dict[int, float]]:
    """Evaluate each candidate count via walk-forward CV.

    For each count:
    1. For each CV fold, run select_features_for_fold() on fold training data
    2. Train XGBoost on fold training data with THAT fold's selected features
    3. Predict on fold validation data
    4. Compute MAE across folds
    5. Pick count with lowest mean MAE
    """
    results = {}
    for count in candidate_counts:
        fold_maes = []
        for val_season in VALIDATION_SEASONS:
            train = all_data[all_data["season"] < val_season]
            val = all_data[all_data["season"] == val_season]
            # Select features using only training data
            sel = select_features_for_fold(train, feature_cols, target_col, count)
            # Train and evaluate with selected features
            model = xgb.XGBRegressor(**CONSERVATIVE_PARAMS)
            model.fit(train[sel.selected_features], train[target_col], ...)
            preds = model.predict(val[sel.selected_features])
            fold_maes.append(mean_absolute_error(val[target_col], preds))
        results[count] = np.mean(fold_maes)

    best_count = min(results, key=results.get)
    return best_count, results
```

### Anti-Patterns to Avoid
- **Full-dataset feature selection:** Running SHAP or correlation on all data (including validation folds) inflates selection quality. Every selection step MUST use only the current fold's training split.
- **Using HOLDOUT_SEASON data in any selection step:** The 2024 season must never appear in training data for SHAP computation or correlation analysis. An explicit assert guards this.
- **Different features per fold in final model:** The CV-validated cutoff finds the optimal COUNT, then the final model uses features selected from ALL training data (2016-2023) at that count. Each fold uses its own selected features only for MAE evaluation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature importance | Custom gain extraction | `shap.TreeExplainer(model).shap_values(X)` | SHAP is more robust than gain, accounts for interactions |
| Correlation matrix | Manual pairwise loops | `pd.DataFrame.corr(method='pearson')` | Vectorized, handles NaN, returns full matrix |
| Feature ranking | Custom sorting logic | `np.argsort(mean_abs_shap)[::-1]` | Standard numpy pattern, no edge cases |

## Common Pitfalls

### Pitfall 1: Feature Selection on Full Dataset (Data Snooping)
**What goes wrong:** Running SHAP importance or correlation analysis on all data (including validation folds) produces an optimistically biased feature set that overfits to validation data.
**Why it happens:** It is simpler to run selection once on all data than per-fold. Developers rationalize "correlation is a property of the features, not the target" -- but SHAP importance IS target-dependent and MUST be computed per-fold.
**How to avoid:** Feature selection runs inside each walk-forward fold (D-04). The `select_features_for_fold()` function takes only training data as input. Tests verify no full-dataset selection occurs.
**Warning signs:** CV MAE looks great but holdout MAE degrades vs baseline.

### Pitfall 2: SHAP Computation on Large Data is Slow
**What goes wrong:** Computing SHAP on all ~2,100 training rows with 303 features takes significant time per fold, and with 5 folds x 5 candidate counts = 25 SHAP computations, the total runtime becomes prohibitive.
**Why it happens:** TreeExplainer is exact but O(T * L * D * N) where T=trees, L=leaves, D=depth, N=samples.
**How to avoid:** Use a subsample of training data for SHAP computation (e.g., 500 rows). SHAP importance rankings are stable with 500+ samples. The model is still trained on all data; only the SHAP explanation uses a subsample.
**Warning signs:** Feature selection CLI takes more than 10 minutes per candidate count.

### Pitfall 3: Features with Zero Variance in Some Folds
**What goes wrong:** Early folds (train on 2016-2018 only) may have features with zero variance (e.g., a player quality metric only available from 2020+). These cause XGBoost to ignore them and SHAP to assign 0.0, but they may be valuable in later folds.
**Why it happens:** Walk-forward CV starts with small training sets. Player quality features from Phase 28 only have data from certain seasons.
**How to avoid:** Drop zero-variance features from the fold's feature list before SHAP computation. These features are neither selected nor penalized -- they are simply not considered for that fold. The final selection uses the largest fold (train on 2016-2022, val on 2023) which has the most complete data.
**Warning signs:** Features that appear selected in late folds but absent from early folds.

### Pitfall 4: Correlated Pair Detection Missing Transitive Chains
**What goes wrong:** If A correlates with B (r=0.92) and B correlates with C (r=0.91) but A and C only correlate at r=0.80, naive pairwise filtering might keep both A and C. This isn't necessarily wrong, but it can leave residual multicollinearity.
**Why it happens:** Pairwise correlation filtering is greedy, not global.
**How to avoid:** Process pairs in order from highest to lowest correlation. When a feature is dropped, remove it from future pair considerations. This greedy approach resolves most transitive chains.
**Warning signs:** The selected feature set still has pairs with r > 0.85 (below threshold but high).

### Pitfall 5: Confusing Per-Fold Selection with Final Model Features
**What goes wrong:** Using each fold's independently-selected features for the final model, resulting in a jagged feature set. Or worse, taking the union of all folds' selected features (which defeats the purpose of selection).
**Why it happens:** The CV loop selects different features per fold, leading to confusion about what the final model uses.
**How to avoid:** The CV loop is ONLY for evaluating which feature COUNT is best. After finding the optimal count, run one final selection on all training data (2016-2023) at that count. That single feature list becomes `SELECTED_FEATURES` in config.py.
**Warning signs:** Feature count in `SELECTED_FEATURES` doesn't match the optimal count from CV.

## Code Examples

### SHAP TreeExplainer Usage (Verified)
```python
# Source: Verified locally with SHAP 0.49.1 + XGBoost 2.1.4
import shap
import numpy as np
import xgboost as xgb

model = xgb.XGBRegressor(**CONSERVATIVE_PARAMS)
model.fit(X_train, y_train, verbose=False)

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_train)  # shape: (n_samples, n_features), type: np.ndarray
mean_abs_shap = np.mean(np.abs(shap_values), axis=0)  # shape: (n_features,)

# Rank features by importance
feature_importance = dict(zip(feature_cols, mean_abs_shap))
ranked = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)
```

### Correlation Filtering with SHAP-Informed Pair Resolution (D-03)
```python
def filter_correlated_features(
    data: pd.DataFrame,
    feature_cols: List[str],
    shap_rank: Dict[str, float],
    threshold: float = 0.90,
) -> Tuple[List[str], Dict[str, str], List[Tuple[str, str, float]]]:
    """Remove one of each highly correlated pair, keeping higher-SHAP feature.

    Returns:
        surviving: features that passed the filter
        dropped_map: {dropped_feat: kept_feat}
        pairs: [(feat_a, feat_b, correlation)]
    """
    corr = data[feature_cols].corr(method="pearson").abs()

    dropped = set()
    dropped_map = {}
    pairs = []

    # Get upper triangle pairs above threshold, sorted by correlation (highest first)
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    high_corr = [
        (col, row, upper.loc[row, col])
        for col in upper.columns
        for row in upper.index
        if upper.loc[row, col] > threshold
    ]
    high_corr.sort(key=lambda x: x[2], reverse=True)

    for feat_a, feat_b, r in high_corr:
        if feat_a in dropped or feat_b in dropped:
            continue
        pairs.append((feat_a, feat_b, float(r)))
        # Drop the one with lower SHAP importance (D-03)
        if shap_rank.get(feat_a, 0) >= shap_rank.get(feat_b, 0):
            dropped.add(feat_b)
            dropped_map[feat_b] = feat_a
        else:
            dropped.add(feat_a)
            dropped_map[feat_a] = feat_b

    surviving = [f for f in feature_cols if f not in dropped]
    return surviving, dropped_map, pairs
```

### Holdout Guard Pattern (FSEL-04)
```python
# Source: Extends existing pattern from model_training.py
from config import HOLDOUT_SEASON

def _assert_no_holdout(data: pd.DataFrame, context: str) -> None:
    """Raise if holdout season data is present."""
    if HOLDOUT_SEASON in data["season"].values:
        raise ValueError(
            f"Holdout season {HOLDOUT_SEASON} found in data during {context}. "
            "Feature selection must never use holdout data."
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XGBoost gain importance | SHAP TreeExplainer | SHAP 0.40+ (2022) | SHAP accounts for feature interactions; gain can be misleading with correlated features |
| Global feature selection | Per-fold selection in walk-forward CV | Standard practice in temporal ML | Prevents selection leakage; more conservative but honest |
| Fixed feature count | CV-validated cutoff search | Standard hyperparameter tuning | Data-driven rather than arbitrary |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed, 449 tests passing) |
| Config file | `tests/` directory, no pytest.ini needed |
| Quick run command | `python -m pytest tests/test_feature_selector.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FSEL-01 | Correlated feature pairs (r > 0.90) are removed | unit | `python -m pytest tests/test_feature_selector.py::TestCorrelationFilter -x` | Wave 0 |
| FSEL-02 | SHAP scores computed and low-importance features pruned | unit | `python -m pytest tests/test_feature_selector.py::TestSHAPRanking -x` | Wave 0 |
| FSEL-03 | Selection runs inside each CV fold (not full dataset) | unit | `python -m pytest tests/test_feature_selector.py::TestPerFoldSelection -x` | Wave 0 |
| FSEL-04 | 2024 holdout data excluded from all selection ops | unit | `python -m pytest tests/test_feature_selector.py::TestHoldoutExclusion -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_feature_selector.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_feature_selector.py` -- covers FSEL-01 through FSEL-04
- [ ] Synthetic data fixtures for feature selection (extend pattern from `test_model_training.py::_make_synthetic_game_data`)

## Open Questions

1. **SHAP subsample size for speed**
   - What we know: TreeExplainer on 303 features x 2,100 rows runs in seconds per fold. With 25 total SHAP computations (5 folds x 5 counts), total runtime should be under 5 minutes.
   - What's unclear: Whether player quality features (Phase 28) add enough rows/complexity to change this timing.
   - Recommendation: Start without subsampling. Add a `shap_sample_size` parameter (default None = use all) that can be set if runtime exceeds 10 minutes.

2. **Handling the final selection vs per-fold selection**
   - What we know: CV loop selects per-fold for MAE evaluation. Final model needs one definitive feature list.
   - What's unclear: Whether to use intersection, union, or independent final selection.
   - Recommendation: Run one final `select_features_for_fold()` on ALL training data (2016-2023) at the optimal count. This is the cleanest approach and matches D-14.

## Sources

### Primary (HIGH confidence)
- Local verification: SHAP 0.49.1 TreeExplainer with XGBoost 2.1.4 (tested in project venv)
- `src/model_training.py` -- walk-forward CV implementation, `VALIDATION_SEASONS`, `HOLDOUT_SEASON` guard pattern
- `src/feature_engineering.py` -- `get_feature_columns()` returns 283 features (verified via model metadata)
- `src/config.py` -- `CONSERVATIVE_PARAMS`, `PREDICTION_SEASONS`, `TRAINING_SEASONS`
- `models/spread/metadata.json` -- 283 features, CV mean_mae 10.49, trained 2026-03-23

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` -- correlation filter + SHAP recommendation
- `.planning/research/PITFALLS.md` -- feature selection before holdout split warning
- `.planning/research/ARCHITECTURE.md` -- feature_selector.py module architecture

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and verified locally
- Architecture: HIGH - extends existing walk-forward CV pattern, clear module boundaries
- Pitfalls: HIGH - based on known ML best practices and project-specific leakage history

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable domain, no library changes expected)
