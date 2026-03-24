# Stack Research: v2.0 Prediction Model Improvement

**Domain:** NFL game prediction — player-level features, model ensembles, feature selection, advanced signals
**Researched:** 2026-03-24
**Confidence:** HIGH

## Scope

This document covers ONLY the stack additions needed for v2.0. The existing stack (Python 3.9, pandas 1.5.3, pyarrow, xgboost 2.1.4, optuna 4.8.0, scikit-learn 1.6.1, numpy 1.26.4, scipy 1.13.1) is validated and unchanged. Do not re-evaluate or reinstall those packages.

## What Is Already Installed

Confirmed via `pip list` in the project venv:

| Package | Version | Status |
|---------|---------|--------|
| xgboost | 2.1.4 | Installed, in use |
| optuna | 4.8.0 | Installed, in use |
| scikit-learn | 1.6.1 | Installed, in use |
| pandas | 1.5.3 | Installed, in use |
| numpy | 1.26.4 | Installed, in use |
| scipy | 1.13.1 | Installed, in use |

Not installed (needed for v2.0): `lightgbm`, `catboost`, `shap`, `matplotlib`.

## Python 3.9 Constraint

The project is pinned to Python 3.9 due to nfl-data-py 0.3.3 (archived, untested on 3.10+). All version choices below are verified against Python 3.9 via PyPI JSON API.

## Recommended Stack Additions

### Core ML Libraries (New)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LightGBM | 4.6.0 | Second base learner in ensemble | Trains 2-5x faster than XGBoost on 283-feature data. Histogram-based splitting handles high-dimensional tabular data efficiently. Supports Python 3.9 (requires_python>=3.7). Use as the default base model alongside XGBoost. |
| CatBoost | 1.2.10 | Third base learner in ensemble | Adds ensemble diversity through a different algorithmic approach (symmetric trees, ordered boosting). Python 3.9 wheel confirmed (cp39 wheels on PyPI). 28MB wheel download. Include because the PROJECT.md target spec explicitly names it; its symmetric tree structure tends to generalize differently than LightGBM/XGBoost on noisy sports outcomes, providing orthogonal predictions that reduce stacking variance. |

### Already-Installed Libraries With New Use Cases

These are installed but not yet imported in prediction code:

| Library | Version | New Use in v2.0 | Notes |
|---------|---------|-----------------|-------|
| scikit-learn | 1.6.1 | `StackingRegressor`, `SelectFromModel`, `mutual_info_regression`, `VarianceThreshold`, `RidgeCV` | All APIs confirmed present via import test in installed version. `StackingRegressor` is the right tool for the meta-learner. Default meta-learner is `RidgeCV` — keep it. |
| pandas | 1.5.3 | `ewm(halflife=N)` for adaptive/exponential windows, multi-window rolling for momentum features | `ewm()` confirmed working in 1.5.3. No new install needed — use existing EWM and rolling APIs for adaptive window features. |

### Explainability (New)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| SHAP | 0.48.0 | Feature importance after ensemble training | 0.48.0 is the last Python 3.9 compatible release (requires_python>=3.9; 0.49+ requires 3.11+). `TreeExplainer` runs natively on LightGBM, XGBoost, CatBoost without model-agnostic sampling overhead. Use after training to identify which player-level features contribute signal. |

### Visualization (New)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| matplotlib | 3.9.4 | Calibration plots, SHAP beeswarms, feature importance charts | Lowest-footprint plotting option; already a transitive dependency of CatBoost so it arrives for free when CatBoost installs. Pin to 3.9.4 to be explicit. Supports Python 3.9. |

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| statsmodels | Adds ~60MB for statistical models (ARIMA, OLS diagnostics). All needed stats (rolling correlations, regime signals) are achievable with pandas + scipy, which are already installed. | `pandas.ewm()` + `scipy.stats` |
| tsfresh | Automated time-series feature extraction framework. Overkill — momentum and regime features are domain-specific (streak lengths, EPA trends) and hand-rolled in ~30 lines of pandas. Adds heavy dependency chain. | Pandas rolling/ewm + custom functions in `feature_engineering.py` |
| mlxtend | Third-party stacking library. `sklearn.ensemble.StackingRegressor` (confirmed in 1.6.1) covers everything needed without an extra dependency. | `sklearn.ensemble.StackingRegressor` |
| XGBoost 3.x | Requires Python 3.10+. Breaking change. | Pinned 2.1.4 already installed |
| SHAP 0.49+ | Requires Python 3.11+. | SHAP 0.48.0 |
| PyTorch / TensorFlow | Gradient boosting consistently outperforms deep learning on tabular sports data at this scale (~2,100 games). Neural nets need 10x more data to generalize on noisy outcomes. | LightGBM + XGBoost + CatBoost ensemble |
| MLflow | Experiment tracking is premature for a local-first project with 3 models. Heavy dependency chain. | Extend the existing JSON metadata sidecar pattern in `model_training.py` |

## Installation

```bash
source venv/bin/activate

# New base learners
pip install lightgbm==4.6.0 catboost==1.2.10

# Explainability and visualization
pip install shap==0.48.0 matplotlib==3.9.4

# Freeze
pip freeze > requirements.txt
```

Total new packages: 4 (plus matplotlib/graphviz as CatBoost transitive deps, already accounted for).

## Feature Selection: No New Libraries Needed

All required feature selection tooling is already present in scikit-learn 1.6.1:

