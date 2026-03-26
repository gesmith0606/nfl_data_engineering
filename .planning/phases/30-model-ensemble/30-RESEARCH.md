# Phase 30: Model Ensemble - Research

**Researched:** 2026-03-25
**Domain:** Stacking ensemble (XGBoost + LightGBM + CatBoost + Ridge meta-learner)
**Confidence:** HIGH

## Summary

Phase 30 adds a three-model stacking ensemble on top of the existing single-XGBoost prediction pipeline. All three libraries (XGBoost 2.1.4, LightGBM 4.6.0, CatBoost 1.2.10) are already installed and verified working with Python 3.9. The sklearn-compatible `.fit()/.predict()` API is consistent across all three, making the walk-forward CV generalization straightforward. Each library has distinct save/load patterns: XGBoost uses `.save_model()/.load_model()` with JSON, LightGBM uses `booster_.save_model()` for `.txt` format and `lgb.Booster(model_file=...)` for loading, CatBoost uses `.save_model()/.load_model()` with `.cbm` format.

The core technical challenge is generating temporally-correct out-of-fold (OOF) predictions. Each base model must produce predictions for every validation season using only training data from prior seasons. These OOF predictions form a 3-column matrix that becomes the Ridge meta-learner's training data. The existing `walk_forward_cv()` function handles the fold logic correctly but is XGBoost-specific -- it needs generalization to accept any sklearn-compatible regressor or a factory function.

