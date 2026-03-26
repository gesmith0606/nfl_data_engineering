# Phase 30: Model Ensemble - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a three-model stacking ensemble (XGBoost + LightGBM + CatBoost with Ridge meta-learner) trained on the SELECTED_FEATURES from Phase 29. Two separate ensembles (spread and total), each with its own base models and Ridge meta-learner. Backtest against the v1.4 single-XGBoost baseline with ATS/ROI comparison.

</domain>

<decisions>
## Implementation Decisions

### Stacking Architecture
- **D-01:** Single-pass OOF — each base model runs walk-forward CV once, producing out-of-fold predictions for each validation season
- **D-02:** Two separate ensemble pipelines — one for spread prediction, one for total prediction — each independently optimized
- **D-03:** Ridge meta-learner per target trains on a 3-column OOF matrix (one column per base model's OOF predictions)
- **D-04:** All 3 base models use the same SELECTED_FEATURES from Phase 29 — stacking leverages model diversity, not feature diversity
- **D-05:** Walk-forward CV fold structure matches existing VALIDATION_SEASONS=[2019, 2020, 2021, 2022, 2023] with HOLDOUT_SEASON=2024 excluded

### Hyperparameter Tuning
- **D-06:** Per-model independent Optuna tuning — each model gets its own study with model-specific search space
- **D-07:** 50 Optuna trials per model, using walk-forward CV MAE as the objective function
- **D-08:** XGBoost keeps existing CONSERVATIVE_PARAMS as default starting point; LightGBM and CatBoost get analogous conservative defaults (shallow trees, strong regularization)
- **D-09:** Tuning is optional (CLI flag) — models can train with conservative defaults for quick iteration

### Model Artifact Layout
- **D-10:** Flat directory at `models/ensemble/` with prefixed filenames: `xgb_spread.json`, `lgb_spread.txt`, `cb_spread.cbm`, `ridge_spread.pkl`, plus corresponding `*_total.*` files
- **D-11:** Single `models/ensemble/metadata.json` lists all components, their roles, training dates, CV MAE, and the SELECTED_FEATURES used
- **D-12:** Prediction CLI dispatch via `--ensemble` flag on `generate_predictions.py` — loads from `models/ensemble/` when set, defaults to single XGBoost from `models/`
- **D-13:** Backtest CLI gets `--ensemble` flag on `backtest_predictions.py` for side-by-side ATS/ROI comparison

### Claude's Discretion
- Exact Optuna search space bounds for LightGBM and CatBoost (should be conservative like XGBoost's)
- How to generalize walk_forward_cv() for multiple model types (new function vs parameterized existing)
- Ridge regularization alpha selection (CV or fixed)
- Test structure and organization
- Whether to add ensemble training to existing train_prediction_model.py or create new script

</decisions>

<specifics>
## Specific Ideas

- The OOF matrix for Ridge is conceptually simple: for each game in the training set, each base model produces a prediction from a fold where it never saw that game — these 3 predictions become Ridge's input features
- LightGBM native format is `.txt`, CatBoost is `.cbm`, XGBoost is `.json` — each has its own serialization
- Ridge from sklearn.linear_model is lightweight — pickle serialization is fine
- The `--ensemble` flag pattern keeps the existing single-model workflow untouched for backwards compatibility

</specifics>

<canonical_refs>
## Canonical References

### Existing model infrastructure
- `src/model_training.py` — `walk_forward_cv()` with 5 season-boundary folds, `train_final_model()` with JSON serialization, `CONSERVATIVE_PARAMS`
- `src/config.py` — `HOLDOUT_SEASON=2024`, `VALIDATION_SEASONS`, `SELECTED_FEATURES`, `MODEL_DIR`
- `src/feature_selector.py` — `FeatureSelectionResult`, `select_features_for_fold()`

### Backtesting and prediction
- `src/prediction_backtester.py` — existing backtest with ATS/O-U/vig-adjusted profit at -110
- `scripts/generate_predictions.py` — prediction CLI that loads models and generates weekly/preseason predictions
- `scripts/backtest_predictions.py` — backtest CLI with per-season breakdown

### Feature engineering
- `src/feature_engineering.py` — `assemble_multiyear_features()`, `get_feature_columns()`

### Research references
- `.planning/research/ARCHITECTURE.md` — ensemble stacking architecture recommendations
- `.planning/research/FEATURES.md` — feature selection approach (feeds into this phase's feature set)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `walk_forward_cv()` in model_training.py — core fold logic reusable, but currently XGBoost-specific (creates `xgb.XGBRegressor` directly). Needs generalization to accept any sklearn-compatible model
- `train_final_model()` — JSON serialization XGBoost-specific. LightGBM/CatBoost need their own save/load
- `WalkForwardResult` dataclass — reusable as-is for any model type's CV results
- `CONSERVATIVE_PARAMS` — XGBoost-specific dict, need analogous defaults for LGB/CB

### Established Patterns
- Walk-forward CV with temporal ordering and holdout guard
- Model + metadata sidecar JSON pattern
- CLI with argparse, `--season`/`--week` flags

### Integration Points
- `config.py`: Add `ENSEMBLE_DIR`, LGB/CB default params
- `generate_predictions.py`: Add `--ensemble` flag, load ensemble models
- `backtest_predictions.py`: Add `--ensemble` flag for comparison output
- `model_training.py`: Generalize or create parallel functions for LGB/CB

</code_context>

<deferred>
## Deferred Ideas

- Bayesian stacking (replace Ridge with Bayesian Ridge or GP) — Phase 31 or future
- Model weighting based on recent performance — future enhancement
- Online ensemble updating for in-season adaptation — v3.0 production infra
- Neural network base learner — out of scope per REQUIREMENTS.md

</deferred>

---

*Phase: 30-model-ensemble*
*Context gathered: 2026-03-25*