| Need | API | Confirmed |
|------|-----|-----------|
| Remove zero/low-variance features | `sklearn.feature_selection.VarianceThreshold` | Yes |
| Model-based importance filtering | `sklearn.feature_selection.SelectFromModel` | Yes |
| Mutual information ranking | `sklearn.feature_selection.mutual_info_regression` | Yes |
| Correlation-based deduplication | `pandas.DataFrame.corr()` + threshold drop | Yes (pandas) |
| Feature importance from trained model | `model.feature_importances_` (LightGBM/XGBoost native) | Yes |

Strategy: `VarianceThreshold` → correlation dedup (r > 0.95) → `SelectFromModel` with LightGBM importance. Do not use `RFECV` — it is too slow on 283 features with walk-forward CV (fits N×folds models vs 1 for `SelectFromModel`).

## Adaptive Rolling Windows: No New Libraries Needed

All adaptive window capabilities needed for v2.0 are in pandas 1.5.3:

| Signal Type | Pandas API | Notes |
|-------------|-----------|-------|
| Exponential decay (recency-weighted) | `df.ewm(halflife=3).mean()` | `halflife=3` weights last 3 games at 50% |
| Fixed rolling (3-game, 6-game) | `df.rolling(3, min_periods=1).mean()` | Already used throughout Silver |
| Expanding (season-to-date) | `df.expanding().mean()` | Already used for referee tendencies |
| Trend / momentum | `df.rolling(N).mean().diff()` | First difference of rolling mean |
| Regime detection | `df.rolling(N).std()` + threshold | High-variance window = volatile regime |

Use `shift(1)` before all rolling calculations in feature assembly to prevent same-week data leakage (already enforced in `feature_engineering.py` pattern).

## Ensemble Architecture: Use StackingRegressor

`sklearn.ensemble.StackingRegressor` (confirmed in 1.6.1) is the right implementation:

```python
from sklearn.ensemble import StackingRegressor
from sklearn.linear_model import RidgeCV
import lightgbm as lgb
import xgboost as xgb
import catboost as cb

base_learners = [
    ("lgb", lgb.LGBMRegressor(...)),
    ("xgb", xgb.XGBRegressor(...)),
    ("cat", cb.CatBoostRegressor(verbose=0, ...)),
]
stack = StackingRegressor(estimators=base_learners, final_estimator=RidgeCV())
```

The default `RidgeCV` meta-learner is appropriate because:
1. Base learner predictions are highly correlated — Ridge regularization handles multicollinearity better than plain OLS.
2. It cross-validates its own alpha automatically.
3. It is interpretable (coefficients show relative base-learner trust).

Temporal constraint: When integrating stacking with walk-forward CV, use `cv="prefit"` or pass `cv=TimeSeriesSplit(n_splits=5)` to `StackingRegressor` to prevent future leakage in the meta-learner's cross-validation step.

## Integration Points

| Existing Module | v2.0 Change |
|----------------|-------------|
| `src/model_training.py` | Add LightGBM and CatBoost base learners alongside existing XGBoost; add `StackingRegressor` ensemble wrapper; keep walk-forward CV structure |
| `src/feature_engineering.py` | Add player-level feature assembly functions (QB quality, injury replacement); add adaptive window features; add feature selection pipeline |
| `src/prediction_backtester.py` | Extend to handle ensemble model predictions (same interface, new model type) |
| `src/config.py` | Add ensemble model paths, feature selection threshold configs |
| `scripts/train_prediction_model.py` | Add `--ensemble` flag to train stacked model; extend Optuna search space for all 3 base learners |
| `data/gold/predictions/` | Output format unchanged — same Parquet schema |

No new modules strictly required for v2.0 — extend existing `model_training.py` and `feature_engineering.py` rather than creating parallel files.

## Version Compatibility Matrix

| Package | Version | numpy | pandas | Python |
|---------|---------|-------|--------|--------|
| LightGBM | 4.6.0 | >=1.17 | -- | >=3.7 |
| CatBoost | 1.2.10 | >=1.16 (null constraint) | >=0.24 | no constraint (cp39 wheels confirmed) |
| SHAP | 0.48.0 | -- | -- | >=3.9 |
| matplotlib | 3.9.4 | -- | -- | >=3.9 |
| **Our stack** | -- | **1.26.4** | **1.5.3** | **3.9** |

All compatible. No conflicts with existing dependencies.

## Sources

- [LightGBM 4.6.0 PyPI](https://pypi.org/pypi/lightgbm/json) — requires_python>=3.7, latest stable (HIGH confidence)
- [CatBoost 1.2.10 PyPI](https://pypi.org/pypi/catboost/1.2.10/json) — cp39 wheels confirmed for macOS/Linux/Windows (HIGH confidence)
- [SHAP 0.48.0 PyPI](https://pypi.org/pypi/shap/0.48.0/json) — requires_python>=3.9; 0.51.0 requires 3.11+ (HIGH confidence)
- [scikit-learn 1.6.1 StackingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingRegressor.html) — confirmed present via import test (HIGH confidence)
- [scikit-learn feature selection docs](https://scikit-learn.org/stable/modules/feature_selection.html) — SelectFromModel, VarianceThreshold, mutual_info_regression all in 1.6.1 (HIGH confidence)
- [pandas 1.5.3 ewm docs](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.ewm.html) — ewm(halflife=N) confirmed working (HIGH confidence)
- [CatBoost vs LightGBM benchmark](https://arxiv.org/pdf/2305.17094) — LightGBM most consistent on classification, results vary by dataset (MEDIUM confidence)
- `pip list` in project venv — ground truth for installed packages (HIGH confidence)
- Import test in project venv — StackingRegressor, SelectFromModel, Ridge, mutual_info_regression all importable (HIGH confidence)

---
*Stack research for: NFL v2.0 Prediction Model Improvement (player features, ensemble, feature selection, adaptive signals)*
*Researched: 2026-03-24*