**Primary recommendation:** Create a new `src/ensemble_training.py` module with a generalized `walk_forward_cv_generic()` that accepts a model factory callable, plus ensemble-specific training/saving/loading functions. Keep the existing `model_training.py` untouched for single-model backward compatibility.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Single-pass OOF -- each base model runs walk-forward CV once, producing out-of-fold predictions for each validation season
- **D-02:** Two separate ensemble pipelines -- one for spread prediction, one for total prediction -- each independently optimized
- **D-03:** Ridge meta-learner per target trains on a 3-column OOF matrix (one column per base model's OOF predictions)
- **D-04:** All 3 base models use the same SELECTED_FEATURES from Phase 29 -- stacking leverages model diversity, not feature diversity
- **D-05:** Walk-forward CV fold structure matches existing VALIDATION_SEASONS=[2019, 2020, 2021, 2022, 2023] with HOLDOUT_SEASON=2024 excluded
- **D-06:** Per-model independent Optuna tuning -- each model gets its own study with model-specific search space
- **D-07:** 50 Optuna trials per model, using walk-forward CV MAE as the objective function
- **D-08:** XGBoost keeps existing CONSERVATIVE_PARAMS as default starting point; LightGBM and CatBoost get analogous conservative defaults (shallow trees, strong regularization)
- **D-09:** Tuning is optional (CLI flag) -- models can train with conservative defaults for quick iteration
- **D-10:** Flat directory at `models/ensemble/` with prefixed filenames: `xgb_spread.json`, `lgb_spread.txt`, `cb_spread.cbm`, `ridge_spread.pkl`, plus corresponding `*_total.*` files
- **D-11:** Single `models/ensemble/metadata.json` lists all components, their roles, training dates, CV MAE, and the SELECTED_FEATURES used
- **D-12:** Prediction CLI dispatch via `--ensemble` flag on `generate_predictions.py` -- loads from `models/ensemble/` when set, defaults to single XGBoost from `models/`
- **D-13:** Backtest CLI gets `--ensemble` flag on `backtest_predictions.py` for side-by-side ATS/ROI comparison

### Claude's Discretion
- Exact Optuna search space bounds for LightGBM and CatBoost (should be conservative like XGBoost's)
- How to generalize walk_forward_cv() for multiple model types (new function vs parameterized existing)
- Ridge regularization alpha selection (CV or fixed)
- Test structure and organization
- Whether to add ensemble training to existing train_prediction_model.py or create new script

### Deferred Ideas (OUT OF SCOPE)
- Bayesian stacking (replace Ridge with Bayesian Ridge or GP) -- Phase 31 or future
- Model weighting based on recent performance -- future enhancement
- Online ensemble updating for in-season adaptation -- v3.0 production infra
- Neural network base learner -- out of scope per REQUIREMENTS.md
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENS-01 | Train LightGBM base learner with model-specific Optuna search space | LGB conservative defaults + Optuna search space documented below; LGBMRegressor sklearn API verified |
| ENS-02 | Train CatBoost base learner with model-specific tuning constraints | CB conservative defaults + Optuna search space documented; CatBoostRegressor API verified |
| ENS-03 | Generate temporal OOF predictions from walk-forward CV for stacking | Generalized walk_forward_cv pattern returns OOF predictions per fold; temporal ordering preserved |
| ENS-04 | Train Ridge meta-learner on OOF predictions from all base models | Ridge with RidgeCV for automatic alpha selection; 3-column OOF matrix pattern documented |
| ENS-05 | Backtest ensemble model and compare ATS/ROI vs single XGBoost baseline | --ensemble flag pattern for both backtest and prediction CLIs; side-by-side output format |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 2.1.4 | Base learner 1 (existing) | Already in use, proven baseline |
| lightgbm | 4.6.0 | Base learner 2 | Installed Phase 28, fast training, different split algorithm from XGB |
| catboost | 1.2.10 | Base learner 3 | Installed Phase 28, ordered boosting provides model diversity |
| scikit-learn | 1.6.1 | Ridge meta-learner, RidgeCV | Already installed, lightweight linear stacking |
| optuna | 4.8.0 | Per-model hyperparameter tuning | Already used for XGBoost tuning in v1.4 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pickle (stdlib) | N/A | Ridge model serialization | Save/load Ridge meta-learner |
| numpy | (installed) | OOF matrix construction | Stacking OOF predictions into Ridge input |
| pandas | (installed) | Data handling | Feature data, OOF DataFrames |

**Installation:** All libraries already installed. No new dependencies needed.

## Architecture Patterns

### Recommended Project Structure
```
src/
  ensemble_training.py      # NEW: generalized CV, OOF generation, ensemble train/save/load
  model_training.py         # UNCHANGED: single XGBoost (backward compat)
  config.py                 # ADD: LGB_PARAMS, CB_PARAMS, ENSEMBLE_DIR
  prediction_backtester.py  # UNCHANGED: reused for ensemble eval

scripts/
  train_ensemble.py         # NEW: CLI for training full ensemble pipeline
  train_prediction_model.py # UNCHANGED: single XGBoost training
  generate_predictions.py   # MODIFIED: add --ensemble flag
  backtest_predictions.py   # MODIFIED: add --ensemble flag

models/
  spread/                   # EXISTING: single XGBoost spread
  total/                    # EXISTING: single XGBoost total
  ensemble/                 # NEW: flat directory with all ensemble artifacts
    xgb_spread.json
    lgb_spread.txt
    cb_spread.cbm
    ridge_spread.pkl
    xgb_total.json
    lgb_total.txt
    cb_total.cbm
    ridge_total.pkl
    metadata.json
```

### Pattern 1: Generalized Walk-Forward CV with OOF Collection
**What:** A model-agnostic walk_forward_cv that accepts a factory callable and returns both CV metrics AND out-of-fold predictions.
**When to use:** Training any base model for the stacking ensemble.
**Recommendation:** Create a new function rather than modifying the existing one. The existing `walk_forward_cv()` is XGBoost-specific and works for the single-model path. A new `walk_forward_cv_with_oof()` in `ensemble_training.py` keeps concerns separate.

```python
from typing import Callable, Tuple

def walk_forward_cv_with_oof(
    all_data: pd.DataFrame,
    feature_cols: list,
    target_col: str,
    model_factory: Callable[[], Any],
    fit_kwargs: Optional[dict] = None,
    val_seasons: Optional[list] = None,
) -> Tuple[WalkForwardResult, pd.DataFrame]:
    """Walk-forward CV that also collects OOF predictions.

    Args:
        model_factory: Callable that returns a fresh, untrained model instance
                       with .fit() and .predict() methods.
        fit_kwargs: Extra kwargs passed to model.fit() (e.g., callbacks for LGB).

    Returns:
        Tuple of (WalkForwardResult, oof_df) where oof_df has columns:
        [game_id, season, week, oof_prediction].
    """
```

### Pattern 2: Model Factory Callables
**What:** Each model type has a factory function that returns a fresh sklearn-compatible instance.
**When to use:** Passed to `walk_forward_cv_with_oof()` for each base model.

```python
import lightgbm as lgb
import catboost as cb
import xgboost as xgb

def make_xgb_model(params: dict) -> xgb.XGBRegressor:
    p = params.copy()
    early_stop = p.pop("early_stopping_rounds", 50)
    return xgb.XGBRegressor(early_stopping_rounds=early_stop, **p)

def make_lgb_model(params: dict) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**params)

def make_cb_model(params: dict) -> cb.CatBoostRegressor:
    return cb.CatBoostRegressor(**params)
```

### Pattern 3: OOF Matrix Assembly for Ridge
**What:** After all 3 base models produce OOF predictions, join them into a 3-column matrix aligned by game_id.
**When to use:** Before training the Ridge meta-learner.

```python
oof_matrix = pd.DataFrame({
    "game_id": xgb_oof["game_id"],
    "xgb_pred": xgb_oof["oof_prediction"],
    "lgb_pred": lgb_oof["oof_prediction"],
    "cb_pred": cb_oof["oof_prediction"],
    "actual": xgb_oof["actual"],  # target for Ridge
})
# Ridge trains on columns ["xgb_pred", "lgb_pred", "cb_pred"] -> "actual"
```

### Pattern 4: Early Stopping Differences
**What:** Each library handles early stopping differently in its sklearn API.
**Critical detail:**

```python
# XGBoost: early_stopping_rounds as constructor param
model = xgb.XGBRegressor(early_stopping_rounds=50, **params)
model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

# LightGBM: via callbacks (not constructor param in 4.x)
model = lgb.LGBMRegressor(n_estimators=500, verbose=-1, **params)
model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
          callbacks=[lgb.early_stopping(50, verbose=False)])

# CatBoost: early_stopping_rounds as constructor param
model = cb.CatBoostRegressor(iterations=500, early_stopping_rounds=50, verbose=0, **params)
model.fit(X_train, y_train, eval_set=(X_val, y_val))  # tuple, not list of tuples!
```

### Pattern 5: Model Save/Load Differences
**What:** Each library has different serialization.

```python
# XGBoost
model.save_model("xgb_spread.json")  # JSON format
loaded = xgb.XGBRegressor(); loaded.load_model("xgb_spread.json")

# LightGBM - save via booster, load via Booster class
model.booster_.save_model("lgb_spread.txt")  # text format
loaded = lgb.Booster(model_file="lgb_spread.txt")
# loaded.predict() works directly on numpy arrays

# CatBoost
model.save_model("cb_spread.cbm")  # binary format
loaded = cb.CatBoostRegressor(); loaded.load_model("cb_spread.cbm")

# Ridge - pickle
import pickle
with open("ridge_spread.pkl", "wb") as f: pickle.dump(model, f)
with open("ridge_spread.pkl", "rb") as f: loaded = pickle.load(f)
```

**Important LightGBM note:** After loading via `lgb.Booster`, prediction returns numpy arrays directly. The `.predict()` API is the same shape. No need to wrap back into LGBMRegressor.

### Anti-Patterns to Avoid
- **Modifying existing `walk_forward_cv()`:** Changing its signature or behavior risks breaking the single-XGBoost pipeline. Create a new function instead.
- **Sharing OOF folds across targets:** Spread and total ensembles must be independently trained (D-02). Don't optimize one then reuse its hyperparams for the other.
- **Using Ridge without alpha tuning:** Fixed alpha=1.0 may underfit or overfit. Use `RidgeCV` with a small set of alphas for automatic selection.
- **Training Ridge on non-OOF predictions:** If base models predict on data they were trained on, the meta-learner sees optimistically biased inputs. OOF predictions are mandatory.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Ridge alpha selection | Manual grid search | `sklearn.linear_model.RidgeCV` | Built-in efficient LOO-CV for alpha selection |
| Walk-forward fold logic | New fold splitting code | Reuse fold boundaries from existing `VALIDATION_SEASONS` | Already tested and proven correct |
| Model serialization | Custom JSON format | Native save/load per library | Each library's format is optimized and version-safe |
| Hyperparameter search | Manual param grid | Optuna (already integrated) | Bayesian optimization, pruning, existing pattern in codebase |

## Common Pitfalls

### Pitfall 1: LightGBM Eval Set Format
**What goes wrong:** LightGBM's sklearn API takes `eval_set=[(X, y)]` (list of tuples) like XGBoost, but early stopping must be passed via `callbacks` parameter in LightGBM 4.x, not as a constructor argument.
**Why it happens:** The API looks similar to XGBoost but differs in early stopping mechanism.
**How to avoid:** Always use `callbacks=[lgb.early_stopping(50, verbose=False)]` in `.fit()`.
**Warning signs:** DeprecationWarning about early_stopping_rounds in constructor.

### Pitfall 2: CatBoost Eval Set Format
**What goes wrong:** CatBoost's `.fit()` takes `eval_set=(X, y)` as a plain tuple, NOT `eval_set=[(X, y)]` like XGBoost/LightGBM.
**Why it happens:** CatBoost has a different API convention.
**How to avoid:** Pass `eval_set=(X_val, y_val)` without wrapping in a list.
**Warning signs:** CatBoostError about invalid eval_set format.

### Pitfall 3: LightGBM Booster vs Regressor Loading
**What goes wrong:** Saving with `booster_.save_model()` produces a Booster-format file. Loading it back into `LGBMRegressor` doesn't work directly.
**Why it happens:** The sklearn wrapper and the native Booster are different classes.
**How to avoid:** Load with `lgb.Booster(model_file=path)` and call `.predict()` on it directly. Both return numpy arrays.
**Warning signs:** AttributeError or incorrect predictions after loading.

### Pitfall 4: OOF Temporal Leakage
**What goes wrong:** If the OOF matrix includes predictions where a base model saw future data, the Ridge meta-learner learns from leaked signal.
**Why it happens:** Incorrect fold assignment or using full-data predictions instead of OOF.
**How to avoid:** Each OOF prediction for season S must come from a model trained ONLY on seasons < S. Verify by checking fold_details.
**Warning signs:** Ensemble ATS accuracy suspiciously high (> 58%), especially on early seasons.

### Pitfall 5: Feature Mismatch at Prediction Time
**What goes wrong:** Ensemble models trained on SELECTED_FEATURES but prediction pipeline assembles different columns.
**Why it happens:** SELECTED_FEATURES may be None in config.py if Phase 29 hasn't populated it.
**How to avoid:** Store feature list in metadata.json. At prediction time, load from metadata, not from config.py.
**Warning signs:** ValueError about feature count mismatch, or silently degraded predictions.

### Pitfall 6: Ridge Sees Different Feature Scale Than Expected
**What goes wrong:** If base model predictions have very different scales (unlikely for spread/total), Ridge coefficients become unstable.
**Why it happens:** Ridge is scale-sensitive on its inputs.
**How to avoid:** All 3 base models predict the same target (e.g., point margin), so predictions should be on similar scales. No normalization needed in practice, but verify with a sanity check on OOF prediction distributions.
**Warning signs:** Ridge coefficients with very large magnitudes (> 10).

## Code Examples

### Conservative Default Params (Analogous to XGBoost's CONSERVATIVE_PARAMS)

```python
# config.py additions

LGB_CONSERVATIVE_PARAMS = {
    "objective": "regression",
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 500,
    "min_child_samples": 20,   # analogous to min_child_weight
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "random_state": 42,
    "verbose": -1,
    "force_col_wise": True,  # suppress threading warning
}

CB_CONSERVATIVE_PARAMS = {
    "loss_function": "RMSE",
    "depth": 4,
    "learning_rate": 0.05,
    "iterations": 500,
    "l2_leaf_reg": 5.0,        # analogous to reg_lambda
    "min_data_in_leaf": 20,    # analogous to min_child_weight
    "subsample": 0.8,          # requires bootstrap_type="Bernoulli"
    "bootstrap_type": "Bernoulli",
    "rsm": 0.7,               # analogous to colsample_bytree
    "random_seed": 42,
    "verbose": 0,
    "early_stopping_rounds": 50,
    "allow_writing_files": False,  # don't create catboost_info/ directory
}

ENSEMBLE_DIR = os.path.join(MODEL_DIR, "ensemble")
```

### Optuna Search Spaces for LightGBM and CatBoost

```python
# LightGBM Optuna search space
def lgb_objective(trial, all_data, feature_cols, target_col):
    params = {
        "objective": "regression",
        "max_depth": trial.suggest_int("max_depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "n_estimators": 500,
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
        "subsample": trial.suggest_float("subsample", 0.6, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 0.8),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.1, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 20.0, log=True),
        "random_state": 42,
        "verbose": -1,
        "force_col_wise": True,
    }
    result = walk_forward_cv_with_oof(all_data, feature_cols, target_col,
                                       model_factory=lambda: make_lgb_model(params))
    return result[0].mean_mae  # WalkForwardResult.mean_mae

# CatBoost Optuna search space
def cb_objective(trial, all_data, feature_cols, target_col):
    params = {
        "loss_function": "RMSE",
        "depth": trial.suggest_int("depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "iterations": 500,
        "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 20.0, log=True),
        "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 10, 50),
        "subsample": trial.suggest_float("subsample", 0.6, 0.9),
        "bootstrap_type": "Bernoulli",
        "rsm": trial.suggest_float("rsm", 0.5, 0.8),
        "random_seed": 42,
        "verbose": 0,
        "early_stopping_rounds": 50,
        "allow_writing_files": False,
    }
    result = walk_forward_cv_with_oof(all_data, feature_cols, target_col,
                                       model_factory=lambda: make_cb_model(params))
    return result[0].mean_mae
```

### Ridge Meta-Learner with RidgeCV

```python
from sklearn.linear_model import RidgeCV

def train_ridge_meta(oof_matrix: pd.DataFrame, target_col: str) -> RidgeCV:
    """Train Ridge meta-learner on OOF predictions with automatic alpha selection.

    Args:
        oof_matrix: DataFrame with columns xgb_pred, lgb_pred, cb_pred, and target.
        target_col: Name of the actual target column.

    Returns:
        Fitted RidgeCV model.
    """
    feature_cols = ["xgb_pred", "lgb_pred", "cb_pred"]
    X = oof_matrix[feature_cols].values
    y = oof_matrix[target_col].values

    ridge = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0])
    ridge.fit(X, y)
    # ridge.alpha_ gives the selected alpha
    return ridge
```

### Ensemble Prediction at Inference Time

```python
def predict_ensemble(game_features, spread_models, total_models):
    """Generate ensemble predictions for a set of games.

    spread_models / total_models are dicts with keys: 'xgb', 'lgb', 'cb', 'ridge'
    """
    features = game_features[SELECTED_FEATURES].fillna(0.0)

    # Base model predictions
    xgb_pred = spread_models["xgb"].predict(features)
    lgb_pred = spread_models["lgb"].predict(features)  # Booster.predict()
    cb_pred = spread_models["cb"].predict(features)

    # Stack into Ridge input
    meta_input = np.column_stack([xgb_pred, lgb_pred, cb_pred])
    ensemble_pred = spread_models["ridge"].predict(meta_input)

    return ensemble_pred
```

### Metadata Schema for `models/ensemble/metadata.json`

```json
{
  "ensemble_version": "1.0",
  "trained_at": "2026-03-25T12:00:00Z",
  "training_seasons": [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023],
  "holdout_season": 2024,
  "selected_features": ["diff_off_epa_per_play_roll3", "..."],
  "n_features": 85,
  "targets": {
    "spread": {
      "target_col": "actual_margin",
      "base_models": {
        "xgb": {"file": "xgb_spread.json", "cv_mae": 11.2, "params": {}},
        "lgb": {"file": "lgb_spread.txt", "cv_mae": 11.1, "params": {}},
        "cb":  {"file": "cb_spread.cbm", "cv_mae": 11.3, "params": {}}
      },
      "meta_learner": {
        "file": "ridge_spread.pkl",
        "alpha": 1.0,
        "coefficients": [0.35, 0.40, 0.25],
        "ensemble_cv_mae": 10.9
      }
    },
    "total": {
      "target_col": "actual_total",
      "base_models": {
        "xgb": {"file": "xgb_total.json", "cv_mae": 10.5},
        "lgb": {"file": "lgb_total.txt", "cv_mae": 10.4},
        "cb":  {"file": "cb_total.cbm", "cv_mae": 10.6}
      },
      "meta_learner": {
        "file": "ridge_total.pkl",
        "alpha": 10.0,
        "coefficients": [0.30, 0.35, 0.35],
        "ensemble_cv_mae": 10.2
      }
    }
  }
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single XGBoost (v1.4) | 3-model stacking ensemble | Phase 30 | Model diversity reduces variance; Ridge learns optimal blending |
| Full 283-feature set | SELECTED_FEATURES from Phase 29 | Phase 29 | Reduced feature set prevents overfitting in ensemble |
| XGBoost-only Optuna | Per-model Optuna studies | Phase 30 | Each model optimized within its own hyperparameter space |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (installed) |
| Config file | None (uses pytest defaults) |
| Quick run command | `python -m pytest tests/test_ensemble_training.py -x -v` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENS-01 | LightGBM trains with model-specific Optuna space | unit | `python -m pytest tests/test_ensemble_training.py::TestLGBTraining -x` | No - Wave 0 |
| ENS-02 | CatBoost trains with model-specific tuning constraints | unit | `python -m pytest tests/test_ensemble_training.py::TestCBTraining -x` | No - Wave 0 |
| ENS-03 | Temporal OOF predictions from walk-forward CV | unit | `python -m pytest tests/test_ensemble_training.py::TestOOFGeneration -x` | No - Wave 0 |
| ENS-04 | Ridge meta-learner on OOF predictions | unit | `python -m pytest tests/test_ensemble_training.py::TestRidgeMeta -x` | No - Wave 0 |
| ENS-05 | Ensemble backtest with ATS/ROI comparison | integration | `python -m pytest tests/test_ensemble_training.py::TestEnsembleBacktest -x` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_ensemble_training.py -x -v`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ensemble_training.py` -- covers ENS-01 through ENS-05
- [ ] Synthetic data fixture reusable from test_model_training.py pattern (copy `_make_synthetic_game_data`)

## Open Questions

1. **SELECTED_FEATURES is currently None**
   - What we know: Phase 29 populates it via config rewriting. If it's still None at ensemble training time, we fall back to `get_feature_columns()`.
   - What's unclear: Whether Phase 29 has been executed and populated the value.
   - Recommendation: Ensemble training code should check `SELECTED_FEATURES` and fall back to `get_feature_columns(all_data)` if None. Log a warning when falling back.

2. **Ridge alpha range**
   - What we know: RidgeCV with alphas=[0.01, 0.1, 1.0, 10.0, 100.0] covers a wide range.
   - What's unclear: Optimal alpha for ~2100 game OOF matrix with 3 features.
   - Recommendation: Use RidgeCV (automatic LOO-CV). The 5-value alpha grid is sufficient for 3 features. Report selected alpha in metadata.

## Sources

### Primary (HIGH confidence)
- Verified LightGBM 4.6.0 API: `lgb.LGBMRegressor.fit()` with `callbacks=[lgb.early_stopping()]` -- tested in local venv
- Verified CatBoost 1.2.10 API: `cb.CatBoostRegressor.fit()` with `eval_set=(X, y)` tuple -- tested in local venv
- Verified scikit-learn 1.6.1 `RidgeCV` -- standard sklearn API
- Existing codebase: `src/model_training.py`, `src/config.py`, `scripts/train_prediction_model.py`

### Secondary (MEDIUM confidence)
- LightGBM 4.x early stopping via callbacks (not constructor param) -- verified locally
- CatBoost `allow_writing_files=False` to suppress catboost_info/ directory -- verified locally

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed and version-verified in local venv
- Architecture: HIGH - follows existing patterns, generalization approach is straightforward
- Pitfalls: HIGH - all API differences verified by running actual code in local Python environment

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (stable libraries, no breaking changes expected)
